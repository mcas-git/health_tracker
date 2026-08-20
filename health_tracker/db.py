from __future__ import annotations

from contextlib import contextmanager
from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from health_tracker.config import PROFILE, database_url
from health_tracker.models import Base, DailyEntry, GoalSettings, NutritionLog

engine = create_engine(database_url(), pool_pre_ping=True)


def calculate_targets(weight_kg: float = PROFILE.start_weight_kg) -> dict[str, int]:
    # Mifflin-St Jeor, sedentary baseline, moderate sustainable deficit.
    bmr = 10 * weight_kg + 6.25 * PROFILE.height_cm - 5 * PROFILE.age + 5
    calories = max(1500, round((bmr * 1.35 - 650) / 50) * 50)
    protein = round(PROFILE.target_weight_kg * 1.8)
    fat = round(PROFILE.target_weight_kg * 0.8)
    carbs = max(50, round((calories - protein * 4 - fat * 9) / 4))
    return {"calories": calories, "protein": protein, "carbs": carbs, "fat": fat}


def init_db() -> None:
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        if session.get(GoalSettings, 1) is None:
            targets = calculate_targets()
            session.add(
                GoalSettings(
                    id=1,
                    calorie_target=targets["calories"],
                    protein_target_g=targets["protein"],
                    carbs_target_g=targets["carbs"],
                    fat_target_g=targets["fat"],
                    fibre_target_g=30,
                )
            )
            session.commit()


@contextmanager
def session_scope():
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def upsert_daily(values: dict) -> DailyEntry:
    with session_scope() as session:
        item = session.scalar(
            select(DailyEntry).where(DailyEntry.entry_date == values["entry_date"])
        )
        if item is None:
            item = DailyEntry(entry_date=values["entry_date"])
            session.add(item)
        for key, value in values.items():
            setattr(item, key, value)
        session.flush()
        session.refresh(item)
        return item


def get_daily(entry_date: date) -> DailyEntry | None:
    with Session(engine) as session:
        return session.scalar(select(DailyEntry).where(DailyEntry.entry_date == entry_date))


def get_nutrition(entry_date: date) -> NutritionLog | None:
    with Session(engine) as session:
        return session.scalar(select(NutritionLog).where(NutritionLog.entry_date == entry_date))
