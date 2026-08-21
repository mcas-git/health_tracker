from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from health_tracker.analytics import current_streak, daily_health_score, excel_safe_data
from health_tracker.auth import create_remember_token, hash_password, valid_remember_token
from health_tracker.config import PROFILE
from health_tracker.db import calculate_targets
from health_tracker.nutrition import DailyNutritionEstimate
from health_tracker.quotes import QUOTES, quote_count
from health_tracker.theme import normalize_color
from scripts.send_reminder import reminder_copy, should_send


def test_profile_target_date_is_uk_interpretation():
    assert PROFILE.target_date == date(2027, 9, 1)


def test_target_calculation_is_sensible():
    targets = calculate_targets()
    assert 1500 <= targets["calories"] <= 3000
    assert targets["protein"] >= 100
    assert targets["carbs"] >= 50


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
