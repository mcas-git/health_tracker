from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DailyEntry(Base):
    __tablename__ = "daily_entries"
    __table_args__ = (UniqueConstraint("entry_date", name="uq_daily_entry_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    waist_cm: Mapped[float | None] = mapped_column(Float)
    bmi: Mapped[float | None] = mapped_column(Float)
    resting_heart_rate: Mapped[int | None] = mapped_column(Integer)
    systolic: Mapped[int | None] = mapped_column(Integer)
    diastolic: Mapped[int | None] = mapped_column(Integer)
    sleep_hours: Mapped[float | None] = mapped_column(Float)
    steps: Mapped[int | None] = mapped_column(Integer)
    mood: Mapped[int | None] = mapped_column(Integer)
    energy: Mapped[int | None] = mapped_column(Integer)
    hunger: Mapped[int | None] = mapped_column(Integer)
    cravings: Mapped[int | None] = mapped_column(Integer)
    diet_satisfaction: Mapped[int | None] = mapped_column(Integer)
    calories_burned: Mapped[int | None] = mapped_column(Integer)
    gym: Mapped[bool] = mapped_column(Boolean, default=False)
    cardio: Mapped[bool] = mapped_column(Boolean, default=False)
    erg: Mapped[bool] = mapped_column(Boolean, default=False)
    supplements: Mapped[bool] = mapped_column(Boolean, default=False)
    protein_powder: Mapped[bool] = mapped_column(Boolean, default=False)
    alcohol_free: Mapped[bool] = mapped_column(Boolean, default=False)
    sufficient_water: Mapped[bool] = mapped_column(Boolean, default=False)
    physio: Mapped[bool] = mapped_column(Boolean, default=False)
    drugs: Mapped[bool] = mapped_column(Boolean, default=False)
    sleep_target: Mapped[bool] = mapped_column(Boolean, default=False)
    illness: Mapped[bool] = mapped_column(Boolean, default=False)
    injury: Mapped[bool] = mapped_column(Boolean, default=False)
    travel: Mapped[bool] = mapped_column(Boolean, default=False)
    unusual_day: Mapped[bool] = mapped_column(Boolean, default=False)
    fasted: Mapped[bool] = mapped_column(Boolean, default=False)
    fast_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fast_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fasting_hours: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class NutritionLog(Base):
    __tablename__ = "nutrition_logs"
    __table_args__ = (UniqueConstraint("entry_date", name="uq_nutrition_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    raw_note: Mapped[str] = mapped_column(Text)
    meals_json: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="")
    calories: Mapped[int] = mapped_column(Integer)
    protein_g: Mapped[float] = mapped_column(Float)
    carbs_g: Mapped[float] = mapped_column(Float)
    fat_g: Mapped[float] = mapped_column(Float)
    fibre_g: Mapped[float] = mapped_column(Float)
    confidence: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class GoalSettings(Base):
    __tablename__ = "goal_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    calorie_target: Mapped[int] = mapped_column(Integer)
    protein_target_g: Mapped[int] = mapped_column(Integer)
    carbs_target_g: Mapped[int] = mapped_column(Integer)
    fat_target_g: Mapped[int] = mapped_column(Integer)
    fibre_target_g: Mapped[int] = mapped_column(Integer, default=30)
    fasting_target_hours: Mapped[float] = mapped_column(Float, default=16)
    sleep_target_hours: Mapped[float] = mapped_column(Float, default=8)
    water_target_litres: Mapped[float] = mapped_column(Float, default=2.5)


class AppPreferences(Base):
    __tablename__ = "app_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    color_mode: Mapped[str] = mapped_column(String(20), default="dark")
    accent: Mapped[str] = mapped_column(String(20), default="#7B8451")
    font_family: Mapped[str] = mapped_column(String(40), default="Modern sans")
    smooth_charts: Mapped[bool] = mapped_column(Boolean, default=True)
    success_matches_accent: Mapped[bool] = mapped_column(Boolean, default=False)
    age: Mapped[int] = mapped_column(Integer, default=39)
    sex: Mapped[str] = mapped_column(String(20), default="male")
    height_cm: Mapped[float] = mapped_column(Float, default=177.0)
    start_weight_kg: Mapped[float] = mapped_column(Float, default=105.0)
    target_weight_kg: Mapped[float] = mapped_column(Float, default=77.0)
    target_date: Mapped[date] = mapped_column(Date, default=date(2027, 9, 1))


class WeeklyPlan(Base):
    __tablename__ = "weekly_plans"
    __table_args__ = (UniqueConstraint("week_start", name="uq_weekly_plan_start"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_start: Mapped[date] = mapped_column(Date, index=True)
    focus: Mapped[str] = mapped_column(String(200), default="")
    planned_gym_sessions: Mapped[int] = mapped_column(Integer, default=3)
    planned_cardio_sessions: Mapped[int] = mapped_column(Integer, default=2)
    minimum_steps: Mapped[int] = mapped_column(Integer, default=7000)
    anticipated_barrier: Mapped[str] = mapped_column(Text, default="")
    if_then_plan: Mapped[str] = mapped_column(Text, default="")
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
