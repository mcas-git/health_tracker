from __future__ import annotations

import hashlib
import hmac
import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import UTC, datetime, timedelta

import extra_streamlit_components as stx
import streamlit as st

from health_tracker.config import setting


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


COOKIE_NAME = "health_journey_remember"


def _signing_key(password_hash: str) -> bytes:
    return hashlib.sha256(f"health-journey:{password_hash}".encode()).digest()


def create_remember_token(password_hash: str, days: int = 30) -> str:
    payload = json.dumps(
        {"exp": int((datetime.now(UTC) + timedelta(days=days)).timestamp())},
        separators=(",", ":"),
    ).encode()
    encoded = urlsafe_b64encode(payload).decode().rstrip("=")
    signature = hmac.new(_signing_key(password_hash), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def valid_remember_token(token: str | None, password_hash: str) -> bool:
    try:
        encoded, signature = (token or "").split(".", 1)
        expected = hmac.new(
            _signing_key(password_hash), encoded.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return False
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(urlsafe_b64decode(padded).decode())
        return int(payload["exp"]) > int(datetime.now(UTC).timestamp())
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return False


def require_login() -> None:
    expected = setting("APP_PASSWORD_HASH")
    if not expected:
        st.error("APP_PASSWORD_HASH is not configured. See README.md.")
        st.stop()
    cookie_manager = stx.CookieManager(key="health_journey_cookie_manager")
    if not st.session_state.get("authenticated"):
        st.session_state.authenticated = valid_remember_token(
            cookie_manager.get(COOKIE_NAME), expected
        )
    if st.session_state.get("authenticated"):
        if st.sidebar.button("Sign out", use_container_width=True):
            cookie_manager.delete(COOKIE_NAME, key="delete_auth_cookie")
            st.session_state.authenticated = False
            st.rerun()
        return
    st.title("Welcome back")
    st.caption("Your private space for a stronger, healthier year")
    with st.form("login"):
        password = st.text_input("Password", type="password")
        remember = st.checkbox("Remember me on this device for 30 days", value=True)
        submitted = st.form_submit_button("Sign in", use_container_width=True)
    if submitted and hmac.compare_digest(hash_password(password), expected):
        st.session_state.authenticated = True
        if remember:
            cookie_manager.set(
                COOKIE_NAME,
                create_remember_token(expected),
                expires_at=datetime.now() + timedelta(days=30),
                key="set_auth_cookie",
            )
        st.rerun()
    if submitted:
        st.error("Incorrect password")
    st.stop()
