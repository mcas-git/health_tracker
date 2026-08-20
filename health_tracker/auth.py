from __future__ import annotations

import hashlib
import hmac

import streamlit as st

from health_tracker.config import setting


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def require_login() -> None:
    expected = setting("APP_PASSWORD_HASH")
    if not expected:
        st.error("APP_PASSWORD_HASH is not configured. See README.md.")
        st.stop()
    if st.session_state.get("authenticated"):
        return
    st.title("Health Journey")
    st.caption("Private sign in")
    with st.form("login"):
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", use_container_width=True)
    if submitted and hmac.compare_digest(hash_password(password), expected):
        st.session_state.authenticated = True
        st.rerun()
    if submitted:
        st.error("Incorrect password")
    st.stop()
