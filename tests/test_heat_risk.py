import asyncio

import httpx

from app.heat_risk import RiskLevel, calculate_heat_index_c, classify_risk
from app.main import app



def request(method: str, path: str, **kwargs: object) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


def test_noaa_heat_index_reference_case() -> None:
    # NOAA's regression formula: 90 F and 70% humidity produces about 106 F.
    result_c = calculate_heat_index_c((90 - 32) * 5 / 9, 70)
    assert round(result_c * 9 / 5 + 32) == 106


def test_risk_thresholds() -> None:
    assert classify_risk(26.7) == RiskLevel.CAUTION
    assert classify_risk(32.3) == RiskLevel.EXTREME_CAUTION
    assert classify_risk(39.5) == RiskLevel.DANGER


def test_assessment_endpoint_personalizes_recommendations() -> None:
    response = request(
        "POST",
        "/api/v1/heat-risk/assess",
        json={
            "temperature_c": 35,
            "humidity_percent": 60,
            "vulnerable_groups": ["older adults"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["risk_level"] in {"extreme_caution", "danger", "extreme_danger"}
    assert any("older adults" in item for item in body["recommendations"])


def test_rejects_invalid_humidity() -> None:
    response = request(
        "POST",
        "/api/v1/heat-risk/assess",
        json={"temperature_c": 35, "humidity_percent": 120},
    )
    assert response.status_code == 422


def test_forecast_endpoint_preserves_timestamps() -> None:
    response = request(
        "POST",
        "/api/v1/heat-risk/forecast",
        json=[
            {
                "temperature_c": 35,
                "humidity_percent": 60,
                "observed_at": "2026-10-14T12:00:00Z",
            }
        ],
    )

    assert response.status_code == 200
    assert response.json()[0]["observed_at"] == "2026-10-14T12:00:00Z"


def test_live_endpoint_fetches_weather_and_flags_consecutive_hot_days(monkeypatch) -> None:
    async def fake_forecast(latitude: float, longitude: float) -> dict[str, object]:
        assert latitude == 19.076
        assert longitude == 72.8777
        return {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": "Asia/Kolkata",
            "current": {
                "time": "2026-10-14T12:00",
                "temperature_2m": 40,
                "relative_humidity_2m": 55,
                "apparent_temperature": 46,
            },
            "hourly": {
                "time": [
                    "2026-10-14T12:00",
                    "2026-10-15T12:00",
                    "2026-10-16T12:00",
                ],
                "temperature_2m": [40, 40, 30],
                "relative_humidity_2m": [55, 55, 50],
                "apparent_temperature": [46, 46, 32],
            },
        }

    monkeypatch.setattr("app.main.fetch_open_meteo_forecast", fake_forecast)
    response = request(
        "GET",
        "/api/v1/heat-risk/live?latitude=19.076&longitude=72.8777",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "Open-Meteo"
    assert len(body["daily_outlook"]) == 3
    assert body["heatwave_outlook"]["potential_heatwave"] is True
    assert body["heatwave_outlook"]["periods"][0]["duration_days"] == 2