from __future__ import annotations

import hashlib
import hmac
import json
from base64 import b64encode, urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import extra_streamlit_components as stx
import streamlit as st

from health_tracker.config import setting

GOOGLE_LOGO = Path(__file__).resolve().parents[1] / "assets" / "logo" / "google.svg"
GOOGLE_SIGN_IN_LABEL = "Sign in with Google"
if GOOGLE_LOGO.is_file():
    google_logo_data = b64encode(GOOGLE_LOGO.read_bytes()).decode()
    GOOGLE_SIGN_IN_LABEL = (
        f"![](data:image/svg+xml;base64,{google_logo_data}) Sign in with Google"
    )


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


COOKIE_NAME = "health_journey_remember"
OIDC_SETTINGS = {
    "redirect_uri",
    "cookie_secret",
    "client_id",
    "client_secret",
    "server_metadata_url",
}


@dataclass(frozen=True)
class AuthContext:
    mode: str
    cookie_manager: stx.CookieManager | None = None


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


def email_is_allowed(email: str, configured_emails: str) -> bool:
    allowed = {
        item.strip().casefold() for item in configured_emails.split(",") if item.strip()
    }
    return email.strip().casefold() in allowed


def oidc_configured() -> bool:
    try:
        auth = st.secrets["auth"]
        return all(str(auth.get(name, "")).strip() for name in OIDC_SETTINGS)
    except Exception:
        return False


def _login_shell_intro(message: str | None = None) -> None:
    st.markdown('<p class="login-wordmark">HEALTH JOURNEY</p>', unsafe_allow_html=True)
    st.title("Welcome back")
    if message:
        st.caption(message)


def sign_out_button(auth_context: AuthContext | stx.CookieManager) -> None:
    if st.button("Log out", icon=":material/logout:", use_container_width=True):
        if isinstance(auth_context, AuthContext) and auth_context.mode == "oidc":
            st.logout()
            return
        cookie_manager = (
            auth_context.cookie_manager
            if isinstance(auth_context, AuthContext)
            else auth_context
        )
        if cookie_manager is not None:
            cookie_manager.delete(COOKIE_NAME, key="delete_auth_cookie")
        st.session_state.authenticated = False
        st.rerun()


def _require_google_login() -> AuthContext:
    allowed_emails = setting("ALLOWED_EMAIL")
    if not allowed_emails:
        st.error("ALLOWED_EMAIL is not configured in the app secrets.")
        st.stop()
    if not st.user.is_logged_in:
        _, login_column, _ = st.columns([1, 1.15, 1])
        with login_column, st.container(key="login_shell"):
            _login_shell_intro()
            if st.button(
                GOOGLE_SIGN_IN_LABEL,
                type="primary",
                use_container_width=True,
                key="google_sign_in",
            ):
                st.login()
            st.markdown(
                '<p class="login-footnote">Use your approved Google account to continue.</p>',
                unsafe_allow_html=True,
            )
        st.stop()
    identity = st.user.to_dict()
    email = str(identity.get("email", ""))
    if not identity.get("email_verified") or not email_is_allowed(email, allowed_emails):
        _, login_column, _ = st.columns([1, 1.15, 1])
        with login_column, st.container(key="login_shell"):
            _login_shell_intro("This Google account is not approved for this tracker.")
            st.error("Access denied. Sign in with the authorised Google account.")
            if st.button("Use a different Google account", use_container_width=True):
                st.logout()
        st.stop()
    return AuthContext(mode="oidc")


def _require_password_login() -> AuthContext:
    expected = setting("APP_PASSWORD_HASH")
    if not expected:
        st.error("Google authentication or APP_PASSWORD_HASH must be configured. See README.md.")
        st.stop()
    cookie_manager = stx.CookieManager(key="health_journey_cookie_manager")
    if not st.session_state.get("authenticated"):
        st.session_state.authenticated = valid_remember_token(
            cookie_manager.get(COOKIE_NAME), expected
        )
    if st.session_state.get("authenticated"):
        return AuthContext(mode="password", cookie_manager=cookie_manager)
    _, login_column, _ = st.columns([1, 1.15, 1])
    with login_column, st.container(key="login_shell"):
        _login_shell_intro("Sign in to continue to your private health tracker.")
        with st.form("login", border=False):
            password = st.text_input("Password", type="password")
            remember = st.checkbox("Remember me on this device for 30 days", value=True)
            submitted = st.form_submit_button(
                "Sign in", type="primary", use_container_width=True
            )
        st.markdown(
            '<p class="login-footnote">Your health data stays behind this private '
            'access screen.</p>',
            unsafe_allow_html=True,
        )
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


def require_login() -> AuthContext:
    if oidc_configured():
        return _require_google_login()
    return _require_password_login()
