from __future__ import annotations

import smtplib
import sys
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from html import escape
from pathlib import Path

# Support direct execution locally and from GitHub Actions.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from health_tracker.config import LONDON, setting


def should_send(now: datetime, event_name: str) -> bool:
    """Skip the duplicate UTC cron during the other UK daylight-saving season."""
    return event_name != "schedule" or now.astimezone(LONDON).hour in {5, 21}


def reminder_copy(now: datetime) -> tuple[str, str, str]:
    if now.astimezone(LONDON).hour < 12:
        return (
            "🌅 Start today with one small check-in",
            "Good morning",
            "Record your starting point and set today's intention. A quick check-in now makes the "
            "next healthy choice easier: add your weight, fasting status and activity plan.",
        )
    return (
        "🌿 Close the loop on today's health journey",
        "Your two-minute evening check-in",
        "Take a moment to record the day while it is still fresh. Add your food note, "
        "measurements, fasting and habits. Consistent honest entries matter more than "
        "perfect days.",
    )


def build_message(now: datetime) -> EmailMessage:
    subject, heading, body = reminder_copy(now)
    url = setting("APP_URL", "http://localhost:8501")
    from_address = setting("REMINDER_FROM")
    from_name = setting("REMINDER_FROM_NAME", "Health Journey")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((from_name, from_address))
    message["To"] = setting("REMINDER_TO")
    message.set_content(
        f"{heading}\n\n{body}\n\nOpen your health tracker:\n{url}\n\n"
        "Just show up. The entry does not need to be perfect."
    )
    safe_url = escape(url, quote=True)
    message.add_alternative(
        f"""\
<!doctype html>
<html><body style="margin:0;background:#f3f8f6;font-family:Arial,sans-serif;color:#16302b">
  <div style="max-width:560px;margin:32px auto;padding:32px;background:white;border-radius:18px">
    <p style="color:#2a9d8f;font-weight:bold;margin-top:0">HEALTH JOURNEY</p>
    <h1 style="font-size:24px">{escape(heading)}</h1>
    <p style="font-size:17px;line-height:1.55">{escape(body)}</p>
    <p style="margin:28px 0">
      <a href="{safe_url}" style="background:#2a9d8f;color:white;text-decoration:none;
         padding:14px 22px;border-radius:10px;font-weight:bold">Open my health tracker</a>
    </p>
    <p style="font-size:14px;color:#63736f">Just show up. The entry does not need to be perfect.</p>
  </div>
</body></html>""",
        subtype="html",
    )
    return message


def main() -> None:
    required = ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "REMINDER_FROM", "REMINDER_TO"]
    missing = [name for name in required if not setting(name)]
    if missing:
        raise SystemExit(f"Missing reminder settings: {', '.join(missing)}")
    now = datetime.now(LONDON)
    if not should_send(now, setting("GITHUB_EVENT_NAME")):
        print(f"Skipping duplicate daylight-saving cron at {now:%H:%M %Z}.")
        return
    message = build_message(now)
    host = setting("SMTP_HOST", "smtp.gmail.com")
    port = int(setting("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(setting("SMTP_USERNAME"), setting("SMTP_PASSWORD"))
        smtp.send_message(message)


if __name__ == "__main__":
    main()
