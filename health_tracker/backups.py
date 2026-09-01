from __future__ import annotations

import json
from datetime import UTC, date, datetime

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Date as SQLDate
from sqlalchemy import DateTime as SQLDateTime
from sqlalchemy import select
from sqlalchemy.orm import Session

from health_tracker import db
from health_tracker.models import (
    AppPreferences,
    DailyEntry,
    GoalSettings,
    NutritionLog,
    TargetAdjustment,
    WeeklyPlan,
)

BACKUP_VERSION = 1
MAX_BACKUP_BYTES = 20 * 1024 * 1024
MAX_ROWS_PER_TABLE = 10_000
BACKUP_MODELS = {
    "daily_entries": DailyEntry,
    "nutrition_logs": NutritionLog,
    "goal_settings": GoalSettings,
    "app_preferences": AppPreferences,
    "weekly_plans": WeeklyPlan,
    "target_adjustments": TargetAdjustment,
}
IDENTITY_FIELDS = {
    "daily_entries": "entry_date",
    "nutrition_logs": "entry_date",
    "goal_settings": "id",
    "app_preferences": "id",
    "weekly_plans": "week_start",
    "target_adjustments": "week_start",
}


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def create_backup_document() -> dict:
    """Create a complete, portable snapshot without application secrets."""
    tables: dict[str, list[dict]] = {}
    with Session(db.engine) as session:
        for table_name, model in BACKUP_MODELS.items():
            records = session.scalars(select(model)).all()
            tables[table_name] = [
                {
                    column.name: _json_value(getattr(record, column.name))
                    for column in model.__table__.columns
                }
                for record in records
            ]
    return {
        "format": "health-journey-backup",
        "version": BACKUP_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "tables": tables,
    }


def _fernet(key: str) -> Fernet:
    try:
        return Fernet(key.strip().encode("ascii"))
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ValueError("BACKUP_ENCRYPTION_KEY is not a valid Fernet key.") from exc


def create_encrypted_backup(key: str) -> bytes:
    raw = json.dumps(create_backup_document(), separators=(",", ":")).encode()
    return _fernet(key).encrypt(raw)


def _validated_document(encrypted: bytes, key: str) -> dict:
    if not encrypted or len(encrypted) > MAX_BACKUP_BYTES:
        raise ValueError("The backup file is empty or too large.")
    try:
        raw = _fernet(key).decrypt(encrypted)
    except InvalidToken as exc:
        raise ValueError("The backup could not be decrypted with the configured key.") from exc
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("The decrypted backup is not valid JSON.") from exc
    if not isinstance(document, dict):
        raise ValueError("The backup document is malformed.")
    if document.get("format") != "health-journey-backup":
        raise ValueError("This is not a Health Journey backup.")
    if document.get("version") != BACKUP_VERSION:
        raise ValueError("This backup version is not supported.")
    tables = document.get("tables")
    if not isinstance(tables, dict):
        raise ValueError("The backup does not contain a table collection.")
    unknown_tables = set(tables) - set(BACKUP_MODELS)
    if unknown_tables:
        raise ValueError(
            f"The backup contains unknown tables: {', '.join(sorted(unknown_tables))}."
        )
    for table_name, rows in tables.items():
        if not isinstance(rows, list) or len(rows) > MAX_ROWS_PER_TABLE:
            raise ValueError(f"The {table_name} table has an invalid row collection.")
        allowed_columns = {column.name for column in BACKUP_MODELS[table_name].__table__.columns}
        for row in rows:
            if not isinstance(row, dict) or set(row) - allowed_columns:
                raise ValueError(f"The {table_name} table contains an invalid row.")
            if IDENTITY_FIELDS[table_name] not in row:
                raise ValueError(f"The {table_name} table contains a row without an identity.")
    return document


def inspect_encrypted_backup(encrypted: bytes, key: str) -> dict:
    document = _validated_document(encrypted, key)
    return {
        "created_at": document.get("created_at"),
        "tables": {
            table_name: len(document["tables"].get(table_name, [])) for table_name in BACKUP_MODELS
        },
        "total_rows": sum(len(rows) for rows in document["tables"].values()),
    }


def _database_value(column, value):
    if value is None:
        return None
    if isinstance(column.type, SQLDateTime):
        return datetime.fromisoformat(value)
    if isinstance(column.type, SQLDate):
        return date.fromisoformat(value)
    return value


def restore_encrypted_backup(encrypted: bytes, key: str) -> dict[str, int]:
    """Merge an encrypted snapshot transactionally; records absent from it are retained."""
    document = _validated_document(encrypted, key)
    created = 0
    updated = 0
    with db.session_scope() as session:
        for table_name, model in BACKUP_MODELS.items():
            identity_name = IDENTITY_FIELDS[table_name]
            columns = {column.name: column for column in model.__table__.columns}
            for raw_row in document["tables"].get(table_name, []):
                values = {
                    name: _database_value(columns[name], value) for name, value in raw_row.items()
                }
                identity_value = values[identity_name]
                item = session.scalar(
                    select(model).where(getattr(model, identity_name) == identity_value)
                )
                if item is None:
                    initial = {identity_name: identity_value}
                    item = model(**initial)
                    session.add(item)
                    created += 1
                else:
                    updated += 1
                for name, value in values.items():
                    if name == "id" and identity_name != "id":
                        continue
                    setattr(item, name, value)
    return {"created": created, "updated": updated}


def backup_filename(day: date | None = None) -> str:
    return f"health-journey-{day or date.today():%Y-%m-%d}.healthbackup"
