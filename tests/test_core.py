from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from health_tracker import db, garmin
from health_tracker.analytics import (
    bmi_status,
    current_streak,
    daily_health_score,
    excel_safe_data,
    weekly_coaching_summary,
    weight_milestones,
)
from health_tracker.auth import create_remember_token, hash_password, valid_remember_token
from health_tracker.config import PROFILE
from health_tracker.db import calculate_targets
from health_tracker.models import Base, DailyEntry
from health_tracker.nutrition import DailyNutritionEstimate
from health_tracker.quotes import QUOTES, daily_item, quote_count
from health_tracker.research import RESEARCH_INSIGHTS
from health_tracker.theme import normalize_color
from scripts.send_reminder import reminder_copy, should_send
from scripts.send_weekly_report import build_weekly_message, should_send_weekly


def test_profile_target_date_is_uk_interpretation():
    assert PROFILE.target_date == date(2027, 9, 1)


def test_target_calculation_is_sensible():
    targets = calculate_targets()
    assert 1500 <= targets["calories"] <= 3000
    assert targets["protein"] >= 100
    assert targets["carbs"] >= 50


def test_latest_daily_before_uses_most_recent_earlier_entry(monkeypatch):
    test_engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(test_engine)
    daily_columns = {column["name"] for column in inspect(test_engine).get_columns("daily_entries")}
    assert "travel" in daily_columns
    preference_columns = {
        column["name"] for column in inspect(test_engine).get_columns("app_preferences")
    }
    assert {
        "age",
        "sex",
        "height_cm",
        "start_weight_kg",
        "target_weight_kg",
        "target_date",
        "success_matches_accent",
    } <= preference_columns
    with Session(test_engine) as session:
        session.add_all(
            [
                DailyEntry(entry_date=date(2026, 8, 20), weight_kg=101.5),
                DailyEntry(entry_date=date(2026, 8, 22), weight_kg=100.8),
                DailyEntry(entry_date=date(2026, 8, 25), weight_kg=100.1),
            ]
        )
        session.commit()
    monkeypatch.setattr(db, "engine", test_engine)

    latest = db.get_latest_daily_before(date(2026, 8, 24))

    assert latest is not None
    assert latest.entry_date == date(2026, 8, 22)
    assert latest.weight_kg == 100.8


def test_garmin_sync_uses_selected_date_for_stats_and_overnight_sleep(monkeypatch):
    calls = []

    class FakeGarmin:
        def __init__(self, email, password):
            pass

        def login(self):
            pass

        def get_stats(self, day):
            calls.append(("stats", day))
            return {"totalSteps": 8000, "totalKilocalories": 2200}

        def get_sleep_data(self, day):
            calls.append(("sleep", day))
            return {"dailySleepDTO": {"sleepTimeSeconds": 27000}}

        def get_heart_rates(self, day):
            calls.append(("heart_rate", day))
            return {"restingHeartRate": 55}

        def get_activities_by_date(self, start, end):
            calls.append(("activities", start, end))
            return []

    monkeypatch.setattr(garmin, "Garmin", FakeGarmin)
    monkeypatch.setattr(garmin, "setting", lambda name: f"test-{name.lower()}")

    result = garmin.sync_day(date(2026, 8, 25))

    assert calls == [
        ("stats", "2026-08-25"),
        ("sleep", "2026-08-25"),
        ("heart_rate", "2026-08-25"),
        ("activities", "2026-08-25", "2026-08-25"),
    ]
    assert result["sleep_hours"] == 7.5


def test_password_hash_is_deterministic_and_not_plaintext():
    assert hash_password("secret") == hash_password("secret")
    assert hash_password("secret") != "secret"


def test_remember_token_is_signed_and_bound_to_current_password():
    current_hash = hash_password("current")
    token = create_remember_token(current_hash)
    assert valid_remember_token(token, current_hash)
    assert not valid_remember_token(token, hash_password("changed"))
    assert not valid_remember_token(f"{token}x", current_hash)


def test_nutrition_schema_parses():
    estimate = DailyNutritionEstimate.model_validate(
        {
            "meals": [
                {
                    "label": "Lunch",
                    "foods": ["soup"],
                    "calories": 200,
                    "protein_g": 10,
                    "carbs_g": 30,
                    "fat_g": 4,
                    "fibre_g": 5,
                }
            ],
            "summary": "Typical bowl assumed",
            "calories": 200,
            "protein_g": 10,
            "carbs_g": 30,
            "fat_g": 4,
            "fibre_g": 5,
            "confidence": "medium",
        }
    )
    assert estimate.calories == 200


def test_streak_uses_yesterday_if_today_missing():
    today = date.today()
    df = pd.DataFrame({"entry_date": [today - timedelta(days=2), today - timedelta(days=1)]})
    assert current_streak(df) == 2


def test_excel_export_removes_timezone_information():
    aware = datetime(2026, 8, 21, 12, tzinfo=ZoneInfo("Europe/London"))
    data = pd.DataFrame({"created_at": [aware], "value": [1]})

    exported = excel_safe_data(data)

    assert exported.loc[0, "created_at"].tzinfo is None


def test_daily_health_score_is_deterministic_and_uses_available_measurements():
    item = type(
        "Entry",
        (),
        {
            "bmi": 24,
            "waist_cm": 80,
            "systolic": 120,
            "diastolic": 80,
            "sleep_hours": 8,
            "steps": 9000,
            "mood": 8,
            "energy": 7,
        },
    )()
    score, label, included = daily_health_score(item)
    assert score == 93
    assert label == "Strong"
    assert len(included) == 7


def test_bmi_status_uses_standard_adult_bands():
    assert bmi_status(24.9)[0] == "Healthy range"
    assert bmi_status(25.0)[0] == "Overweight"
    assert bmi_status(30.0)[0] == "Obesity"


def test_pandas_measurement_row_supports_health_indicators():
    item = pd.Series({"bmi": 31.2, "waist_cm": 101.0, "mood": 7, "energy": 6})
    assert bmi_status(item.bmi)[0] == "Obesity"
    assert daily_health_score(item) is not None


def test_palette_colour_accepts_hex_and_rgb():
    assert normalize_color("#7b8451") == "#7B8451"
    assert normalize_color("rgb(123, 132, 81)") == "#7B8451"


def test_reminder_schedule_handles_bst_and_gmt():
    london = ZoneInfo("Europe/London")
    assert should_send(datetime(2026, 7, 1, 5, tzinfo=london), "schedule")
    assert should_send(datetime(2026, 12, 1, 21, tzinfo=london), "schedule")
    assert not should_send(datetime(2026, 7, 1, 6, tzinfo=london), "schedule")
    assert should_send(datetime(2026, 7, 1, 6, tzinfo=london), "workflow_dispatch")


def test_morning_and_evening_reminders_are_distinct():
    london = ZoneInfo("Europe/London")
    morning = reminder_copy(datetime(2026, 7, 1, 5, tzinfo=london))
    evening = reminder_copy(datetime(2026, 7, 1, 21, tzinfo=london))
    assert morning != evening
    assert "intention" in morning[2]
    assert "food note" in evening[2]


def test_motivational_library_has_60_unique_short_entries():
    assert quote_count() == 60
    assert len(set(QUOTES)) == 60
    assert max(map(len, QUOTES)) < 100


def test_daily_quote_is_stable_for_the_day():
    day = date(2026, 8, 21)
    assert daily_item(QUOTES, day) == daily_item(QUOTES, day)


def test_every_research_note_has_a_source_and_motivation():
    assert all(item["insight"] and item["source"] and item["url"] for item in RESEARCH_INSIGHTS)
    assert all(item["motivation"] for item in RESEARCH_INSIGHTS)


def test_research_note_rotates_with_calendar_day():
    start = date(2026, 8, 21)
    daily_notes = [
        daily_item(RESEARCH_INSIGHTS, start + timedelta(days=offset)) for offset in range(7)
    ]
    assert all(daily_notes[index] != daily_notes[index + 1] for index in range(6))


def test_weekly_coaching_summary_reports_completion_and_trends():
    end = date(2026, 8, 21)
    rows = []
    for offset in range(14):
        rows.append(
            {
                "entry_date": end - timedelta(days=13 - offset),
                "weight_kg": 100 - offset * 0.1,
                "protein_g": 170,
                "steps": 8000,
                "sleep_hours": 7.5,
                "gym": offset % 3 == 0,
                "cardio": False,
                "alcohol_free": True,
            }
        )

    summary = weekly_coaching_summary(pd.DataFrame(rows), end)

    assert summary["logged_days"] == 7
    assert summary["completion"] == 100
    assert summary["weight_change"] < 0
    assert summary["habits"]["alcohol_free"] == 7


def test_weight_milestones_follow_a_sustainable_plan_pace():
    milestones, pace = weight_milestones(date(2026, 8, 23))

    assert [item["label"] for item in milestones] == [
        "1 month",
        "3 months",
        "6 months",
        "9 months",
    ]
    assert 0.5 <= pace <= 1.0
    assert all(
        left["weight_kg"] > right["weight_kg"]
        for left, right in zip(milestones, milestones[1:], strict=False)
    )


def test_weekly_report_schedule_handles_daylight_saving():
    london = ZoneInfo("Europe/London")
    assert should_send_weekly(datetime(2026, 7, 5, 19, tzinfo=london), "schedule")
    assert not should_send_weekly(datetime(2026, 7, 5, 18, tzinfo=london), "schedule")
    assert should_send_weekly(datetime(2026, 7, 5, 18, tzinfo=london), "workflow_dispatch")


def test_weekly_report_contains_summary(monkeypatch):
    monkeypatch.setenv("REMINDER_FROM", "sender@example.com")
    monkeypatch.setenv("REMINDER_TO", "receiver@example.com")
    monkeypatch.setenv("APP_URL", "https://example.streamlit.app")
    summary = {
        "completion": 86,
        "logged_days": 6,
        "weight_change": -0.4,
        "loss_percent": 5.2,
        "recommendation": "Keep the current routine repeatable for another week.",
    }

    message = build_weekly_message(datetime(2026, 8, 23), summary)

    assert "86% logged" in message["Subject"]
    assert "-0.4 kg" in message.get_body(preferencelist=("plain",)).get_content()
    assert (
        "https://example.streamlit.app" in message.get_body(preferencelist=("html",)).get_content()
    )
