from __future__ import annotations

from datetime import date

from garminconnect import Garmin

from health_tracker.config import setting


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
    sleep_seconds = sleep.get("dailySleepDTO", {}).get("sleepTimeSeconds")
    resting_hr = heart_rate.get("restingHeartRate") or stats.get("restingHeartRate")
    return {
        "steps": stats.get("totalSteps"),
        "calories_burned": stats.get("totalKilocalories"),
        "sleep_hours": round(sleep_seconds / 3600, 2) if sleep_seconds else None,
        "resting_heart_rate": resting_hr,
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
