from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from app.heat_risk import RiskLevel, assess_heat_risk

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
HEATWAVE_HEAT_INDEX_THRESHOLD_C = 39.4
HEATWAVE_MINIMUM_CONSECUTIVE_DAYS = 2


class WeatherProviderError(Exception):
    pass


async def fetch_open_meteo_forecast(latitude: float, longitude: float) -> dict[str, Any]:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature",
        "hourly": "temperature_2m,relative_humidity_2m,apparent_temperature",
        "forecast_days": 7,
        "timezone": "auto",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(OPEN_METEO_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise WeatherProviderError("Live weather data is currently unavailable.") from error

    if not isinstance(payload, dict):
        raise WeatherProviderError("Weather provider returned an invalid response.")
    return payload


def _require_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WeatherProviderError(f"Weather provider response is missing valid {field} data.")
    return float(value)


def _parse_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise WeatherProviderError("Weather provider response contains an invalid timestamp.")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise WeatherProviderError("Weather provider response contains an invalid timestamp.") from error


def _find_heatwave_periods(daily_outlook: list[dict[str, Any]]) -> list[dict[str, Any]]:
    periods: list[dict[str, Any]] = []
    active_days: list[dict[str, Any]] = []

    def save_period() -> None:
        if len(active_days) >= HEATWAVE_MINIMUM_CONSECUTIVE_DAYS:
            periods.append(
                {
                    "start_date": active_days[0]["date"],
                    "end_date": active_days[-1]["date"],
                    "duration_days": len(active_days),
                    "peak_heat_index_c": max(
                        day["maximum_heat_index_c"] for day in active_days
                    ),
                }
            )

    for day in daily_outlook:
        is_hot = day["maximum_heat_index_c"] >= HEATWAVE_HEAT_INDEX_THRESHOLD_C
        is_consecutive = (
            not active_days
            or date.fromisoformat(day["date"])
            == date.fromisoformat(active_days[-1]["date"]) + timedelta(days=1)
        )
        if is_hot and is_consecutive:
            active_days.append(day)
        else:
            save_period()
            active_days = [day] if is_hot else []

    save_period()
    return periods


def build_live_report(
    payload: dict[str, Any], latitude: float, longitude: float
) -> dict[str, Any]:
    current = payload.get("current")
    hourly = payload.get("hourly")
    if not isinstance(current, dict) or not isinstance(hourly, dict):
        raise WeatherProviderError("Weather provider response is missing current or hourly data.")

    current_temperature = _require_number(current.get("temperature_2m"), "current temperature")
    current_humidity = _require_number(
        current.get("relative_humidity_2m"), "current humidity"
    )
    current_time = _parse_datetime(current.get("time"))
    current_assessment = assess_heat_risk(current_temperature, current_humidity, [])
    current_result = {
        "observed_at": current_time.isoformat(),
        "temperature_c": current_temperature,
        "humidity_percent": current_humidity,
        "apparent_temperature_c": current.get("apparent_temperature"),
        **current_assessment,
    }

    times = hourly.get("time")
    temperatures = hourly.get("temperature_2m")
    humidities = hourly.get("relative_humidity_2m")
    apparent_temperatures = hourly.get("apparent_temperature", [])
    if not (
        isinstance(times, list)
        and isinstance(temperatures, list)
        and isinstance(humidities, list)
        and len(times) == len(temperatures) == len(humidities)
    ):
        raise WeatherProviderError("Weather provider returned incomplete hourly forecast data.")
    if not isinstance(apparent_temperatures, list) or len(apparent_temperatures) != len(times):
        apparent_temperatures = [None] * len(times)

    by_date: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for time_value, temperature_value, humidity_value, apparent_value in zip(
        times, temperatures, humidities, apparent_temperatures
    ):
        if temperature_value is None or humidity_value is None:
            continue
        timestamp = _parse_datetime(time_value)
        temperature = _require_number(temperature_value, "hourly temperature")
        humidity = _require_number(humidity_value, "hourly humidity")
        assessment = assess_heat_risk(temperature, humidity, [])
        by_date[timestamp.date()].append(
            {
                "observed_at": timestamp.isoformat(),
                "temperature_c": temperature,
                "humidity_percent": humidity,
                "apparent_temperature_c": apparent_value,
                **assessment,
            }
        )

    if not by_date:
        raise WeatherProviderError("Weather provider returned no usable hourly forecast data.")

    daily_outlook = []
    for forecast_date, observations in sorted(by_date.items()):
        peak = max(observations, key=lambda item: item["heat_index_c"])
        daily_outlook.append(
            {
                "date": forecast_date.isoformat(),
                "maximum_temperature_c": max(item["temperature_c"] for item in observations),
                "maximum_heat_index_c": peak["heat_index_c"],
                "risk_level": peak["risk_level"],
                "risk_code": peak["risk_code"],
            }
        )

    periods = _find_heatwave_periods(daily_outlook)
    has_extreme_day = any(day["risk_code"] >= int(RiskLevel.DANGER) for day in daily_outlook)
    outlook_status = (
        "potential_heatwave"
        if periods
        else "extreme_heat_watch"
        if has_extreme_day
        else "no_heuristic_signal"
    )

    return {
        "provider": "Open-Meteo",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "location": {
            "latitude": payload.get("latitude", latitude),
            "longitude": payload.get("longitude", longitude),
            "timezone": payload.get("timezone"),
        },
        "current": current_result,
        "daily_outlook": daily_outlook,
        "heatwave_outlook": {
            "status": outlook_status,
            "potential_heatwave": bool(periods),
            "criteria": {
                "daily_max_heat_index_threshold_c": HEATWAVE_HEAT_INDEX_THRESHOLD_C,
                "minimum_consecutive_days": HEATWAVE_MINIMUM_CONSECUTIVE_DAYS,
            },
            "periods": periods,
        },
        "method_note": (
            "This is a screening heuristic based on forecast daily maximum heat index, "
            "not an official regional heatwave warning or a trained ML prediction."
        ),
    }