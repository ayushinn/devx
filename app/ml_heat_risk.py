from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib

from app.heat_risk import RiskLevel

MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "heat_risk_classifier.joblib"
MODEL_DISCLAIMER = (
    "Experimental model trained to imitate the existing NOAA heat-index risk rules; "
    "not validated against health outcomes or an official warning system."
)


@lru_cache(maxsize=1)
def _load_artifact() -> dict[str, Any] | None:
    if not MODEL_PATH.is_file():
        return None
    artifact = joblib.load(MODEL_PATH)
    if not isinstance(artifact, dict) or "model" not in artifact:
        raise ValueError("The trained heat-risk model artifact is invalid.")
    return artifact


def predict_heat_risk(temperature_c: float, humidity_percent: float) -> dict[str, object] | None:
    artifact = _load_artifact()
    if artifact is None:
        return None

    model = artifact["model"]
    features = [[temperature_c, humidity_percent]]
    risk_code = int(model.predict(features)[0])
    probabilities = model.predict_proba(features)[0]
    class_probabilities = {
        RiskLevel(int(class_code)).name.lower(): round(float(probability), 6)
        for class_code, probability in zip(model.classes_, probabilities)
    }
    return {
        "risk_level": RiskLevel(risk_code).name.lower(),
        "risk_code": risk_code,
        "class_probabilities": class_probabilities,
        "disclaimer": MODEL_DISCLAIMER,
    }