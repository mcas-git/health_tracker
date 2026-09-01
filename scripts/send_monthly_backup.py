from __future__ import annotations

import smtplib
import sys
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from health_tracker.backups import backup_filename, create_encrypted_backup
from health_tracker.config import LONDON, setting
from health_tracker.db import init_db


def should_send_monthly_backup(now: datetime, event_name: str) -> bool:
    return event_name != "schedule" or (
        now.astimezone(LONDON).day == 1 and now.astimezone(LONDON).hour == 19
    )


def build_backup_message(now: datetime, encrypted_backup: bytes) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = f"Encrypted Health Journey backup · {now:%B %Y}"
    message["From"] = formataddr(
        (setting("REMINDER_FROM_NAME", "Health Journey"), setting("REMINDER_FROM"))
    )
    message["To"] = setting("REMINDER_TO")
    message.set_content(
        "Your monthly encrypted Health Journey backup is attached.\n\n"
        "Keep your BACKUP_ENCRYPTION_KEY separately: the attachment cannot be restored without it. "
        "You can merge this file from Targets, backup and privacy in the tracker."
    )
    message.add_attachment(
        encrypted_backup,
        maintype="application",
        subtype="octet-stream",
        filename=backup_filename(now.date()),
    )
    return message


def main() -> None:
    now = datetime.now(LONDON)
    if not should_send_monthly_backup(now, setting("GITHUB_EVENT_NAME")):
        print(f"Skipping duplicate daylight-saving cron at {now:%H:%M %Z}.")
        return
    backup_key = setting("BACKUP_ENCRYPTION_KEY")
    if not backup_key:
        print("BACKUP_ENCRYPTION_KEY is not configured; monthly backup skipped.")
        return
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
        raise SystemExit(f"Missing monthly backup settings: {', '.join(missing)}")
    init_db()
    message = build_backup_message(now, create_encrypted_backup(backup_key))
    with smtplib.SMTP(
        setting("SMTP_HOST", "smtp.gmail.com"),
        int(setting("SMTP_PORT", "587")),
        timeout=30,
    ) as smtp:
        smtp.starttls()
        smtp.login(setting("SMTP_USERNAME"), setting("SMTP_PASSWORD"))
        smtp.send_message(message)


if __name__ == "__main__":
    main()
