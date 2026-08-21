from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from health_tracker.analytics import current_streak
from health_tracker.auth import hash_password
from health_tracker.config import PROFILE
from health_tracker.db import calculate_targets
from health_tracker.nutrition import DailyNutritionEstimate
from health_tracker.quotes import QUOTES, quote_count
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
