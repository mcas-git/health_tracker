from __future__ import annotations

import streamlit as st

FONTS = {
    "Modern sans": "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    "Classic serif": "Georgia, 'Times New Roman', serif",
    "Clean rounded": "Avenir, 'Trebuchet MS', sans-serif",
    "Focused mono": "ui-monospace, SFMono-Regular, Menlo, monospace",
}

OLIVE_ACCENT = "#7B8451"


def apply_theme(mode: str, font_name: str) -> None:
    dark = mode == "dark"
    accent = OLIVE_ACCENT
    background = "#161811" if dark else "#F5F5EE"
    surface = "#22251A" if dark else "#FCFCF7"
    secondary = "#292D1F" if dark else "#E9EAD8"
    text = "#EFF0E5" if dark else "#2C3023"
    muted = "#B1B59A" if dark else "#6E7359"
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
        [data-baseweb="input"],
        [data-baseweb="textarea"],
        [data-baseweb="select"] > div,
        [data-testid="stDateInput"] > div > div,
        [data-testid="stNumberInput"] > div > div {{
            background-color:{surface} !important;
            border-color:{muted} !important;
            color:{text} !important;
        }}
        [data-baseweb="select"] span,
        [data-baseweb="select"] div,
        [data-testid="stDateInput"] button,
        [data-testid="stNumberInput"] button {{
            color:{text} !important;
            fill:{text} !important;
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
        .sport-watermark {{
            position:fixed; left:20rem; bottom:1.5rem; width:min(25vw,350px);
            opacity:.065; pointer-events:none; z-index:0;
        }}
        .sport-watermark svg {{ display:block; width:100%; height:auto; }}
        @media (max-width:768px) {{
            .sport-watermark {{ left:1rem; bottom:1rem; width:210px; opacity:.055; }}
        }}
        .neutral-note {{
            background:{surface}; color:{text}; border-left:4px solid {accent};
            border-radius:10px; padding:16px 18px; margin:12px 0;
        }}
        .quote-text {{ font-size:clamp(1.35rem,3vw,2rem); line-height:1.4; font-weight:600; }}
        .quote-label {{ color:{accent}; letter-spacing:.12em; font-size:.75rem; font-weight:700; }}
        .stButton > button, .stFormSubmitButton > button {{ border-radius:10px; }}
        button[kind="primary"], .stFormSubmitButton > button {{
            background:{accent} !important; border-color:{accent} !important;
        }}
        [data-testid="stAlert"] {{
            background:{surface} !important; color:{text} !important;
            border-color:{accent} !important;
        }}
        [data-testid="stAlert"] svg,
        [data-testid="stCheckbox"] svg {{ fill:{accent} !important; color:{accent} !important; }}
        [data-testid="stProgress"] [role="progressbar"] > div {{ background:{accent} !important; }}
        [data-testid="stSidebarCollapsedControl"] {{
            display:flex !important; visibility:visible !important; opacity:1 !important;
            background:{surface} !important; color:{text} !important;
            border:1px solid {accent}55 !important; border-radius:9px !important;
        }}
        [data-testid="stSidebarCollapsedControl"] button,
        [data-testid="stSidebarCollapseButton"] button {{
            background:{surface} !important; color:{text} !important;
            border:1px solid {muted} !important;
        }}
        [data-testid="stSidebarCollapsedControl"] span,
        [data-testid="stSidebarCollapseButton"] span {{
            font-family:"Material Symbols Rounded", "Material Symbols Outlined" !important;
            color:{text} !important; opacity:1 !important; font-size:1.5rem !important;
            font-variation-settings:"FILL" 0, "wght" 600, "GRAD" 0, "opsz" 24;
        }}
        [data-testid="stSidebarCollapsedControl"] svg,
        [data-testid="stSidebarCollapseButton"] svg {{
            color:{text} !important; fill:{text} !important;
            stroke:{text} !important; opacity:1 !important;
        }}
        a {{ color:{accent}; }}
        {dark_overrides}
        </style>
        """,
        unsafe_allow_html=True,
    )
