from __future__ import annotations

from contextlib import contextmanager
from datetime import date

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from health_tracker.config import PROFILE, database_url
from health_tracker.models import (
    AppPreferences,
    Base,
    DailyEntry,
    GoalSettings,
    NutritionLog,
    WeeklyPlan,
)

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
    existing_columns = {column["name"] for column in inspect(engine).get_columns("daily_entries")}
    with engine.begin() as connection:
        column_types = {
            "morning_submitted": "BOOLEAN NOT NULL DEFAULT FALSE",
            "evening_submitted": "BOOLEAN NOT NULL DEFAULT FALSE",
            "physio": "BOOLEAN NOT NULL DEFAULT FALSE",
            "drugs": "BOOLEAN NOT NULL DEFAULT FALSE",
            "protein_powder": "BOOLEAN NOT NULL DEFAULT FALSE",
            "hunger": "INTEGER",
            "cravings": "INTEGER",
            "diet_satisfaction": "INTEGER",
            "illness": "BOOLEAN NOT NULL DEFAULT FALSE",
            "injury": "BOOLEAN NOT NULL DEFAULT FALSE",
            "travel": "BOOLEAN NOT NULL DEFAULT FALSE",
            "unusual_day": "BOOLEAN NOT NULL DEFAULT FALSE",
            "holiday": "BOOLEAN NOT NULL DEFAULT FALSE",
        }
        for column, sql_type in column_types.items():
            if column not in existing_columns:
                connection.execute(
                    text(f"ALTER TABLE daily_entries ADD COLUMN {column} {sql_type}")
                )
    preference_columns = {
        column["name"] for column in inspect(engine).get_columns("app_preferences")
    }
    preference_column_types = {
        "smooth_charts": "BOOLEAN NOT NULL DEFAULT TRUE",
        "success_matches_accent": "BOOLEAN NOT NULL DEFAULT FALSE",
        "show_placeholders": "BOOLEAN NOT NULL DEFAULT TRUE",
        "show_palette_preview": "BOOLEAN NOT NULL DEFAULT TRUE",
        "show_page_toggles": "BOOLEAN NOT NULL DEFAULT TRUE",
        "background_color": "VARCHAR(20)",
        "surface_color": "VARCHAR(20)",
        "text_color": "VARCHAR(20)",
        "muted_color": "VARCHAR(20)",
        "link_color": "VARCHAR(20)",
        "border_color": "VARCHAR(20)",
        "age": "INTEGER NOT NULL DEFAULT 39",
        "sex": "VARCHAR(20) NOT NULL DEFAULT 'male'",
        "height_cm": "FLOAT NOT NULL DEFAULT 177.0",
        "start_weight_kg": "FLOAT NOT NULL DEFAULT 105.0",
        "target_weight_kg": "FLOAT NOT NULL DEFAULT 77.0",
        "target_date": "DATE NOT NULL DEFAULT '2027-09-01'",
    }
    with engine.begin() as connection:
        for column, sql_type in preference_column_types.items():
            if column not in preference_columns:
                connection.execute(
                    text(f"ALTER TABLE app_preferences ADD COLUMN {column} {sql_type}")
                )
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
        if session.get(AppPreferences, 1) is None:
            session.add(AppPreferences(id=1))
            session.commit()
        elif session.get(AppPreferences, 1).color_mode != "dark":
            session.get(AppPreferences, 1).color_mode = "dark"
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


def get_latest_daily_before(entry_date: date) -> DailyEntry | None:
    with Session(engine) as session:
        return session.scalar(
            select(DailyEntry)
            .where(DailyEntry.entry_date < entry_date)
            .order_by(DailyEntry.entry_date.desc())
            .limit(1)
        )


def get_nutrition(entry_date: date) -> NutritionLog | None:
    with Session(engine) as session:
        return session.scalar(select(NutritionLog).where(NutritionLog.entry_date == entry_date))


def get_weekly_plan(week_start: date) -> WeeklyPlan | None:
    with Session(engine) as session:
        return session.scalar(select(WeeklyPlan).where(WeeklyPlan.week_start == week_start))


def upsert_weekly_plan(values: dict) -> WeeklyPlan:
    with session_scope() as session:
        item = session.scalar(
            select(WeeklyPlan).where(WeeklyPlan.week_start == values["week_start"])
        )
        if item is None:
            item = WeeklyPlan(week_start=values["week_start"])
            session.add(item)
        for key, value in values.items():
            setattr(item, key, value)
        session.flush()
        session.refresh(item)
        return item
