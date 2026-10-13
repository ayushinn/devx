from enum import IntEnum


class RiskLevel(IntEnum):
    LOW = 0
    CAUTION = 1
    EXTREME_CAUTION = 2
    DANGER = 3
    EXTREME_DANGER = 4


def calculate_heat_index_c(temperature_c: float, humidity_percent: float) -> float:
    """Calculate NOAA heat index in Celsius from air temperature and relative humidity."""
    temperature_f = temperature_c * 9 / 5 + 32

    if temperature_f < 80:
        heat_index_f = 0.5 * (
            temperature_f
            + 61
            + (temperature_f - 68) * 1.2
            + humidity_percent * 0.094
        )
        heat_index_f = (heat_index_f + temperature_f) / 2
    else:
        heat_index_f = (
            -42.379
            + 2.04901523 * temperature_f
            + 10.14333127 * humidity_percent
            - 0.22475541 * temperature_f * humidity_percent
            - 0.00683783 * temperature_f**2
            - 0.05481717 * humidity_percent**2
            + 0.00122874 * temperature_f**2 * humidity_percent
            + 0.00085282 * temperature_f * humidity_percent**2
            - 0.00000199 * temperature_f**2 * humidity_percent**2
        )

        if humidity_percent < 13 and 80 <= temperature_f <= 112:
            heat_index_f -= (
                (13 - humidity_percent) / 4
            ) * ((17 - abs(temperature_f - 95)) / 17) ** 0.5
        elif humidity_percent > 85 and 80 <= temperature_f <= 87:
            heat_index_f += (
                (humidity_percent - 85) / 10
            ) * ((87 - temperature_f) / 5)

    return round((heat_index_f - 32) * 5 / 9, 1)


def classify_risk(heat_index_c: float) -> RiskLevel:
    heat_index_f = heat_index_c * 9 / 5 + 32
    if heat_index_f >= 125:
        return RiskLevel.EXTREME_DANGER
    if heat_index_f >= 103:
        return RiskLevel.DANGER
    if heat_index_f >= 90:
        return RiskLevel.EXTREME_CAUTION
    if heat_index_f >= 80:
        return RiskLevel.CAUTION
    return RiskLevel.LOW


def recommendations(level: RiskLevel, vulnerable_groups: list[str]) -> list[str]:
    guidance = {
        RiskLevel.LOW: ["Stay hydrated and check local forecasts."],
        RiskLevel.CAUTION: [
            "Drink water regularly and take breaks in the shade.",
            "Limit strenuous outdoor activity during the hottest hours.",
        ],
        RiskLevel.EXTREME_CAUTION: [
            "Reschedule strenuous outdoor activity for a cooler part of the day.",
            "Take frequent breaks in a cool or shaded place and drink water.",
        ],
        RiskLevel.DANGER: [
            "Avoid strenuous outdoor activity; move essential tasks to cooler hours.",
            "Spend time in air-conditioned or shaded spaces and drink water frequently.",
        ],
        RiskLevel.EXTREME_DANGER: [
            "Avoid outdoor activity and seek an air-conditioned environment.",
            "Follow local emergency guidance; call emergency services for signs of heat illness.",
        ],
    }[level].copy()

    if vulnerable_groups:
        guidance.append(
            "Check on at-risk people, including "
            + ", ".join(vulnerable_groups)
            + ", and help them reach a cool place."
        )
    if level >= RiskLevel.EXTREME_CAUTION:
        guidance.append(
            "Confusion, fainting, or very hot skin can indicate an emergency; seek urgent medical help."
        )
    return guidance


def assess_heat_risk(
    temperature_c: float,
    humidity_percent: float,
    vulnerable_groups: list[str],
) -> dict[str, object]:
    heat_index_c = calculate_heat_index_c(temperature_c, humidity_percent)
    level = classify_risk(heat_index_c)
    return {
        "heat_index_c": heat_index_c,
        "risk_level": level.name.lower(),
        "risk_code": int(level),
        "recommendations": recommendations(level, vulnerable_groups),
    }