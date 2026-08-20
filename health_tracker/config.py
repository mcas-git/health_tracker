from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

LONDON = ZoneInfo("Europe/London")


def setting(name: str, default: str = "") -> str:
    """Read a setting from environment or Streamlit secrets without requiring Streamlit."""
    value = os.getenv(name)
    if value is not None:
        return value
    try:
        import streamlit as st

        return str(st.secrets.get(name, default))
    except Exception:
        return default


@dataclass(frozen=True)
class Profile:
    age: int = 39
    sex: str = "male"
    height_cm: float = 177.0
    start_weight_kg: float = 105.0
    target_weight_kg: float = 77.0
    target_date: date = date(2027, 9, 1)


PROFILE = Profile()


def database_url() -> str:
    url = setting("DATABASE_URL", "sqlite:///data/health_tracker.db")
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("sqlite"):
        Path("data").mkdir(exist_ok=True)
    return url
