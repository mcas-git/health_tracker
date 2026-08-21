from __future__ import annotations

import smtplib
import sys
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from health_tracker.analytics import load_data, weekly_coaching_summary
from health_tracker.config import LONDON, setting
from health_tracker.db import init_db


def should_send_weekly(now: datetime, event_name: str) -> bool:
    return event_name != "schedule" or now.astimezone(LONDON).hour == 19


def build_weekly_message(now: datetime, summary: dict) -> EmailMessage:
    url = setting("APP_URL", "http://localhost:8501")
    change = summary.get("weight_change")
    change_text = f"{change:+.1f} kg" if change is not None else "not enough data"
    subject = f"Your weekly health review · {summary['completion']}% logged"
    lines = [
        f"Days logged: {summary['logged_days']}/7",
        f"Weekly weight trend: {change_text}",
        f"Weight lost from start: {summary.get('loss_percent', 0):.1f}%",
        f"Suggested next action: {summary['recommendation']}",
    ]
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr(
        (setting("REMINDER_FROM_NAME", "Health Journey"), setting("REMINDER_FROM"))
    )
    message["To"] = setting("REMINDER_TO")
    message.set_content("Weekly review\n\n" + "\n".join(lines) + f"\n\nOpen the tracker:\n{url}")
    rows = "".join(f"<li>{escape(line)}</li>" for line in lines)
    message.add_alternative(
        f"""<!doctype html><html><body style="font-family:Arial,sans-serif;color:#2c3023">
        <div style="max-width:600px;margin:30px auto;padding:32px;background:#f5f5ee">
        <p style="font-weight:bold">HEALTH JOURNEY · WEEKLY REVIEW</p>
        <h1 style="font-size:24px">Review, learn, plan one action</h1>
        <ul style="font-size:17px;line-height:1.7">{rows}</ul>
        <p><a href="{escape(url, quote=True)}">Open weekly coaching</a></p>
        <p style="font-size:13px">Trends are informational and are not medical advice.</p>
        </div></body></html>""",
        subtype="html",
    )
    return message


def main() -> None:
    required = [
        "DATABASE_URL",
        "SMTP_HOST",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "REMINDER_FROM",
        "REMINDER_TO",
    ]
    missing = [name for name in required if not setting(name)]
    if missing:
        raise SystemExit(f"Missing weekly report settings: {', '.join(missing)}")
    now = datetime.now(LONDON)
    if not should_send_weekly(now, setting("GITHUB_EVENT_NAME")):
        print(f"Skipping duplicate daylight-saving cron at {now:%H:%M %Z}.")
        return
    init_db()
    summary = weekly_coaching_summary(load_data(), now.date())
    message = build_weekly_message(now, summary)
    with smtplib.SMTP(
        setting("SMTP_HOST", "smtp.gmail.com"), int(setting("SMTP_PORT", "587"))
    ) as smtp:
        smtp.starttls()
        smtp.login(setting("SMTP_USERNAME"), setting("SMTP_PASSWORD"))
        smtp.send_message(message)


if __name__ == "__main__":
    main()
