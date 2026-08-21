from __future__ import annotations

import streamlit as st

FONTS = {
    "Modern sans": "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    "Classic serif": "Georgia, 'Times New Roman', serif",
    "Clean rounded": "Avenir, 'Trebuchet MS', sans-serif",
    "Focused mono": "ui-monospace, SFMono-Regular, Menlo, monospace",
}

ACCENTS = {
    "Teal": "#2A9D8F",
    "Ocean": "#2979A8",
    "Violet": "#7057C7",
    "Coral": "#D8664F",
    "Forest": "#397552",
}


def apply_theme(mode: str, accent: str, font_name: str) -> None:
    dark = mode == "dark"
    background = "#101614" if dark else "#F7FAF9"
    surface = "#18221F" if dark else "#FFFFFF"
    secondary = "#22302C" if dark else "#EAF4F1"
    text = "#EDF6F2" if dark else "#16302B"
    muted = "#A9BBB5" if dark else "#63736F"
    font = FONTS.get(font_name, FONTS["Modern sans"])
    st.markdown(
        f"""
        <style>
        :root {{ --accent:{accent}; --surface:{surface}; --muted:{muted}; }}
        .stApp, [data-testid="stAppViewContainer"] {{ background:{background}; color:{text}; }}
        html, body, [class*="st-"] {{ font-family:{font}; }}
        [data-testid="stSidebar"] {{ background:{secondary}; }}
        div[data-testid="stMetric"], .quote-card {{
            background:{surface}; border:1px solid {accent}33; border-radius:16px; padding:18px;
            box-shadow:0 5px 20px #0000000d;
        }}
        .quote-card {{ padding:32px; margin:12px 0 28px; }}
        .quote-text {{ font-size:clamp(1.35rem,3vw,2rem); line-height:1.4; font-weight:600; }}
        .quote-label {{ color:{accent}; letter-spacing:.12em; font-size:.75rem; font-weight:700; }}
        .stButton > button, .stFormSubmitButton > button {{ border-radius:10px; }}
        a {{ color:{accent}; }}
        </style>
        """,
        unsafe_allow_html=True,
    )
