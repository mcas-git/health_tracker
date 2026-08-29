from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from health_tracker.config import PROFILE, Profile
from health_tracker.db import engine
from health_tracker.models import DailyEntry, NutritionLog


def _finite_number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def load_data() -> pd.DataFrame:
    with Session(engine) as session:
        daily = session.scalars(select(DailyEntry).order_by(DailyEntry.entry_date)).all()
        nutrition = session.scalars(select(NutritionLog).order_by(NutritionLog.entry_date)).all()
    daily_rows = [
        {column.name: getattr(row, column.name) for column in DailyEntry.__table__.columns}
        for row in daily
    ]
    nutrition_rows = [
        {
            "entry_date": row.entry_date,
            "calories": row.calories,
            "protein_g": row.protein_g,
            "carbs_g": row.carbs_g,
            "fat_g": row.fat_g,
            "fibre_g": row.fibre_g,
        }
        for row in nutrition
    ]
    left = pd.DataFrame(daily_rows)
    right = pd.DataFrame(nutrition_rows)
    if left.empty:
        left = pd.DataFrame(columns=["entry_date"])
    if right.empty:
        return left
    return left.merge(right, on="entry_date", how="outer").sort_values("entry_date")


def recent_kpi_table(df: pd.DataFrame, limit: int = 14) -> pd.DataFrame:
    """Build the compact dashboard export, including recorded circumstances."""
    data = df.copy()
    circumstance_fields = ["illness", "injury", "travel", "unusual_day"]
    recorded_circumstances = [field for field in circumstance_fields if field in data]
    if recorded_circumstances:
        data["extenuating_circumstance"] = (
            data[recorded_circumstances]
            .fillna(False)
            .astype(bool)
            .any(axis=1)
            .map({True: "Yes", False: "No"})
        )
    export_fields = [
        "entry_date",
        "weight_kg",
        "bmi",
        "waist_cm",
        "steps",
        "sleep_hours",
        "calories",
        "calories_burned",
        "mood",
        "energy",
        "extenuating_circumstance",
    ]
    columns = [field for field in export_fields if field in data]
    return data[columns].tail(limit).sort_values("entry_date", ascending=False)


def morning_measurement_status(item) -> dict[str, str]:
    """Format recorded morning measurements and make absent values explicit."""
    weight = getattr(item, "weight_kg", None) if item is not None else None
    waist = getattr(item, "waist_cm", None) if item is not None else None
    systolic = getattr(item, "systolic", None) if item is not None else None
    diastolic = getattr(item, "diastolic", None) if item is not None else None
    return {
        "Weight": f"{weight:.1f} kg" if weight is not None else "Missing",
        "Waist": f"{waist:.1f} cm" if waist is not None else "Missing",
        "Blood pressure": (
            f"{systolic}/{diastolic} mmHg"
            if systolic is not None and diastolic is not None
            else "Missing"
        ),
    }


def evening_measurement_status(item) -> dict[str, str]:
    """Format evening measurements and make absent values explicit."""
    field_specs = {
        "Resting heart rate": ("resting_heart_rate", lambda result: f"{result} bpm"),
        "Sleep": ("sleep_hours", lambda result: f"{result:.2f} h"),
        "Steps": ("steps", lambda result: f"{result:,}"),
        "Calories burned": ("calories_burned", lambda result: f"{result:,} kcal"),
        "Mood": ("mood", lambda result: f"{result}/10"),
        "Energy": ("energy", lambda result: f"{result}/10"),
        "Cravings": ("cravings", lambda result: f"{result}/10"),
        "Diet satisfaction": ("diet_satisfaction", lambda result: f"{result}/10"),
    }
    status = {}
    for label, (field, formatter) in field_specs.items():
        result = getattr(item, field, None) if item is not None else None
        status[label] = formatter(result) if result is not None else "Missing"
    return status


def morning_checkin_complete(item) -> bool:
    """Return whether the morning section was submitted or its core fields exist.

    The explicit flag keeps intentionally missing measurements valid. The field fallback
    preserves completion for entries saved before the submission flag was introduced.
    """
    if item is None:
        return False
    if bool(getattr(item, "morning_submitted", False)):
        return True
    return all(
        (measurement := _finite_number(getattr(item, field, None))) is not None
        and measurement > 0
        for field in ("weight_kg", "systolic", "diastolic")
    )


def evening_checkin_complete(item) -> bool:
    """Return whether every required smartwatch and evening rating is recorded."""
    if item is None:
        return False
    positive_fields = ("resting_heart_rate", "sleep_hours", "steps", "calories_burned")
    ratings = ("mood", "energy", "cravings", "diet_satisfaction")
    measurements_complete = all(
        (measurement := _finite_number(getattr(item, field, None))) is not None
        and measurement >= 0
        for field in positive_fields
    )
    ratings_complete = all(
        (rating := _finite_number(getattr(item, field, None))) is not None
        and 1 <= rating <= 10
        for field in ratings
    )
    return measurements_complete and ratings_complete


def excel_safe_data(df: pd.DataFrame) -> pd.DataFrame:
    """Return an Excel-compatible copy with timezone information removed."""
    result = df.copy()
    for column in result.columns:
        series = result[column]
        if isinstance(series.dtype, pd.DatetimeTZDtype):
            result[column] = series.dt.tz_localize(None)
        elif series.dtype == "object":
            result[column] = series.map(
                lambda item: (
                    item.replace(tzinfo=None)
                    if isinstance(item, datetime) and item.tzinfo is not None
                    else item
                )
            )
    return result


def daily_health_score(item, profile: Profile = PROFILE) -> tuple[int, str, list[str]] | None:
    """Create a non-diagnostic indicator from the measurements recorded for one day."""
    components: list[tuple[str, float]] = []
    bmi = _finite_number(getattr(item, "bmi", None))
    if bmi is not None and bmi > 0:
        components.append(
            ("BMI", 100 if 18.5 <= bmi < 25 else 65 if 25 <= bmi < 30 else 35 if bmi < 35 else 15)
        )
    waist = _finite_number(getattr(item, "waist_cm", None))
    if waist is not None and waist > 0:
        ratio = waist / profile.height_cm
        components.append(("Waist-to-height", 100 if ratio < 0.5 else 55 if ratio < 0.6 else 20))
    systolic = _finite_number(getattr(item, "systolic", None))
    diastolic = _finite_number(getattr(item, "diastolic", None))
    if systolic is not None and systolic > 0 and diastolic is not None and diastolic > 0:
        components.append(
            (
                "Blood pressure",
                100
                if 90 <= systolic < 135 and 60 <= diastolic < 85
                else 65
                if 90 <= systolic < 140 and 60 <= diastolic < 90
                else 25,
            )
        )
    resting_hr = _finite_number(getattr(item, "resting_heart_rate", None))
    if resting_hr is not None and resting_hr > 0:
        components.append(
            (
                "Resting heart rate",
                100 if 50 <= resting_hr <= 90 else 65 if 40 <= resting_hr <= 100 else 25,
            )
        )
    sleep = _finite_number(getattr(item, "sleep_hours", None))
    if sleep is not None and sleep >= 0:
        components.append(("Sleep", 100 if 7 <= sleep <= 9 else 65 if 6 <= sleep <= 10 else 30))
    steps = _finite_number(getattr(item, "steps", None))
    if steps is not None and steps >= 0:
        components.append(("Activity", 100 if steps >= 8000 else 70 if steps >= 5000 else 40))
    for field, label in (("mood", "Mood"), ("energy", "Energy")):
        rating = _finite_number(getattr(item, field, None))
        if rating is not None and 1 <= rating <= 10:
            components.append((label, rating * 10))
    if not components:
        return None
    score = round(sum(value for _, value in components) / len(components))
    label = "Strong" if score >= 75 else "Watch" if score >= 45 else "Needs attention"
    return score, label, [name for name, _ in components]


HEALTH_SCORE_HALF_LIFE_DAYS = 28
HEALTH_DOMAIN_WEIGHTS = {
    "Body": 0.25,
    "Cardiovascular": 0.25,
    "Recovery": 0.15,
    "Activity": 0.15,
    "Nutrition": 0.10,
    "Wellbeing": 0.10,
}


def _bounded_score(
    value: float,
    ideal_low: float,
    ideal_high: float,
    hard_low: float,
    hard_high: float,
) -> float:
    """Score a value against an ideal band with linear shoulders."""
    if ideal_low <= value <= ideal_high:
        return 100.0
    if value < ideal_low:
        return max(0.0, 100 * (value - hard_low) / (ideal_low - hard_low))
    return max(0.0, 100 * (hard_high - value) / (hard_high - ideal_high))


def _rating_score(value, *, inverse: bool = False) -> float | None:
    rating = _finite_number(value)
    if rating is None or not 1 <= rating <= 10:
        return None
    score = (rating - 1) / 9 * 100
    return 100 - score if inverse else score


def _recency_weighted_metric(
    data: pd.DataFrame,
    reference_date: pd.Timestamp,
    scorer,
) -> float | None:
    observations: list[tuple[float, float]] = []
    for _, row in data.iterrows():
        score = scorer(row)
        if score is None or not math.isfinite(score):
            continue
        recorded = pd.Timestamp(row["entry_date"]).normalize()
        days_old = max(0, int((reference_date - recorded).days))
        weight = 0.5 ** (days_old / HEALTH_SCORE_HALF_LIFE_DAYS)
        observations.append((max(0.0, min(100.0, score)), weight))
    if not observations:
        return None
    return sum(score * weight for score, weight in observations) / sum(
        weight for _, weight in observations
    )


def health_journey_score(
    data: pd.DataFrame,
    profile: Profile = PROFILE,
    targets: dict[str, float] | None = None,
) -> tuple[int, str, dict[str, int], date, date] | None:
    """Create a deterministic, recency-weighted indicator from all recorded history.

    Every observation remains in the calculation. Recent observations receive more weight
    through a fixed 28-day half-life. Metrics are averaged within domains first so frequently
    logged fields cannot overwhelm less-frequent measurements. Missing domains are omitted and
    the remaining fixed domain weights are renormalised.
    """
    if data.empty or "entry_date" not in data:
        return None
    history = data.copy()
    history["entry_date"] = pd.to_datetime(history["entry_date"], errors="coerce")
    history = history.dropna(subset=["entry_date"]).sort_values("entry_date")
    if history.empty:
        return None
    reference_date = history["entry_date"].max().normalize()

    def number(row, field: str) -> float | None:
        return _finite_number(row.get(field))

    def bmi_score(row) -> float | None:
        bmi = number(row, "bmi")
        weight = number(row, "weight_kg")
        if bmi is None and weight is not None and profile.height_cm > 0:
            bmi = weight / ((profile.height_cm / 100) ** 2)
        return _bounded_score(bmi, 18.5, 25.0, 14.0, 40.0) if bmi and bmi > 0 else None

    def waist_score(row) -> float | None:
        waist = number(row, "waist_cm")
        if waist is None or waist <= 0 or profile.height_cm <= 0:
            return None
        ratio = waist / profile.height_cm
        return 100.0 if ratio <= 0.5 else max(0.0, 100 - (ratio - 0.5) * 500)

    def blood_pressure_score(row) -> float | None:
        systolic = number(row, "systolic")
        diastolic = number(row, "diastolic")
        if systolic is None or diastolic is None:
            return None
        return min(
            _bounded_score(systolic, 90, 120, 70, 180),
            _bounded_score(diastolic, 60, 80, 40, 120),
        )

    def resting_heart_rate_score(row) -> float | None:
        heart_rate = number(row, "resting_heart_rate")
        if heart_rate is None:
            return None
        return _bounded_score(heart_rate, 50, 80, 35, 130)

    def sleep_score(row) -> float | None:
        sleep = number(row, "sleep_hours")
        return _bounded_score(sleep, 7, 9, 3, 12) if sleep is not None else None

    def steps_score(row) -> float | None:
        steps = number(row, "steps")
        return min(100.0, max(0.0, steps / 8000 * 100)) if steps is not None else None

    def target_score(row, field: str, target_key: str, mode: str) -> float | None:
        if not targets or not (target := _finite_number(targets.get(target_key))) or target <= 0:
            return None
        amount = number(row, field)
        if amount is None or amount < 0:
            return None
        ratio = amount / target
        if mode == "band":
            return _bounded_score(ratio, 0.85, 1.15, 0.4, 1.8)
        return min(100.0, max(0.0, ratio * 100))

    metric_scorers = {
        "Body": [bmi_score, waist_score],
        "Cardiovascular": [blood_pressure_score, resting_heart_rate_score],
        "Recovery": [sleep_score],
        "Activity": [steps_score],
        "Nutrition": [
            lambda row: target_score(row, "calories", "calories", "band"),
            lambda row: target_score(row, "protein_g", "protein_g", "minimum"),
            lambda row: target_score(row, "fibre_g", "fibre_g", "minimum"),
        ],
        "Wellbeing": [
            lambda row: _rating_score(row.get("mood")),
            lambda row: _rating_score(row.get("energy")),
            lambda row: _rating_score(row.get("cravings"), inverse=True),
            lambda row: _rating_score(row.get("diet_satisfaction")),
        ],
    }
    domains: dict[str, float] = {}
    for domain, scorers in metric_scorers.items():
        metrics = [
            result
            for scorer in scorers
            if (result := _recency_weighted_metric(history, reference_date, scorer)) is not None
        ]
        if metrics:
            domains[domain] = sum(metrics) / len(metrics)
    if not domains:
        return None
    available_weight = sum(HEALTH_DOMAIN_WEIGHTS[domain] for domain in domains)
    score = round(
        sum(domains[domain] * HEALTH_DOMAIN_WEIGHTS[domain] for domain in domains)
        / available_weight
    )
    critical_scores = [
        domains[domain] for domain in ("Body", "Cardiovascular") if domain in domains
    ]
    if any(domain_score < 25 for domain_score in critical_scores):
        score = min(score, 49)
    elif any(domain_score < 50 for domain_score in critical_scores):
        score = min(score, 74)
    if len(domains) < 3:
        label = "Limited data"
    else:
        label = "Strong" if score >= 75 else "Watch" if score >= 50 else "Needs attention"
    return (
        score,
        label,
        {domain: round(value) for domain, value in domains.items()},
        history["entry_date"].min().date(),
        reference_date.date(),
    )


def bmi_status(bmi: float | None) -> tuple[str, str, str] | None:
    """Return the standard adult BMI band, tone and short context."""
    if bmi is None:
        return None
    if bmi < 18.5:
        return "Underweight", "attention", "Below the standard healthy adult range"
    if bmi < 25:
        return "Healthy range", "strong", "Within the standard healthy adult range"
    if bmi < 30:
        return "Overweight", "watch", "Above the standard healthy adult range"
    if bmi < 40:
        return "Obesity", "attention", "Within the standard obesity range"
    return "Severe obesity", "attention", "Within the standard severe-obesity range"


def weekly_coaching_summary(
    df: pd.DataFrame, end_date: date | None = None, profile: Profile = PROFILE
) -> dict:
    end_date = end_date or date.today()
    if df.empty:
        return {"logged_days": 0, "completion": 0, "recommendation": "Log the first day."}
    data = df.copy()
    data["entry_date"] = pd.to_datetime(data["entry_date"])
    end = pd.Timestamp(end_date)
    six_days = pd.Timedelta(6, unit="D")
    thirteen_days = pd.Timedelta(13, unit="D")
    current = data[(data.entry_date >= end - six_days) & (data.entry_date <= end)]
    previous = data[(data.entry_date >= end - thirteen_days) & (data.entry_date < end - six_days)]
    logged_days = int(current.entry_date.dt.date.nunique())
    weights = current.weight_kg.dropna() if "weight_kg" in current else pd.Series(dtype=float)
    previous_weights = (
        previous.weight_kg.dropna() if "weight_kg" in previous else pd.Series(dtype=float)
    )
    weight_change = (
        float(weights.mean() - previous_weights.mean())
        if not weights.empty and not previous_weights.empty
        else None
    )
    averages = {}
    for field in ("calories", "protein_g", "fibre_g", "steps", "sleep_hours"):
        if field in current and current[field].notna().any():
            averages[field] = float(current[field].mean())
    habits = {
        field: int(current[field].fillna(False).sum())
        for field in ("gym", "cardio", "alcohol_free")
        if field in current
    }
    recent_weights = (
        data.dropna(subset=["weight_kg"]).tail(28)
        if "weight_kg" in data
        else pd.DataFrame()
    )
    plateau = False
    if len(recent_weights) >= 14:
        midpoint = len(recent_weights) // 2
        plateau = (
            abs(
                recent_weights.iloc[midpoint:].weight_kg.mean()
                - recent_weights.iloc[:midpoint].weight_kg.mean()
            )
            < 0.4
        )
    recommendation = "Protect logging consistency: aim for at least 5 complete days."
    if logged_days >= 5:
        if averages.get("protein_g", 10**9) < profile.target_weight_kg * 1.5:
            recommendation = "Prioritise a clear protein source at each main meal."
        elif averages.get("steps", 10**9) < 7000:
            recommendation = "Raise the daily movement floor with one planned walk."
        elif averages.get("sleep_hours", 10**9) < 7:
            recommendation = "Protect a consistent sleep window before changing calories."
        else:
            recommendation = "Keep the current routine repeatable for another week."
    if plateau and logged_days >= 5:
        recommendation = "Review portions, weekends and activity before adjusting calorie targets."
    start_weight = profile.start_weight_kg
    latest_weight = (
        float(data.weight_kg.dropna().iloc[-1])
        if "weight_kg" in data and data.weight_kg.notna().any()
        else None
    )
    loss_percent = ((start_weight - latest_weight) / start_weight * 100) if latest_weight else 0
    milestone = max((level for level in (5, 10, 15, 20) if loss_percent >= level), default=0)
    return {
        "logged_days": logged_days,
        "completion": round(logged_days / 7 * 100),
        "weight_change": weight_change,
        "averages": averages,
        "habits": habits,
        "plateau": plateau,
        "recommendation": recommendation,
        "loss_percent": loss_percent,
        "milestone": milestone,
    }


def weight_milestones(start_date: date, profile: Profile = PROFILE) -> tuple[list[dict], float]:
    """Return fixed plan milestones using a gradual 0.5–1.0 kg weekly pace."""
    target_date = profile.target_date
    total_weeks = max((target_date - start_date).days / 7, 1)
    required_pace = (profile.start_weight_kg - profile.target_weight_kg) / total_weeks
    weekly_pace = min(1.0, max(0.5, required_pace))
    milestones = []
    for months in (1, 3, 6, 9):
        milestone_date = (pd.Timestamp(start_date) + pd.DateOffset(months=months)).date()
        elapsed_weeks = max(0, (milestone_date - start_date).days / 7)
        weight = max(
            profile.target_weight_kg,
            profile.start_weight_kg - weekly_pace * elapsed_weeks,
        )
        milestones.append(
            {
                "milestone_date": milestone_date,
                "weight_kg": round(weight, 1),
                "label": f"{months} month" if months == 1 else f"{months} months",
            }
        )
    return milestones, weekly_pace


def current_streak(df: pd.DataFrame) -> int:
    if df.empty or "entry_date" not in df:
        return 0
    dates = {pd.Timestamp(value).date() for value in df["entry_date"].dropna()}
    cursor = date.today()
    if cursor not in dates:
        cursor -= timedelta(days=1)
    streak = 0
    while cursor in dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def projected_target_date(df: pd.DataFrame, profile: Profile = PROFILE) -> date | None:
    if df.empty or "weight_kg" not in df or df["weight_kg"].dropna().shape[0] < 2:
        return None
    weights = df[["entry_date", "weight_kg"]].dropna().tail(28).copy()
    weights["day"] = (
        pd.to_datetime(weights.entry_date) - pd.to_datetime(weights.entry_date).min()
    ).dt.days
    slope = weights["day"].cov(weights["weight_kg"]) / weights["day"].var()
    if pd.isna(slope) or slope >= 0:
        return None
    remaining = (profile.target_weight_kg - weights.iloc[-1].weight_kg) / slope
    return pd.Timestamp(weights.iloc[-1].entry_date).date() + timedelta(days=max(0, int(remaining)))
