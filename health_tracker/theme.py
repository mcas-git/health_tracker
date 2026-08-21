from __future__ import annotations

import re

import streamlit as st

FONTS = {
    "Modern sans": "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    "Classic serif": "Georgia, 'Times New Roman', serif",
    "Clean rounded": "Avenir, 'Trebuchet MS', sans-serif",
    "Focused mono": "ui-monospace, SFMono-Regular, Menlo, monospace",
    "Editorial": "Baskerville, 'Palatino Linotype', Palatino, serif",
    "Humanist": "Optima, Candara, 'Segoe UI', sans-serif",
    "Geometric": "Futura, 'Century Gothic', Avenir, sans-serif",
    "Compact": "'Arial Narrow', 'Helvetica Neue', Arial, sans-serif",
    "Friendly": "Verdana, Geneva, sans-serif",
}

OLIVE_ACCENT = "#7B8451"


def normalize_color(value: str) -> str:
    value = value.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return value.upper()
    match = re.fullmatch(r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)", value, re.I)
    if match and all(0 <= int(part) <= 255 for part in match.groups()):
        return "#" + "".join(f"{int(part):02X}" for part in match.groups())
    raise ValueError("Use #RRGGBB or rgb(0–255, 0–255, 0–255).")


def _mix(color: str, target: str, amount: float) -> str:
    source = tuple(int(color[index : index + 2], 16) for index in (1, 3, 5))
    destination = tuple(int(target[index : index + 2], 16) for index in (1, 3, 5))
    values = tuple(
        round(left * (1 - amount) + right * amount)
        for left, right in zip(source, destination, strict=True)
    )
    return "#" + "".join(f"{value:02X}" for value in values)


def derived_palette(mode: str, accent: str) -> dict[str, str | list[str]]:
    accent = normalize_color(accent)
    dark = mode == "dark"
    return {
        "accent": accent,
        "foreground": _mix(accent, "#FFFFFF", 0.9) if dark else _mix(accent, "#000000", 0.76),
        "grid": _mix(accent, "#FFFFFF", 0.38) if dark else _mix(accent, "#FFFFFF", 0.68),
        "series": [
            accent,
            _mix(accent, "#FFFFFF", 0.38) if dark else _mix(accent, "#000000", 0.3),
            _mix(accent, "#FFFFFF", 0.65) if dark else _mix(accent, "#000000", 0.52),
        ],
        "scale": [
            _mix(accent, "#000000", 0.45) if dark else _mix(accent, "#FFFFFF", 0.78),
            accent,
            _mix(accent, "#FFFFFF", 0.68) if dark else _mix(accent, "#000000", 0.48),
        ],
    }


def apply_theme(mode: str, accent: str, font_name: str) -> None:
    dark = mode == "dark"
    accent = normalize_color(accent)
    background = _mix(accent, "#000000", 0.84) if dark else _mix(accent, "#FFFFFF", 0.93)
    surface = _mix(accent, "#000000", 0.72) if dark else _mix(accent, "#FFFFFF", 0.98)
    secondary = _mix(accent, "#000000", 0.66) if dark else _mix(accent, "#FFFFFF", 0.84)
    text = _mix(accent, "#FFFFFF", 0.9) if dark else _mix(accent, "#000000", 0.76)
    muted = _mix(accent, "#FFFFFF", 0.55) if dark else _mix(accent, "#000000", 0.48)
    accent_rgb = ", ".join(str(int(accent[index : index + 2], 16)) for index in (1, 3, 5))
    red, green, blue = (int(accent[index : index + 2], 16) for index in (1, 3, 5))
    accent_text = "#111111" if (0.2126 * red + 0.7152 * green + 0.0722 * blue) > 150 else "#FFFFFF"
    neutral_icon = "#D8D8D8" if dark else "#4A4A4A"
    sidebar_icon = "#FFFFFF" if dark else neutral_icon
    neutral_border = "#666666" if dark else "#C8C8C8"
    neutral_surface = "#303030" if dark else "#F2F2F2"
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
        input[type="date"], input[type="time"] {{
            color:{text} !important; background:{surface} !important;
            -webkit-text-fill-color:{text} !important; color-scheme:dark;
        }}
        input[type="date"]::-webkit-datetime-edit,
        input[type="date"]::-webkit-datetime-edit-fields-wrapper,
        input[type="date"]::-webkit-datetime-edit-text,
        input[type="date"]::-webkit-datetime-edit-month-field,
        input[type="date"]::-webkit-datetime-edit-day-field,
        input[type="date"]::-webkit-datetime-edit-year-field,
        input[type="time"]::-webkit-datetime-edit {{
            color:{text} !important; -webkit-text-fill-color:{text} !important;
            opacity:1 !important;
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
        :root, .stApp {{
            --accent:{accent}; --surface:{surface}; --muted:{muted};
            --primary-color:{accent} !important;
            --primary-color-rgb:{accent_rgb} !important;
        }}
        input, button {{ accent-color:{accent} !important; }}
        .stApp, [data-testid="stAppViewContainer"] {{ background:{background}; color:{text}; }}
        [data-testid="stMarkdownContainer"],
        [data-testid="stWidgetLabel"],
        [data-testid="stMetric"],
        [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] *,
        [data-baseweb="select"], input, textarea {{ font-family:{font}; }}
        [data-testid="stAppViewContainer"] h1,
        [data-testid="stAppViewContainer"] h2,
        [data-testid="stAppViewContainer"] h3,
        [data-testid="stAppViewContainer"] h4,
        [data-testid="stAppViewContainer"] h5,
        [data-testid="stAppViewContainer"] h6 {{ font-family:{font} !important; }}
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
        .health-score {{
            width:100%; box-sizing:border-box; background:{surface};
            border:2px solid var(--score-color); border-radius:14px;
            padding:16px 20px; margin:10px 0 18px; display:grid;
            grid-template-columns:1fr auto; gap:4px 18px;
        }}
        .health-score span {{ color:{muted}; font-weight:600; }}
        .health-score strong {{ color:var(--score-color); font-size:1.25rem; }}
        .health-score small {{ color:{muted}; grid-column:1/-1; }}
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
        [data-testid="stElementToolbar"] button,
        [data-testid="stElementToolbar"] svg {{
            color:{neutral_icon} !important; fill:{neutral_icon} !important;
        }}
        [data-testid="stHeaderActionElements"] button,
        [data-testid="stHeaderActionElements"] a,
        [data-testid="stHeaderActionElements"] svg,
        [data-testid="stToolbar"] button,
        [data-testid="stToolbar"] a,
        [data-testid="stToolbar"] svg {{
            color:{neutral_icon} !important; fill:{neutral_icon} !important;
            stroke:{neutral_icon} !important;
        }}
        [data-testid="stSlider"] [role="slider"] {{
            background:{accent} !important; border-color:{accent} !important;
        }}
        [data-baseweb="slider"] [role="slider"] {{
            background:{accent} !important; border-color:{accent} !important;
            box-shadow:0 0 0 1px {accent} !important;
        }}
        [data-baseweb="slider"] > div > div:nth-child(2),
        [data-baseweb="slider"] > div > div:nth-child(3) {{
            background:{accent} !important;
        }}
        [data-baseweb="slider"] div[style*="background"] {{
            background-color:{accent} !important;
        }}
        [data-testid="stSlider"] [role="group"] > div:first-child > div:first-child {{
            background:{secondary} !important; background-image:none !important;
        }}
        [data-testid="stSlider"] [role="group"] > div:first-child > div:has(input[type="range"]) {{
            background:{accent} !important; background-image:none !important;
            outline:none !important; box-shadow:none !important;
        }}
        [data-testid="stSlider"] [role="group"] > div:first-child
        > div:has(input[type="range"]):focus,
        [data-testid="stSlider"] [role="group"] > div:first-child
        > div:has(input[type="range"]):focus-within,
        [data-testid="stSlider"] input[type="range"]:focus {{
            outline:none !important; box-shadow:none !important;
        }}
        [data-testid="stSlider"] [data-testid="stTickBar"] + div,
        [data-testid="stToggle"] [role="switch"][aria-checked="true"] {{
            background:{accent} !important;
        }}
        [data-baseweb="checkbox"] input:checked + div,
        [data-testid="stCheckbox"] input:checked + div {{
            background:{accent} !important; border-color:{neutral_border} !important;
        }}
        [data-testid="stCheckbox"] label:has(input:checked) span:first-of-type,
        [data-baseweb="checkbox"] label:has(input:checked) span:first-of-type {{
            background:{accent} !important; border-color:{neutral_border} !important;
        }}
        [data-testid="stCheckbox"] label:has(input:checked) > span + div {{
            background:{accent} !important; border-color:{neutral_border} !important;
        }}
        [data-testid="stSegmentedControl"] button[aria-pressed="true"],
        [data-baseweb="button-group"] button[aria-pressed="true"],
        [data-testid="stSegmentedControl"] [role="radio"][aria-checked="true"],
        [data-testid="stSegmentedControl"] label:has(input:checked) {{
            background:{accent} !important; border-color:{accent} !important;
            color:#FFFFFF !important;
        }}
        [data-testid="stSegmentedControl"] button[aria-pressed="true"] *,
        [data-testid="stSegmentedControl"] label:has(input:checked) * {{
            color:#FFFFFF !important;
        }}
        [data-testid="stBaseButton-segmented_controlActive"],
        button[kind="segmented_controlActive"] {{
            background:{accent} !important; border-color:{accent} !important;
            color:#FFFFFF !important;
        }}
        [data-testid="stButtonGroup"] [role="radio"][aria-checked="true"] {{
            background:{accent} !important; border-color:{neutral_border} !important;
            color:{accent_text} !important;
        }}
        [data-testid="stButtonGroup"] [role="radio"][aria-checked="true"] * {{
            color:{accent_text} !important;
        }}
        [data-testid="stButtonGroup"] [role="radio"][aria-checked="false"] {{
            background:{surface} !important; border-color:{neutral_border} !important;
            color:{text} !important;
        }}
        [data-testid="stButtonGroup"] [role="radio"][aria-checked="false"] * {{
            color:{text} !important;
        }}
        [data-testid="stDateInput"] [data-baseweb="input"],
        [data-testid="stDateInput"] input {{
            border-color:{neutral_border} !important; caret-color:{text} !important;
            color:{text} !important; -webkit-text-fill-color:{text} !important;
        }}
        [data-testid="stDateInput"] [role="spinbutton"],
        [data-testid="stDateInput"] [role="group"],
        [data-testid="stDateInput"] [role="group"] * {{
            color:{neutral_icon} !important; -webkit-text-fill-color:{neutral_icon} !important;
        }}
        [data-testid="stDateInput"] button,
        [data-testid="stDateInput"] svg {{
            color:{neutral_icon} !important; fill:{neutral_icon} !important;
            stroke:{neutral_icon} !important;
        }}
        [data-baseweb="calendar"] [aria-selected="true"],
        [role="dialog"] [role="gridcell"][aria-selected="true"],
        [role="dialog"] button[data-selected="true"] {{
            background:{neutral_surface} !important; color:{neutral_icon} !important;
            border-color:{neutral_border} !important;
        }}
        [data-testid="stNumberInput"] button,
        [data-testid="stNumberInput"] button:hover,
        [data-testid="stNumberInput"] button:focus {{
            background:{surface} !important; border-color:{neutral_border} !important;
            color:{text} !important; outline:none !important; box-shadow:none !important;
        }}
        [data-testid="stNumberInput"] button svg {{
            color:{neutral_icon} !important; fill:{neutral_icon} !important;
            stroke:{neutral_icon} !important;
        }}
        [data-testid="stTextInput"] [data-baseweb="input"],
        [data-testid="stTextInput"] [data-baseweb="base-input"],
        [data-testid="stTextInput"] input {{
            background:{surface} !important; color:{text} !important;
            -webkit-text-fill-color:{text} !important;
            caret-color:{text} !important; border-color:{neutral_border} !important;
            opacity:1 !important;
        }}
        [data-testid="stTextInput"] input::placeholder {{
            color:{muted} !important; -webkit-text-fill-color:{muted} !important;
            opacity:1 !important;
        }}
        [data-testid="stTextInput"] input::selection {{
            background:{accent} !important; color:{accent_text} !important;
            -webkit-text-fill-color:{accent_text} !important;
        }}
        [data-testid="stTextInput"] input:disabled {{
            color:{muted} !important; -webkit-text-fill-color:{muted} !important;
            opacity:1 !important;
        }}
        [data-testid="stTextArea"] [data-baseweb="textarea"],
        [data-testid="stTextArea"] textarea {{
            background:{surface} !important; color:{text} !important;
            -webkit-text-fill-color:{text} !important;
            caret-color:{text} !important; border-color:{neutral_border} !important;
            opacity:1 !important;
        }}
        [data-testid="stTextArea"] textarea::placeholder {{
            color:{neutral_icon} !important; -webkit-text-fill-color:{neutral_icon} !important;
            opacity:.8 !important;
        }}
        [data-testid="stTextArea"] textarea::selection {{
            background:{accent} !important; color:{accent_text} !important;
            -webkit-text-fill-color:{accent_text} !important;
        }}
        input[type="date"]::-webkit-calendar-picker-indicator {{
            opacity:1; accent-color:{neutral_icon};
        }}
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
        [data-testid="stSidebarCollapseButton"] span,
        [data-testid="stSidebarHeader"] button span {{
            font-family:"Material Symbols Rounded", "Material Symbols Outlined" !important;
            color:{sidebar_icon} !important; -webkit-text-fill-color:{sidebar_icon} !important;
            opacity:1 !important; font-size:1.5rem !important;
            font-variation-settings:"FILL" 0, "wght" 600, "GRAD" 0, "opsz" 24;
        }}
        [data-testid="stSidebarCollapsedControl"] svg,
        [data-testid="stSidebarCollapseButton"] svg,
        [data-testid="stSidebarHeader"] button svg {{
            color:{sidebar_icon} !important; fill:{sidebar_icon} !important;
            stroke:{sidebar_icon} !important; opacity:1 !important;
        }}
        a {{ color:{accent}; }}
        {dark_overrides}

        /* Keep Streamlit's own controls neutral and independent from the app palette. */
        [data-testid="stHeaderActionElements"] button,
        [data-testid="stHeaderActionElements"] button:hover,
        [data-testid="stHeaderActionElements"] button:focus,
        [data-testid="stHeaderActionElements"] button:active,
        [data-testid="stHeaderActionElements"] a,
        [data-testid="stHeaderActionElements"] a:hover,
        [data-testid="stHeaderActionElements"] a:focus,
        [data-testid="stToolbar"] button,
        [data-testid="stToolbar"] button:hover,
        [data-testid="stToolbar"] button:focus,
        [data-testid="stToolbar"] button:active,
        [data-testid="stToolbar"] a,
        [data-testid="stToolbar"] a:hover,
        [data-testid="stToolbar"] a:focus,
        [data-testid="stStatusWidget"] button,
        [data-testid="stStatusWidget"] button:hover,
        [data-testid="stStatusWidget"] button:focus,
        [data-testid="stStatusWidget"] button:active,
        [data-testid="stAppDeployButton"] button,
        [data-testid="stAppDeployButton"] button:hover,
        [data-testid="stAppDeployButton"] button:focus,
        [data-testid="stAppDeployButton"] button:active {{
            background:transparent !important;
            background-color:transparent !important;
            background-image:none !important;
            border:0 !important;
            border-color:transparent !important;
            border-radius:0 !important;
            outline:0 !important;
            box-shadow:none !important;
            color:{neutral_icon} !important;
        }}
        [data-testid="stHeaderActionElements"] svg,
        [data-testid="stToolbar"] svg,
        [data-testid="stStatusWidget"] svg,
        [data-testid="stAppDeployButton"] svg,
        [data-testid="stSpinner"] svg {{
            color:{neutral_icon} !important;
            fill:{neutral_icon} !important;
            stroke:{neutral_icon} !important;
        }}
        [data-testid="stSpinner"] {{
            color:{neutral_icon} !important;
            --primary-color:{neutral_icon} !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
