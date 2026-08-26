from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from health_tracker.config import PROFILE, Profile
from health_tracker.db import engine
from health_tracker.models import DailyEntry, NutritionLog


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
    bmi = getattr(item, "bmi", None)
    if bmi:
        components.append(
            ("BMI", 100 if 18.5 <= bmi < 25 else 65 if 25 <= bmi < 30 else 35 if bmi < 35 else 15)
        )
    waist = getattr(item, "waist_cm", None)
    if waist:
        ratio = waist / profile.height_cm
        components.append(("Waist-to-height", 100 if ratio < 0.5 else 55 if ratio < 0.6 else 20))
    systolic = getattr(item, "systolic", None)
    diastolic = getattr(item, "diastolic", None)
    if systolic and diastolic:
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
    resting_hr = getattr(item, "resting_heart_rate", None)
    if resting_hr is not None:
        components.append(
            (
                "Resting heart rate",
                100 if 50 <= resting_hr <= 90 else 65 if 40 <= resting_hr <= 100 else 25,
            )
        )
    sleep = getattr(item, "sleep_hours", None)
    if sleep is not None:
        components.append(("Sleep", 100 if 7 <= sleep <= 9 else 65 if 6 <= sleep <= 10 else 30))
    steps = getattr(item, "steps", None)
    if steps is not None:
        components.append(("Activity", 100 if steps >= 8000 else 70 if steps >= 5000 else 40))
    for field, label in (("mood", "Mood"), ("energy", "Energy")):
        rating = getattr(item, field, None)
        if rating is not None:
            components.append((label, rating * 10))
    if not components:
        return None
    score = round(sum(value for _, value in components) / len(components))
    label = "Strong" if score >= 75 else "Watch" if score >= 45 else "Needs attention"
    return score, label, [name for name, _ in components]


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
