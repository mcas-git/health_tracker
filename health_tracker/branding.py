from __future__ import annotations

from base64 import b64encode
from pathlib import Path

BRAND_MARK_PATH = (
    Path(__file__).resolve().parents[1] / "assets" / "logo" / "health-journey-mark.svg"
)
BRAND_MARK_DATA_URI = (
    "data:image/svg+xml;base64," + b64encode(BRAND_MARK_PATH.read_bytes()).decode()
)
