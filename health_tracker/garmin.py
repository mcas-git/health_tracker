from __future__ import annotations

from datetime import date

from garminconnect import Garmin

from health_tracker.config import setting


def _first_value(*values):
    return next((item for item in values if item is not None), None)


def sync_day(day: date) -> dict:
    email = setting("GARMIN_EMAIL")
    password = setting("GARMIN_PASSWORD")
    if not email or not password:
        raise ValueError("Add GARMIN_EMAIL and GARMIN_PASSWORD to secrets first.")
    client = Garmin(email, password)
    client.login()
    day_text = day.isoformat()
    stats = client.get_stats(day_text)
    sleep = client.get_sleep_data(day_text)
    heart_rate = client.get_heart_rates(day_text)
    activities = client.get_activities_by_date(day_text, day_text)
    sleep_record = sleep.get("dailySleepDTO") or {}
    sleep_seconds = sleep_record.get("sleepTimeSeconds")
    resting_hr = _first_value(
        heart_rate.get("restingHeartRate"), stats.get("restingHeartRate")
    )
    total_calories = stats.get("totalKilocalories")
    active_calories = stats.get("activeKilocalories")
    resting_calories = stats.get("bmrKilocalories")
    if total_calories is None and active_calories is not None and resting_calories is not None:
        total_calories = active_calories + resting_calories
    return {
        "steps": stats.get("totalSteps"),
        "calories_burned": total_calories,
        "active_calories": active_calories,
        "resting_calories": resting_calories,
        "sleep_hours": (
            round(sleep_seconds / 3600, 2) if sleep_seconds is not None else None
        ),
        "resting_heart_rate": resting_hr,
        "source_date": stats.get("calendarDate") or day_text,
        "sleep_date": sleep_record.get("calendarDate") or day_text,
        "activities": [
            {
                "name": a.get("activityName"),
                "type": (a.get("activityType") or {}).get("typeKey"),
                "duration_seconds": a.get("duration"),
                "calories": a.get("calories"),
            }
            for a in activities
        ],
    }
