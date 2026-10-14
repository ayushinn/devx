import argparse
import csv
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import joblib
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, classification_report

from app.heat_risk import assess_heat_risk

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "heat_risk_training.csv"
MODEL_PATH = ROOT / "models" / "heat_risk_classifier.joblib"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
START_DATE = "2020-01-01"
END_DATE = "2025-12-31"
FEATURES = ["temperature_c", "humidity_percent"]
RISK_NAMES = ["low", "caution", "extreme_caution", "danger", "extreme_danger"]
CITIES = [
    {"name": "Mumbai", "latitude": 19.076, "longitude": 72.8777},
    {"name": "Delhi", "latitude": 28.6139, "longitude": 77.209},
    {"name": "Phoenix", "latitude": 33.4484, "longitude": -112.074},
    {"name": "Kuwait City", "latitude": 29.3759, "longitude": 47.9774},
    {"name": "Miami", "latitude": 25.7617, "longitude": -80.1918},
    {"name": "Oslo", "latitude": 59.9139, "longitude": 10.7522},
]
CSV_FIELDS = [
    "city",
    "latitude",
    "longitude",
    "observed_at",
    "temperature_c",
    "humidity_percent",
    "heat_index_c",
    "risk_code",
    "risk_level",
]


def download_dataset() -> int:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows_written = 0
    with httpx.Client(timeout=90) as client, DATA_PATH.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for city in CITIES:
            response = client.get(
                ARCHIVE_URL,
                params={
                    "latitude": city["latitude"],
                    "longitude": city["longitude"],
                    "start_date": START_DATE,
                    "end_date": END_DATE,
                    "hourly": "temperature_2m,relative_humidity_2m",
                    "timezone": "UTC",
                },
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            hourly = payload.get("hourly", {})
            times = hourly.get("time", [])
            temperatures = hourly.get("temperature_2m", [])
            humidities = hourly.get("relative_humidity_2m", [])
            if not (len(times) == len(temperatures) == len(humidities)):
                raise ValueError(f"Archive response has mismatched hourly data for {city['name']}.")

            for observed_at, temperature, humidity in zip(times, temperatures, humidities):
                if temperature is None or humidity is None:
                    continue
                temperature = float(temperature)
                humidity = float(humidity)
                assessment = assess_heat_risk(temperature, humidity, [])
                writer.writerow(
                    {
                        "city": city["name"],
                        "latitude": city["latitude"],
                        "longitude": city["longitude"],
                        "observed_at": observed_at,
                        "temperature_c": temperature,
                        "humidity_percent": humidity,
                        "heat_index_c": assessment["heat_index_c"],
                        "risk_code": assessment["risk_code"],
                        "risk_level": assessment["risk_level"],
                    }
                )
                rows_written += 1
            print(f"Downloaded historical observations for {city['name']}.")

    print(f"Saved {rows_written:,} observations to {DATA_PATH.relative_to(ROOT)}.")
    return rows_written


def read_dataset() -> tuple[list[list[float]], list[int], list[int]]:
    features: list[list[float]] = []
    labels: list[int] = []
    years: list[int] = []
    with DATA_PATH.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            features.append([float(row[feature]) for feature in FEATURES])
            labels.append(int(row["risk_code"]))
            years.append(date.fromisoformat(row["observed_at"][:10]).year)
    return features, labels, years


def train_model() -> None:
    if not DATA_PATH.is_file():
        raise FileNotFoundError(f"Training data not found: {DATA_PATH}. Run without --reuse-data first.")

    features, labels, years = read_dataset()
    train_indices = [index for index, year in enumerate(years) if year < 2025]
    test_indices = [index for index, year in enumerate(years) if year == 2025]
    if not train_indices or not test_indices:
        raise ValueError("Training data must contain observations before 2025 and during 2025.")

    x_train = [features[index] for index in train_indices]
    y_train = [labels[index] for index in train_indices]
    x_test = [features[index] for index in test_indices]
    y_test = [labels[index] for index in test_indices]

    model = HistGradientBoostingClassifier(
        learning_rate=0.12,
        max_iter=180,
        max_leaf_nodes=15,
        l2_regularization=0.1,
        class_weight="balanced",
        random_state=42,
    )
    model.fit(x_train, y_train)
    predictions = model.predict(x_test)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "features": FEATURES,
            "risk_names": RISK_NAMES,
            "training_period": f"{START_DATE} through 2024-12-31",
            "validation_period": "2025-01-01 through 2025-12-31",
            "label_method": "Existing NOAA heat-index formula and risk thresholds",
        },
        MODEL_PATH,
    )

    print(f"Training rows: {len(train_indices):,}; 2025 holdout rows: {len(test_indices):,}")
    print(f"2025 holdout accuracy: {accuracy_score(y_test, predictions):.4f}")
    print(
        classification_report(
            y_test,
            predictions,
            labels=sorted(set(labels)),
            target_names=[RISK_NAMES[code] for code in sorted(set(labels))],
            zero_division=0,
        )
    )
    print(f"Saved trained model to {MODEL_PATH.relative_to(ROOT)}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download weather observations and train the heat-risk baseline.")
    parser.add_argument(
        "--reuse-data",
        action="store_true",
        help="Train from the bundled CSV without downloading the archive again.",
    )
    args = parser.parse_args()
    if not args.reuse_data:
        download_dataset()
    train_model()


if __name__ == "__main__":
    main()