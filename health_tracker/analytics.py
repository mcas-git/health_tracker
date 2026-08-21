from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from health_tracker.config import PROFILE
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


def projected_target_date(df: pd.DataFrame) -> date | None:
    if df.empty or "weight_kg" not in df or df["weight_kg"].dropna().shape[0] < 2:
        return None
    weights = df[["entry_date", "weight_kg"]].dropna().tail(28).copy()
    weights["day"] = (
        pd.to_datetime(weights.entry_date) - pd.to_datetime(weights.entry_date).min()
    ).dt.days
    slope = weights["day"].cov(weights["weight_kg"]) / weights["day"].var()
    if pd.isna(slope) or slope >= 0:
        return None
    remaining = (PROFILE.target_weight_kg - weights.iloc[-1].weight_kg) / slope
    return pd.Timestamp(weights.iloc[-1].entry_date).date() + timedelta(days=max(0, int(remaining)))
