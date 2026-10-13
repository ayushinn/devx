from datetime import datetime
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from app.heat_risk import assess_heat_risk
from app.weather import WeatherProviderError, build_live_report, fetch_open_meteo_forecast

app = FastAPI(
    title="Heatwave Early Warning API",
    description=(
        "Heat-stress assessment using submitted observations or live Open-Meteo "
        "forecast data. It does not replace official warnings or medical advice."
    ),
    version="0.1.0",
)


class HeatObservation(BaseModel):
    temperature_c: Annotated[float, Field(ge=-80, le=70, description="Air temperature in Celsius")]
    humidity_percent: Annotated[float, Field(ge=0, le=100)]
    observed_at: datetime | None = None
    vulnerable_groups: list[str] = Field(default_factory=list)


class HeatRiskAssessment(BaseModel):
    heat_index_c: float
    risk_level: str
    risk_code: int
    recommendations: list[str]
    observed_at: datetime | None = None


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/v1/heat-risk/assess",
    response_model=HeatRiskAssessment,
    tags=["heat risk"],
    summary="Assess human heat stress for one weather observation",
)
def assess(observation: HeatObservation) -> dict[str, object]:
    return {
        **assess_heat_risk(
            observation.temperature_c,
            observation.humidity_percent,
            observation.vulnerable_groups,
        ),
        "observed_at": observation.observed_at,
    }


@app.post(
    "/api/v1/heat-risk/forecast",
    response_model=list[HeatRiskAssessment],
    tags=["heat risk"],
    summary="Assess a supplied series of forecast observations",
)
def assess_forecast(
    observations: Annotated[list[HeatObservation], Field(min_length=1, max_length=168)],
) -> list[dict[str, object]]:
    return [
        {
            **assess_heat_risk(
                observation.temperature_c,
                observation.humidity_percent,
                observation.vulnerable_groups,
            ),
            "observed_at": observation.observed_at,
        }
        for observation in observations
    ]


@app.get(
    "/api/v1/heat-risk/live",
    tags=["heat risk"],
    summary="Fetch live weather and assess the heatwave outlook for a location",
)
async def live_heat_risk(
    latitude: Annotated[float, Query(ge=-90, le=90)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
) -> dict[str, object]:
    try:
        forecast = await fetch_open_meteo_forecast(latitude, longitude)
        return build_live_report(forecast, latitude, longitude)
    except WeatherProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error