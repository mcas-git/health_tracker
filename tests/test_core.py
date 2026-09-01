from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from health_tracker import analytics, db, garmin
from health_tracker.analytics import (
    bmi_status,
    current_streak,
    daily_health_score,
    evening_checkin_complete,
    evening_measurement_status,
    excel_safe_data,
    health_journey_score,
    morning_checkin_complete,
    morning_measurement_status,
    nutrition_period_bounds,
    recent_kpi_table,
    weekly_coaching_summary,
    weight_milestones,
)
from health_tracker.auth import (
    create_remember_token,
    email_is_allowed,
    hash_password,
    valid_remember_token,
)
from health_tracker.config import PROFILE
from health_tracker.db import calculate_targets
from health_tracker.models import AppPreferences, Base, DailyEntry, NutritionLog
from health_tracker.nutrition import DailyNutritionEstimate, quality_assure_estimate
from health_tracker.quotes import QUOTES, daily_item, quote_count, weekly_item
from health_tracker.research import RESEARCH_INSIGHTS
from health_tracker.theme import derived_palette, normalize_color
from scripts.send_reminder import evening_reminder_needed, reminder_copy, should_send
from scripts.send_weekly_report import build_weekly_message, should_send_weekly


def test_morning_measurement_status_marks_unrecorded_values_as_missing():
    item = type(
        "Entry",
        (),
        {"weight_kg": 101.2, "waist_cm": None, "systolic": None, "diastolic": None},
    )()

    assert morning_measurement_status(item) == {
        "Weight": "101.2 kg",
        "Waist": "Missing",
        "Blood pressure": "Missing",
    }


def test_evening_measurement_status_marks_unrecorded_values_as_missing():
    item = type(
        "Entry",
        (),
        {
            "resting_heart_rate": 52,
            "sleep_hours": 7.5,
            "steps": 4551,
            "calories_burned": None,
            "mood": 7,
            "energy": None,
            "cravings": None,
            "diet_satisfaction": 8,
        },
    )()

    assert evening_measurement_status(item) == {
        "Resting heart rate": "52 bpm",
        "Sleep": "7.50 h",
        "Steps": "4,551",
        "Calories burned": "Missing",
        "Mood": "7/10",
        "Energy": "Missing",
        "Cravings": "Missing",
        "Diet satisfaction": "8/10",
    }


def test_checkin_completion_requires_every_measurement():
    values = {
        "weight_kg": 101.2,
        "waist_cm": 108.0,
        "systolic": 118,
        "diastolic": 78,
        "resting_heart_rate": 54,
        "sleep_hours": 7.5,
        "steps": 8000,
        "calories_burned": 2400,
        "mood": 7,
        "energy": 8,
        "cravings": 3,
        "diet_satisfaction": 8,
    }
    complete = SimpleNamespace(**values)
    no_waist = SimpleNamespace(**{**values, "waist_cm": None})
    missing_pressure = SimpleNamespace(**{**values, "systolic": None})
    submitted_missing = SimpleNamespace(
        morning_submitted=True,
        weight_kg=None,
        systolic=None,
        diastolic=None,
    )
    missing_energy = SimpleNamespace(**{**values, "energy": None})
    zero_ratings = SimpleNamespace(
        **{**values, "mood": 0, "energy": 0, "cravings": 0, "diet_satisfaction": 0}
    )
    submitted_evening_missing = SimpleNamespace(evening_submitted=True)

    assert morning_checkin_complete(complete)
    assert morning_checkin_complete(no_waist)
    assert morning_checkin_complete(submitted_missing)
    assert evening_checkin_complete(complete)
    assert evening_checkin_complete(zero_ratings)
    assert evening_checkin_complete(submitted_evening_missing)
    assert not morning_checkin_complete(missing_pressure)
    assert not evening_checkin_complete(missing_energy)


def test_nan_submission_flags_do_not_mark_partial_checkins_complete():
    partial_morning = pd.Series({"morning_submitted": float("nan"), "weight_kg": 101.2})
    partial_evening = pd.Series({"evening_submitted": float("nan"), "mood": 7, "energy": 8})

    assert not morning_checkin_complete(partial_morning)
    assert not evening_checkin_complete(partial_evening)


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
    assert "morning_submitted" in daily_columns
    assert "evening_submitted" in daily_columns
    assert "holiday" in daily_columns
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
        "show_placeholders",
        "show_palette_preview",
        "show_page_toggles",
        "background_color",
        "surface_color",
        "text_color",
        "muted_color",
        "link_color",
        "border_color",
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


def test_saved_entry_remains_readable_after_commit(monkeypatch):
    test_engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(test_engine)
    monkeypatch.setattr(db, "engine", test_engine)

    saved = db.upsert_daily({"entry_date": date(2026, 8, 26), "weight_kg": 100.4})

    assert saved.entry_date == date(2026, 8, 26)
    assert saved.weight_kg == 100.4


def test_init_db_is_idempotent_and_preserves_saved_appearance(monkeypatch):
    test_engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        session.add(AppPreferences(id=1, color_mode="light"))
        session.commit()
    monkeypatch.setattr(db, "engine", test_engine)

    db.init_db()
    db.init_db()

    with Session(test_engine) as session:
        assert session.get(AppPreferences, 1).color_mode == "light"


def test_additive_migrations_upgrade_legacy_tables(monkeypatch):
    test_engine = create_engine("sqlite+pysqlite:///:memory:")
    with test_engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE daily_entries (id INTEGER PRIMARY KEY, entry_date DATE NOT NULL)")
        )
        connection.execute(
            text(
                "CREATE TABLE app_preferences "
                "(id INTEGER PRIMARY KEY, color_mode VARCHAR(20), "
                "accent VARCHAR(20), font_family VARCHAR(40))"
            )
        )
    monkeypatch.setattr(db, "engine", test_engine)

    db._apply_column_migrations()
    db._apply_column_migrations()

    schema = inspect(test_engine)
    daily_columns = {column["name"] for column in schema.get_columns("daily_entries")}
    preference_columns = {column["name"] for column in schema.get_columns("app_preferences")}
    assert set(db.SCHEMA_COLUMN_MIGRATIONS["daily_entries"]) <= daily_columns
    assert set(db.SCHEMA_COLUMN_MIGRATIONS["app_preferences"]) <= preference_columns


def test_load_data_keeps_daily_schema_when_only_nutrition_is_recorded(monkeypatch):
    test_engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        session.add(
            NutritionLog(
                entry_date=date(2026, 8, 25),
                raw_note="Porridge with berries",
                meals_json="[]",
                calories=450,
                protein_g=18,
                carbs_g=70,
                fat_g=10,
                fibre_g=9,
                confidence="medium",
                model="test",
            )
        )
        session.commit()
    monkeypatch.setattr(analytics, "engine", test_engine)

    data = analytics.load_data()

    assert "weight_kg" in data.columns
    assert data["weight_kg"].isna().all()
    assert data.loc[0, "calories"] == 450


def test_nutrition_period_bounds_use_latest_available_record_and_clip_short_history():
    dates = pd.Series(pd.to_datetime(["2026-08-25", "2026-08-27", "2026-08-29"]))

    week_start, week_end = nutrition_period_bounds(dates, date(2026, 8, 31), 7)
    month_start, month_end = nutrition_period_bounds(dates, date(2026, 8, 31), 30)

    assert week_start == pd.Timestamp("2026-08-25")
    assert week_end == pd.Timestamp("2026-08-29")
    assert month_start == pd.Timestamp("2026-08-25")
    assert month_end == pd.Timestamp("2026-08-29")


def test_nutrition_period_bounds_keep_full_rolling_window_when_history_exists():
    dates = pd.Series(pd.date_range("2026-07-01", "2026-08-29", freq="D"))

    period_start, period_end = nutrition_period_bounds(dates, date(2026, 8, 31), 30)

    assert period_start == pd.Timestamp("2026-07-31")
    assert period_end == pd.Timestamp("2026-08-29")


def test_garmin_sync_uses_selected_date_for_stats_and_overnight_sleep(monkeypatch):
    calls = []

    class FakeGarmin:
        def __init__(self, email, password):
            pass

        def login(self):
            pass

        def get_stats(self, day):
            calls.append(("stats", day))
            return {
                "calendarDate": day,
                "totalSteps": 8000,
                "totalKilocalories": 2200,
                "activeKilocalories": 500,
                "bmrKilocalories": 1700,
            }

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
    assert result["calories_burned"] == 2200
    assert result["active_calories"] == 500
    assert result["resting_calories"] == 1700
    assert result["source_date"] == "2026-08-25"


def test_garmin_sync_reconstructs_total_calories_without_discarding_zero(monkeypatch):
    class FakeGarmin:
        def __init__(self, email, password):
            pass

        def login(self):
            pass

        def get_stats(self, day):
            return {
                "totalSteps": 0,
                "activeKilocalories": 450,
                "bmrKilocalories": 1650,
                "restingHeartRate": 0,
            }

        def get_sleep_data(self, day):
            return {"dailySleepDTO": {"sleepTimeSeconds": 0}}

        def get_heart_rates(self, day):
            return {"restingHeartRate": 0}

        def get_activities_by_date(self, start, end):
            return []

    monkeypatch.setattr(garmin, "Garmin", FakeGarmin)
    monkeypatch.setattr(garmin, "setting", lambda name: f"test-{name.lower()}")

    result = garmin.sync_day(date(2026, 8, 25))

    assert result["calories_burned"] == 2100
    assert result["sleep_hours"] == 0
    assert result["resting_heart_rate"] == 0


def test_password_hash_is_deterministic_and_not_plaintext():
    assert hash_password("secret") == hash_password("secret")
    assert hash_password("secret") != "secret"


def test_remember_token_is_signed_and_bound_to_current_password():
    current_hash = hash_password("current")
    token = create_remember_token(current_hash)
    assert valid_remember_token(token, current_hash)
    assert not valid_remember_token(token, hash_password("changed"))
    assert not valid_remember_token(f"{token}x", current_hash)


def test_google_email_allowlist_is_exact_and_case_insensitive():
    configured = "owner@example.com, second@example.com"

    assert email_is_allowed("OWNER@example.com", configured)
    assert email_is_allowed("second@example.com", configured)
    assert not email_is_allowed("intruder@example.com", configured)
    assert not email_is_allowed("owner@example.com.evil.test", configured)


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


def test_nutrition_qa_reconciles_day_totals_from_meals():
    estimate = DailyNutritionEstimate.model_validate(
        {
            "meals": [
                {
                    "label": "Breakfast",
                    "foods": ["porridge"],
                    "calories": 320,
                    "protein_g": 14.24,
                    "carbs_g": 49.26,
                    "fat_g": 7.11,
                    "fibre_g": 6.04,
                },
                {
                    "label": "Lunch",
                    "foods": ["sandwich"],
                    "calories": 485,
                    "protein_g": 28.31,
                    "carbs_g": 55.18,
                    "fat_g": 16.07,
                    "fibre_g": 7.02,
                },
            ],
            "summary": "Typical UK portions assumed.",
            "calories": 999,
            "protein_g": 999,
            "carbs_g": 999,
            "fat_g": 999,
            "fibre_g": 999,
            "confidence": "medium",
        }
    )

    checked = quality_assure_estimate(estimate)

    assert checked.calories == 805
    assert checked.protein_g == 42.5
    assert checked.carbs_g == 104.4
    assert checked.fat_g == 23.2
    assert checked.fibre_g == 13.1


def test_uk_per_slice_label_reference_case():
    reference = DailyNutritionEstimate.model_validate(
        {
            "meals": [
                {
                    "label": "Lunch",
                    "foods": ["2 × 44 g slices of bread"],
                    "calories": 2 * 105,
                    "protein_g": 2 * 3.4,
                    "carbs_g": 2 * 20.0,
                    "fat_g": 2 * 0.7,
                    "fibre_g": 2 * 1.2,
                }
            ],
            "summary": "Used the stated UK per-slice label.",
            "calories": 210,
            "protein_g": 6.8,
            "carbs_g": 40.0,
            "fat_g": 1.4,
            "fibre_g": 2.4,
            "confidence": "high",
        }
    )

    checked = quality_assure_estimate(reference)

    nutrients = checked.model_dump(include={"calories", "protein_g", "carbs_g", "fat_g", "fibre_g"})
    assert nutrients == {
        "calories": 210,
        "protein_g": 6.8,
        "carbs_g": 40.0,
        "fat_g": 1.4,
        "fibre_g": 2.4,
    }


def test_uk_per_100g_label_reference_case():
    portion_grams = 400
    multiplier = portion_grams / 100
    reference = DailyNutritionEstimate.model_validate(
        {
            "meals": [
                {
                    "label": "Dinner",
                    "foods": ["400 g labelled ready meal"],
                    "calories": round(125 * multiplier),
                    "protein_g": 6 * multiplier,
                    "carbs_g": 15 * multiplier,
                    "fat_g": 4 * multiplier,
                    "fibre_g": 2 * multiplier,
                }
            ],
            "summary": "Scaled the stated values from 100 g to the 400 g portion.",
            "calories": 500,
            "protein_g": 24,
            "carbs_g": 60,
            "fat_g": 16,
            "fibre_g": 8,
            "confidence": "high",
        }
    )

    checked = quality_assure_estimate(reference)

    assert checked.calories == 500
    assert checked.protein_g == 24
    assert checked.carbs_g == 60
    assert checked.fat_g == 16
    assert checked.fibre_g == 8


def test_streak_uses_yesterday_if_today_missing():
    today = date.today()
    df = pd.DataFrame({"entry_date": [today - timedelta(days=2), today - timedelta(days=1)]})
    assert current_streak(df) == 2


def test_excel_export_removes_timezone_information():
    aware = datetime(2026, 8, 21, 12, tzinfo=ZoneInfo("Europe/London"))
    data = pd.DataFrame({"created_at": [aware], "value": [1]})

    exported = excel_safe_data(data)

    assert exported.loc[0, "created_at"].tzinfo is None


def test_recent_kpi_table_excludes_fasting_and_marks_circumstances():
    data = pd.DataFrame(
        {
            "entry_date": [date(2026, 8, 24), date(2026, 8, 25)],
            "weight_kg": [101.5, 101.2],
            "fasting_hours": [16.0, 14.0],
            "illness": [False, True],
            "injury": [False, False],
            "travel": [False, False],
            "unusual_day": [False, False],
            "holiday": [False, True],
        }
    )

    exported = recent_kpi_table(data)

    assert "fasting_hours" not in exported
    assert exported["extenuating_circumstance"].tolist() == ["Yes", "No"]


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


def test_daily_health_score_ignores_nan_measurements():
    item = pd.Series(
        {
            "bmi": 31.2,
            "waist_cm": float("nan"),
            "systolic": float("nan"),
            "diastolic": float("nan"),
            "resting_heart_rate": float("nan"),
            "sleep_hours": float("nan"),
            "steps": float("nan"),
            "mood": float("nan"),
            "energy": 7,
        }
    )

    score, label, included = daily_health_score(item)

    assert score == 52
    assert label == "Watch"
    assert included == ["BMI", "Energy"]


def test_daily_health_score_returns_none_when_every_measurement_is_nan():
    item = pd.Series(
        {
            "bmi": float("nan"),
            "waist_cm": float("nan"),
            "mood": float("nan"),
            "energy": float("nan"),
        }
    )

    assert daily_health_score(item) is None


def test_health_journey_score_uses_all_history_and_is_deterministic():
    good = {
        "bmi": 24.0,
        "waist_cm": 82.0,
        "systolic": 118,
        "diastolic": 78,
        "resting_heart_rate": 58,
        "sleep_hours": 8.0,
        "steps": 9000,
        "calories": 2000,
        "protein_g": 140,
        "fibre_g": 30,
        "mood": 9,
        "energy": 9,
        "cravings": 2,
        "diet_satisfaction": 9,
    }
    poor = {
        "bmi": 38.0,
        "waist_cm": 130.0,
        "systolic": 170,
        "diastolic": 110,
        "resting_heart_rate": 120,
        "sleep_hours": 4.0,
        "steps": 1000,
        "calories": 3500,
        "protein_g": 30,
        "fibre_g": 5,
        "mood": 2,
        "energy": 2,
        "cravings": 9,
        "diet_satisfaction": 2,
    }
    targets = {"calories": 2000, "protein_g": 140, "fibre_g": 30}
    good_recent = pd.DataFrame(
        [
            {"entry_date": date(2026, 1, 1), **poor},
            {"entry_date": date(2026, 3, 1), **good},
        ]
    )
    poor_recent = pd.DataFrame(
        [
            {"entry_date": date(2026, 1, 1), **good},
            {"entry_date": date(2026, 3, 1), **poor},
        ]
    )

    first = health_journey_score(good_recent, targets=targets)
    second = health_journey_score(good_recent, targets=targets)
    reversed_result = health_journey_score(poor_recent, targets=targets)

    assert first == second
    assert first is not None and reversed_result is not None
    assert first[0] > reversed_result[0]
    assert first[2].keys() == {
        "Body",
        "Cardiovascular",
        "Recovery",
        "Activity",
        "Nutrition",
        "Wellbeing",
    }
    assert first[3:] == (date(2026, 1, 1), date(2026, 3, 1))


def test_health_journey_score_ignores_missing_domains_instead_of_scoring_zero():
    history = pd.DataFrame([{"entry_date": date(2026, 8, 28), "sleep_hours": 8.0}])

    score = health_journey_score(history)

    assert score is not None
    assert score[0] == 100
    assert score[1] == "Limited data"
    assert score[2] == {"Recovery": 100}


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


def test_palette_exposes_read_only_app_hues():
    palette = derived_palette("dark", "#7B8451")

    assert {
        "background",
        "surface",
        "secondary",
        "accent",
        "foreground",
        "muted",
        "link",
        "input",
        "border",
    } <= palette.keys()
    assert palette["surface"] == palette["secondary"]


def test_palette_allows_saved_colour_overrides_and_keeps_hover_linked_to_cards():
    palette = derived_palette(
        "dark",
        "#7B8451",
        overrides={
            "background": "#101112",
            "surface": "#202122",
            "foreground": "#F0F1F2",
            "muted": "#A0A1A2",
            "link": "#C0C1C2",
            "border": "#505152",
        },
    )

    assert palette["background"] == "#101112"
    assert palette["surface"] == palette["secondary"] == "#202122"
    assert palette["foreground"] == "#F0F1F2"
    assert palette["muted"] == "#A0A1A2"
    assert palette["link"] == "#C0C1C2"
    assert palette["border"] == "#505152"


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


def test_evening_reminder_waits_for_evening_submission():
    morning_only = SimpleNamespace(
        morning_submitted=True,
        evening_submitted=False,
        weight_kg=100.0,
    )
    completed = SimpleNamespace(evening_submitted=True)

    assert evening_reminder_needed(morning_only)
    assert not evening_reminder_needed(completed)


def test_motivational_library_has_60_unique_short_entries():
    assert quote_count() == 60
    assert len(set(QUOTES)) == 60
    assert max(map(len, QUOTES)) < 100


def test_daily_quote_is_stable_for_the_day():
    day = date(2026, 8, 21)
    assert daily_item(QUOTES, day) == daily_item(QUOTES, day)


def test_weekly_item_is_stable_monday_to_sunday_and_changes_next_week():
    monday = date(2026, 8, 24)
    assert all(
        weekly_item(QUOTES, monday + timedelta(days=offset)) == weekly_item(QUOTES, monday)
        for offset in range(7)
    )
    assert weekly_item(QUOTES, monday + timedelta(days=7)) != weekly_item(QUOTES, monday)


def test_every_research_note_has_a_source_and_motivation():
    assert len(RESEARCH_INSIGHTS) >= 25
    assert len({item["insight"] for item in RESEARCH_INSIGHTS}) >= 25
    assert all(item["insight"] and item["source"] and item["url"] for item in RESEARCH_INSIGHTS)
    assert all(item["motivation"] for item in RESEARCH_INSIGHTS)


def test_research_note_rotates_with_calendar_week():
    start = date(2026, 8, 24)
    weekly_notes = [
        weekly_item(RESEARCH_INSIGHTS, start + timedelta(weeks=offset)) for offset in range(25)
    ]
    assert len({item["insight"] for item in weekly_notes}) == 25


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


def test_weekly_coaching_handles_nutrition_before_weight_entries():
    data = pd.DataFrame(
        {
            "entry_date": [date(2026, 8, 25)],
            "calories": [1800],
            "protein_g": [140],
        }
    )

    summary = weekly_coaching_summary(data, date(2026, 8, 25))

    assert summary["logged_days"] == 1
    assert summary["weight_change"] is None


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
