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
    TargetAdjustment,
    WeeklyPlan,
)

engine = create_engine(database_url(), pool_pre_ping=True)

SCHEMA_COLUMN_MIGRATIONS = {
    "daily_entries": {
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
    },
    "app_preferences": {
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
    },
    "nutrition_logs": {
        "logging_status": "VARCHAR(20) NOT NULL DEFAULT 'complete'",
    },
}


def calculate_targets(weight_kg: float = PROFILE.start_weight_kg) -> dict[str, int]:
    # Mifflin-St Jeor, sedentary baseline, moderate sustainable deficit.
    bmr = 10 * weight_kg + 6.25 * PROFILE.height_cm - 5 * PROFILE.age + 5
    calories = max(1500, round((bmr * 1.35 - 650) / 50) * 50)
    protein = round(PROFILE.target_weight_kg * 1.8)
    fat = round(PROFILE.target_weight_kg * 0.8)
    carbs = max(50, round((calories - protein * 4 - fat * 9) / 4))
    return {"calories": calories, "protein": protein, "carbs": carbs, "fat": fat}


def _apply_column_migrations() -> None:
    """Apply the small, additive migrations supported by this single-user app."""
    schema = inspect(engine)
    with engine.begin() as connection:
        for table_name, required_columns in SCHEMA_COLUMN_MIGRATIONS.items():
            existing_columns = {column["name"] for column in schema.get_columns(table_name)}
            for column_name, sql_type in required_columns.items():
                if column_name not in existing_columns:
                    connection.execute(
                        text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {sql_type}")
                    )


def init_db() -> None:
    Base.metadata.create_all(engine)
    _apply_column_migrations()
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
        preferences = session.get(AppPreferences, 1)
        if preferences is None:
            session.add(AppPreferences(id=1))
        session.commit()


@contextmanager
def session_scope():
    # Several helpers return newly saved ORM objects. Keeping loaded attributes
    # available after commit prevents surprising DetachedInstanceError failures.
    session = Session(engine, expire_on_commit=False)
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


def get_target_adjustment(week_start: date) -> TargetAdjustment | None:
    with Session(engine) as session:
        return session.scalar(
            select(TargetAdjustment).where(TargetAdjustment.week_start == week_start)
        )


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


def apply_target_adjustment(
    *,
    week_start: date,
    recommended_calories: int,
    actual_weekly_loss_kg: float,
    target_weekly_loss_kg: float,
    usable_nutrition_days: int,
    weight_measurements: int,
) -> TargetAdjustment:
    """Apply one reviewed calorie adjustment per week and retain an audit record."""
    with session_scope() as session:
        existing = session.scalar(
            select(TargetAdjustment).where(TargetAdjustment.week_start == week_start)
        )
        if existing is not None:
            return existing
        goals = session.get(GoalSettings, 1)
        if goals is None:
            raise RuntimeError("Daily targets have not been initialised.")
        previous_calories = goals.calorie_target
        previous_carbs = goals.carbs_target_g
        calorie_change = recommended_calories - previous_calories
        new_carbs = max(20, previous_carbs + round(calorie_change / 4))
        goals.calorie_target = recommended_calories
        goals.carbs_target_g = new_carbs
        adjustment = TargetAdjustment(
            week_start=week_start,
            previous_calorie_target=previous_calories,
            new_calorie_target=recommended_calories,
            previous_carbs_target_g=previous_carbs,
            new_carbs_target_g=new_carbs,
            actual_weekly_loss_kg=actual_weekly_loss_kg,
            target_weekly_loss_kg=target_weekly_loss_kg,
            usable_nutrition_days=usable_nutrition_days,
            weight_measurements=weight_measurements,
        )
        session.add(adjustment)
        session.flush()
        session.refresh(adjustment)
        return adjustment
