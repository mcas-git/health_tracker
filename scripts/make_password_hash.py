from __future__ import annotations

import getpass
import sys
from pathlib import Path

# Support direct execution: `uv run python scripts/make_password_hash.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from health_tracker.auth import hash_password

password = getpass.getpass("Choose the app password: ")
confirmation = getpass.getpass("Repeat the password: ")
if not password or password != confirmation:
    raise SystemExit("Passwords did not match or were empty.")
print(hash_password(password))
