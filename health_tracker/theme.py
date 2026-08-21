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
    dark_overrides = (
        f"""
        [data-testid="stAppViewContainer"] h1,
        [data-testid="stAppViewContainer"] h2,
        [data-testid="stAppViewContainer"] h3,
        [data-testid="stAppViewContainer"] h4,
        [data-testid="stAppViewContainer"] p,
        [data-testid="stAppViewContainer"] label,
        [data-testid="stAppViewContainer"] li,
        [data-testid="stMetricValue"],
        [data-testid="stMetricLabel"],
        [data-testid="stMetricDelta"],
        [data-testid="stSidebar"] * {{ color:{text} !important; }}

        [data-baseweb="input"] > div,
        [data-baseweb="base-input"],
        [data-baseweb="textarea"],
        [data-baseweb="select"] > div,
        [data-baseweb="popover"] > div,
        [role="listbox"],
        [role="option"] {{ background-color:{surface} !important; color:{text} !important; }}

        input, textarea,
        [data-baseweb="select"] input {{
            color:{text} !important; -webkit-text-fill-color:{text} !important;
        }}
        input::placeholder, textarea::placeholder {{
            color:{muted} !important; -webkit-text-fill-color:{muted} !important;
        }}
        [data-testid="stWidgetLabel"] p,
        [data-testid="stCaptionContainer"],
        [data-testid="stMarkdownContainer"] small {{ color:{muted} !important; }}

        button[kind="secondary"], button[data-baseweb="button"] {{
            background-color:{surface}; color:{text}; border-color:{muted};
        }}
        button[kind="primary"] {{ color:#ffffff !important; }}
        [data-testid="stHeader"], [data-testid="stToolbar"] {{
            background-color:{background} !important;
        }}
        hr {{ border-color:{muted}55; }}
        """
        if dark
        else ""
    )
    st.markdown(
        f"""
        <style>
        :root {{ --accent:{accent}; --surface:{surface}; --muted:{muted}; }}
        .stApp, [data-testid="stAppViewContainer"] {{ background:{background}; color:{text}; }}
        [data-testid="stMarkdownContainer"],
        [data-testid="stWidgetLabel"],
        [data-testid="stMetric"],
        input, textarea {{ font-family:{font}; }}
        [data-testid="stSidebar"] {{ background:{secondary}; }}
        div[data-testid="stMetric"], .quote-card {{
            background:{surface}; border:1px solid {accent}33; border-radius:16px; padding:18px;
            box-shadow:0 5px 20px #0000000d;
        }}
        .quote-card {{ padding:32px; margin:12px 0 28px; }}
        .neutral-note {{
            background:{surface}; color:{text}; border-left:4px solid {accent};
            border-radius:10px; padding:16px 18px; margin:12px 0;
        }}
        .quote-text {{ font-size:clamp(1.35rem,3vw,2rem); line-height:1.4; font-weight:600; }}
        .quote-label {{ color:{accent}; letter-spacing:.12em; font-size:.75rem; font-weight:700; }}
        .stButton > button, .stFormSubmitButton > button {{ border-radius:10px; }}
        [data-testid="stAlert"] {{
            background:{surface} !important; color:{text} !important;
            border-color:{accent} !important;
        }}
        [data-testid="stSidebarCollapsedControl"] {{
            display:flex !important; visibility:visible !important; opacity:1 !important;
            background:{surface} !important; color:{text} !important;
            border:1px solid {accent}55 !important; border-radius:9px !important;
        }}
        [data-testid="stSidebarCollapsedControl"] span,
        [data-testid="stSidebarCollapseButton"] span {{
            font-family:"Material Symbols Rounded", "Material Symbols Outlined" !important;
        }}
        a {{ color:{accent}; }}
        {dark_overrides}
        </style>
        """,
        unsafe_allow_html=True,
    )
