# Heatwave Early Warning API

A FastAPI backend for estimating human heat stress from submitted observations and Open-Meteo weather forecasts.

## Run locally

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`; interactive API documentation is at `/docs`.

## Endpoints

- `GET /health` reports service health.
- `POST /api/v1/heat-risk/assess` estimates heat index, categorizes risk, and returns precautions for one observation.
- `POST /api/v1/heat-risk/forecast` assesses a supplied series of up to 168 forecast observations.
- `GET /api/v1/heat-risk/live?latitude=19.076&longitude=72.8777` fetches current conditions and a seven-day forecast, then returns current risk, daily risk outlook, and potential heatwave periods.

The live endpoint uses Open-Meteo's Forecast API and does not require a key for basic use. Coordinates use decimal latitude/longitude.

Example request:

```json
{
  "temperature_c": 38,
  "humidity_percent": 65,
  "observed_at": "2026-10-14T12:00:00Z",
  "vulnerable_groups": ["older adults", "outdoor workers"]
}
```

## Heatwave screening and limitations

Heat index is the NOAA temperature-and-humidity estimate for shaded conditions with light wind. The live endpoint detects a **potential heatwave** when daily maximum heat index reaches 39.4 C for at least two consecutive forecast days. This is a transparent screening heuristic, not an official regional heatwave definition or a trained ML prediction. Thresholds should be calibrated to local climatology and official guidance before operational use. The service does not issue alerts or compute a full WBGT index.

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```