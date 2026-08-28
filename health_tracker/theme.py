from __future__ import annotations

import re
from base64 import b64encode
from pathlib import Path

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


def derived_palette(
    mode: str, accent: str, overrides: dict[str, str] | None = None
) -> dict[str, str | list[str]]:
    accent = normalize_color(accent)
    surface = _mix(accent, "#000000", 0.72)
    palette: dict[str, str | list[str]] = {
        "accent": accent,
        "background": _mix(accent, "#000000", 0.84),
        "surface": surface,
        "secondary": surface,
        "foreground": _mix(accent, "#FFFFFF", 0.9),
        "muted": _mix(accent, "#FFFFFF", 0.55),
        "link": _mix(accent, "#FFFFFF", 0.42),
        "input": "#202124",
        "border": "#666666",
        "grid": _mix(accent, "#FFFFFF", 0.38),
        "series": [
            accent,
            _mix(accent, "#FFFFFF", 0.38),
            _mix(accent, "#FFFFFF", 0.65),
        ],
        "scale": [
            _mix(accent, "#000000", 0.45),
            accent,
            _mix(accent, "#FFFFFF", 0.68),
        ],
    }
    for key, color in (overrides or {}).items():
        if key in {"background", "surface", "foreground", "muted", "link", "border"}:
            palette[key] = normalize_color(color)
    palette["secondary"] = palette["surface"]
    return palette


def apply_theme(
    mode: str,
    accent: str,
    font_name: str,
    success_matches_accent: bool = False,
    palette_overrides: dict[str, str] | None = None,
) -> None:
    palette = derived_palette(mode, accent, palette_overrides)
    accent = str(palette["accent"])
    background = str(palette["background"])
    surface = str(palette["surface"])
    secondary = str(palette["secondary"])
    text = str(palette["foreground"])
    muted = str(palette["muted"])
    link_color = str(palette["link"])
    accent_rgb = ", ".join(str(int(accent[index : index + 2], 16)) for index in (1, 3, 5))
    red, green, blue = (int(accent[index : index + 2], 16) for index in (1, 3, 5))
    accent_text = "#111111" if (0.2126 * red + 0.7152 * green + 0.0722 * blue) > 150 else "#FFFFFF"
    success_background = accent if success_matches_accent else "#DDEFE0"
    success_text = accent_text if success_matches_accent else "#244C2A"
    success_border = accent if success_matches_accent else "#8FC99A"
    neutral_icon = "#D8D8D8"
    sidebar_icon = "#FFFFFF"
    neutral_border = str(palette["border"])
    neutral_surface = "#303030"
    input_surface = "#202124"
    input_text = "#FFFFFF"
    input_placeholder = "#C4C7C5"
    font = FONTS.get(font_name, FONTS["Modern sans"])
    garmin_logo = Path(__file__).resolve().parents[1] / "assets" / "logo" / "garmin.svg"
    garmin_logo_css = (
        'background-image:url("data:image/svg+xml;base64,'
        + b64encode(garmin_logo.read_bytes()).decode()
        + '") !important;'
        if garmin_logo.is_file()
        else ""
    )
    brand_mark = (
        Path(__file__).resolve().parents[1]
        / "assets"
        / "logo"
        / "health-journey-mark.svg"
    )
    brand_mark_css = (
        'background-image:url("data:image/svg+xml;base64,'
        + b64encode(brand_mark.read_bytes()).decode()
        + '") !important;'
        if brand_mark.is_file()
        else ""
    )
    dark_overrides = f"""
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
        [data-testid="stColorPickerPopover"] input {{
            background:#EAF4F1 !important;
            color:#16302B !important;
            -webkit-text-fill-color:#16302B !important;
            caret-color:#16302B !important;
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

        button[kind="secondary"] {{
            background-color:{surface}; color:{text}; border-color:{muted};
        }}
        button[kind="primary"] {{ color:#ffffff !important; }}
        [data-testid="stHeader"], [data-testid="stToolbar"] {{
            background-color:transparent !important;
        }}
        [data-testid="stHeader"] button,
        [data-testid="stToolbar"] button,
        [data-testid="stHeader"] a,
        [data-testid="stToolbar"] a,
        [data-testid="stHeader"] [role="button"],
        [data-testid="stToolbar"] [role="button"] {{
            background:transparent !important;
            background-color:transparent !important;
            border-color:transparent !important;
            color:#FFFFFF !important;
            -webkit-text-fill-color:#FFFFFF !important;
            box-shadow:none !important;
            outline:none !important;
            accent-color:auto !important;
        }}
        [data-testid="stHeader"] button *,
        [data-testid="stToolbar"] button *,
        [data-testid="stHeader"] a *,
        [data-testid="stToolbar"] a * {{
            color:#FFFFFF !important;
            -webkit-text-fill-color:#FFFFFF !important;
        }}
        [data-testid="stHeader"] svg,
        [data-testid="stToolbar"] svg {{
            color:#FFFFFF !important;
            fill:currentColor !important;
            -webkit-text-fill-color:#FFFFFF !important;
        }}
        [data-testid="stHeader"] svg path[fill="none"],
        [data-testid="stToolbar"] svg path[fill="none"] {{
            fill:none !important;
        }}
        [data-testid="stHeader"] a svg path:not([fill="none"]),
        [data-testid="stToolbar"] a svg path:not([fill="none"]) {{
            fill:#FFFFFF !important; color:#FFFFFF !important;
        }}
        hr {{ border-color:{muted}55; }}
        """
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
        [data-testid="stSidebar"] {{ background:{accent}; }}
        div[data-testid="stMetric"], .quote-card, .motivation-card {{
            background:{surface}; border:1px solid {accent}33; border-radius:16px; padding:18px;
            box-shadow:0 5px 20px #0000000d;
        }}
        .nutrition-metric-card {{
            min-height:132px; box-sizing:border-box;
            background:color-mix(in srgb, var(--nutrient-color) 30%, {surface});
            border:1px solid var(--nutrient-color); border-radius:16px;
            padding:16px; box-shadow:0 5px 20px #0000000d;
        }}
        .nutrition-metric-title {{ color:{text}; font-size:.9rem; font-weight:600; }}
        .nutrition-metric-value {{
            color:{text}; font-size:2rem; font-weight:700; line-height:1.25; margin:.2rem 0;
        }}
        .nutrition-metric-status {{ color:{text}; font-size:.9rem; font-weight:650; }}
        .palette-preview {{
            display:grid; grid-template-columns:repeat(auto-fit,minmax(112px,1fr));
            gap:10px; margin:.5rem 0 1.25rem;
        }}
        .palette-swatch {{
            min-width:0; background:{surface}; border:1px solid {neutral_border};
            border-radius:10px; padding:8px;
        }}
        .palette-swatch-color {{
            display:block; height:40px; border:1px solid {neutral_border};
            border-radius:7px; margin-bottom:7px;
        }}
        .palette-swatch strong {{
            display:block; color:{text}; font-size:.78rem; line-height:1.25;
        }}
        .palette-swatch small {{ color:{muted}; font-size:.72rem; }}
        .quote-card {{ padding:32px; margin:12px 0 16px; }}
        .motivation-card {{ padding:24px 32px; margin:0 0 28px; }}
        .sport-watermark {{
            position:fixed; left:20rem; bottom:1.5rem; width:min(25vw,350px);
            opacity:.065; pointer-events:none; z-index:0;
        }}
        .sport-watermark svg {{ display:block; width:100%; height:auto; }}
        @media (max-width:768px) {{
            .sport-watermark {{ left:1rem; bottom:1rem; width:210px; opacity:.055; }}
            .nutrition-metric-card {{
                width:100%; min-height:0; margin:0 0 10px; padding:11px 14px;
                border-radius:12px; display:grid;
                grid-template-columns:minmax(0,1fr) auto;
                grid-template-areas:"title value" "status status";
                align-items:center; column-gap:12px; row-gap:2px;
            }}
            .nutrition-metric-title {{
                grid-area:title; min-width:0; font-size:.82rem; line-height:1.25;
            }}
            .nutrition-metric-value {{
                grid-area:value; margin:0; font-size:1.35rem; line-height:1.15;
                text-align:right;
            }}
            .nutrition-metric-status {{
                grid-area:status; font-size:.8rem; line-height:1.25;
            }}
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
        .quote-card a, .quote-card a:visited, .quote-card a:hover, .quote-card a:focus {{
            color:{link_color} !important; -webkit-text-fill-color:{link_color} !important;
        }}
        .research-motivation-label {{
            color:{accent}; letter-spacing:.12em; font-size:.7rem; font-weight:700;
            margin-top:1.5rem;
        }}
        .research-motivation {{
            color:{text}; font-size:clamp(1.35rem,3vw,2rem); line-height:1.4;
            font-weight:600; margin-top:.35rem;
        }}
        .stButton > button, .stFormSubmitButton > button {{ border-radius:10px; }}
        .st-key-login_shell {{
            margin-top:clamp(1rem,4vh,2.5rem); padding:clamp(1.5rem,4vw,2.5rem);
            background:{surface}; border:1px solid {neutral_border}; border-radius:22px;
            box-shadow:0 22px 70px #00000040;
        }}
        .st-key-login_shell h1 {{
            margin:.25rem 0 .35rem; font-size:clamp(2rem,4vw,2.8rem); line-height:1.05;
        }}
        .st-key-login_brand_mark {{
            display:flex; align-items:center; justify-content:center;
            min-height:5.5rem; margin:0 0 .65rem;
        }}
        .st-key-login_brand_mark [data-testid="stImage"] {{
            display:flex; justify-content:center; width:100%;
        }}
        .st-key-login_brand_mark img {{
            display:block; width:3.4rem; height:auto;
        }}
        .st-key-login_shell [data-testid="stCaptionContainer"] {{ margin-bottom:1.3rem; }}
        .st-key-login_shell [data-testid="stForm"] {{ padding:0; border:0; }}
        .st-key-login_shell [data-testid="stFormSubmitButton"] {{ margin-top:.55rem; }}
        .st-key-login_shell .login-wordmark {{
            margin:0 !important; color:{accent} !important; font-size:.72rem;
            -webkit-text-fill-color:{accent} !important;
            font-weight:800; letter-spacing:.18em;
        }}
        .st-key-login_shell .login-footnote {{
            margin:1.15rem 0 0 !important; color:{muted} !important;
            -webkit-text-fill-color:{muted} !important;
            font-size:.78rem; line-height:1.4; text-align:center;
        }}
        .st-key-google_sign_in button {{ min-height:2.5rem !important; }}
        .st-key-google_sign_in button p {{
            display:flex !important; align-items:center !important;
            justify-content:center !important; gap:.45rem !important;
            width:max-content !important; white-space:nowrap !important;
        }}
        .st-key-google_sign_in button img {{
            flex:0 0 auto; margin:0 !important;
        }}
        .st-key-login_shell [data-testid="stTextInputRootElement"],
        .st-key-login_shell [data-baseweb="input"] {{
            background:{background} !important; background-color:{background} !important;
        }}
        .st-key-login_shell input:-webkit-autofill {{
            -webkit-box-shadow:0 0 0 1000px {background} inset !important;
            -webkit-text-fill-color:{text} !important;
        }}
        [data-testid="stSidebarUserContent"] {{
            position:relative; min-height:calc(100vh - 1rem);
        }}
        .st-key-sidebar_brand_mark {{
            display:flex; align-items:center; justify-content:center;
            min-height:4rem; margin:.15rem 0 .85rem;
        }}
        .st-key-sidebar_brand_mark [data-testid="stImage"] {{
            display:flex; justify-content:center; width:100%;
        }}
        .st-key-sidebar_brand_mark img {{
            display:block; width:2.35rem; height:auto;
        }}
        .st-key-appearance_action,
        .st-key-sign_out_action {{
            position:absolute; right:0; left:0;
        }}
        .st-key-appearance_action {{
            bottom:7rem;
        }}
        .st-key-sign_out_action {{ bottom:4.7rem; }}
        .st-key-appearance_action a,
        .st-key-sign_out_action button {{
            width:100% !important; min-height:2.25rem; box-sizing:border-box;
            justify-content:flex-start !important; padding:.375rem .5rem !important;
            background:transparent !important; color:{accent_text} !important;
            border:0 !important; border-radius:.5rem !important;
            text-align:left !important; box-shadow:none !important;
        }}
        .st-key-appearance_action a:hover,
        .st-key-appearance_action a:focus,
        .st-key-sign_out_action button:hover,
        .st-key-sign_out_action button:focus {{
            background:{accent_text}14 !important; color:{accent_text} !important;
            border:0 !important; box-shadow:none !important;
        }}
        .st-key-appearance_action a p,
        .st-key-sign_out_action button p {{
            width:100%; margin:0; color:{accent_text} !important; text-align:left !important;
        }}
        .st-key-sign_out_action button > div {{
            width:100% !important; justify-content:flex-start !important;
            text-align:left !important;
        }}
        .st-key-smartwatch_load button {{
            background-color:#FFFFFF !important; {garmin_logo_css}
            background-repeat:no-repeat !important; background-position:center !important;
            background-size:138px auto !important; border-color:#00A6CE !important;
            color:#111111 !important; min-height:3rem !important;
            height:3rem !important;
        }}
        .st-key-smartwatch_intro,
        .st-key-smartwatch_load,
        .st-key-smartwatch_result {{
            box-sizing:border-box; padding-inline:1rem;
        }}
        .st-key-smartwatch_load button:hover,
        .st-key-smartwatch_load button:focus {{
            background-color:#F2FAFC !important; border-color:#007CC3 !important;
            color:#111111 !important; box-shadow:0 0 0 2px #007CC344 !important;
        }}
        .st-key-smartwatch_load button * {{ color:#111111 !important; }}
        .st-key-smartwatch_load button p {{ opacity:0 !important; font-size:0 !important; }}
        .garmin-action-label {{
            color:{text}; font-weight:650; margin:.5rem 0 .35rem;
        }}
        button[kind="primary"], .stFormSubmitButton > button {{
            background:{accent} !important; border-color:{accent} !important;
        }}
        [data-testid="stAlert"] {{
            background:{surface} !important; color:{text} !important;
            border-color:{accent} !important;
        }}
        [data-testid="stAlert"] svg,
        [data-testid="stCheckbox"] svg {{ fill:{accent} !important; color:{accent} !important; }}
        .status-heading {{
            display:flex; align-items:center; flex-wrap:wrap; gap:.55rem;
            overflow:visible; position:relative; margin:0 0 .25rem;
        }}
        .status-heading h1,
        .status-heading h2,
        .status-heading h3 {{
            margin:0 !important; padding:0 !important;
        }}
        .status-heading-1 {{ margin-bottom:.45rem; }}
        .saved-status-badge {{
            display:inline-flex; align-items:center; justify-content:center;
            position:relative; flex:0 0 auto; width:1.25rem; height:1.25rem;
            box-sizing:border-box; border:1.5px solid {success_border};
            border-radius:50%; background:transparent; color:{success_border};
            font-size:.76rem; font-weight:800; line-height:1; cursor:help;
            outline:none; box-shadow:none;
        }}
        .saved-status-badge::after {{
            content:attr(data-message); position:absolute; top:calc(100% + .55rem);
            left:50%; z-index:1000; width:max-content;
            max-width:min(22rem, calc(100vw - 3rem)); padding:.55rem .7rem;
            box-sizing:border-box; border:1px solid {success_border}; border-radius:9px;
            background:{success_background}; color:{success_text};
            box-shadow:0 8px 24px #00000045; font-size:.78rem; font-weight:600;
            line-height:1.35; white-space:normal; text-align:left;
            opacity:0; visibility:hidden; pointer-events:none;
            transform:translate(-50%, -.15rem); transition:opacity .14s ease, transform .14s ease;
        }}
        .saved-status-badge:hover::after,
        .saved-status-badge:focus::after {{
            opacity:1; visibility:visible; transform:translate(-50%, 0);
        }}
        [data-testid="stProgressBarTrack"],
        [data-testid="stProgress"] [data-testid="stProgressBarTrack"],
        [data-testid="stProgressBar"] [data-testid="stProgressBarTrack"] {{
            background:#243E26 !important;
            background-color:#243E26 !important;
        }}
        [data-testid="stProgressBarTrack"] > div,
        [data-testid="stProgress"] [data-testid="stProgressBarTrack"] > div,
        [data-testid="stProgressBar"] [data-testid="stProgressBarTrack"] > div {{
            background:#4F8A55 !important;
            background-color:#4F8A55 !important;
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
        [data-baseweb="checkbox"] label:has(input:checked) > span:first-of-type {{
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
        [data-testid="stNumberInput"] button[aria-label*="clear" i],
        [data-testid="stNumberInput"] button[title*="clear" i] {{
            background:transparent !important; border:0 !important;
            border-radius:0 !important; outline:none !important; box-shadow:none !important;
        }}
        [data-testid="stNumberInput"] button[aria-label*="clear" i] svg,
        [data-testid="stNumberInput"] button[title*="clear" i] svg {{
            display:none !important;
        }}
        [data-testid="stNumberInput"] button[aria-label*="clear" i]::before,
        [data-testid="stNumberInput"] button[title*="clear" i]::before {{
            content:"×"; color:{neutral_icon}; font-size:1.15rem;
            font-weight:400; line-height:1;
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
        [data-testid="stExpandSidebarButton"],
        [data-testid="stSidebarCollapsedControl"] button,
        [data-testid="stSidebarCollapseButton"] button {{
            background:{surface} !important; color:{text} !important;
            border:1px solid {muted} !important; border-radius:9px !important;
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
        a, a:visited {{
            color:{link_color} !important;
            -webkit-text-fill-color:{link_color} !important;
        }}
        {dark_overrides}

        /* One rounded frame per field; inner BaseWeb controls must not draw a second frame. */
        [data-testid="stTextInput"] [data-baseweb="input"],
        [data-testid="stNumberInput"] [data-baseweb="input"],
        [data-testid="stDateInput"] [data-baseweb="input"],
        [data-testid="stTimeInput"] [data-baseweb="input"],
        [data-testid="stTextArea"] [data-baseweb="textarea"],
        [data-baseweb="select"] > div {{
            background:{input_surface} !important;
            background-color:{input_surface} !important;
            border:1px solid {neutral_border} !important;
            border-radius:8px !important;
            box-shadow:none !important;
            outline:none !important;
            overflow:hidden !important;
        }}
        [data-testid="stTextInput"] [data-baseweb="input"]:focus-within,
        [data-testid="stNumberInput"] [data-baseweb="input"]:focus-within,
        [data-testid="stDateInput"] [data-baseweb="input"]:focus-within,
        [data-testid="stTimeInput"] [data-baseweb="input"]:focus-within,
        [data-testid="stTextArea"] [data-baseweb="textarea"]:focus-within,
        [data-baseweb="select"] > div:focus-within {{
            border-color:{accent} !important;
            box-shadow:none !important;
            outline:none !important;
        }}
        [data-testid="stTextInput"] [data-baseweb="base-input"],
        [data-testid="stNumberInput"] [data-baseweb="base-input"],
        [data-testid="stDateInput"] [data-baseweb="base-input"],
        [data-testid="stTimeInput"] [data-baseweb="base-input"],
        [data-testid="stTextInput"] input,
        [data-testid="stNumberInput"] input,
        [data-testid="stDateInput"] input,
        [data-testid="stTimeInput"] input,
        [data-testid="stTextArea"] textarea,
        [data-baseweb="select"] input {{
            background:transparent !important;
            border:0 !important;
            border-radius:0 !important;
            box-shadow:none !important;
            outline:none !important;
            color:{input_text} !important;
            -webkit-text-fill-color:{input_text} !important;
            caret-color:{input_text} !important;
        }}
        [data-testid="stTextInput"] input::placeholder,
        [data-testid="stTextArea"] textarea::placeholder {{
            color:{input_placeholder} !important;
            -webkit-text-fill-color:{input_placeholder} !important;
            opacity:1 !important;
        }}
        [class*="st-key-weekly_focus_"] [data-baseweb="input"],
        [class*="st-key-weekly_barrier_"] [data-baseweb="input"] {{
            background:{background} !important;
            background-color:{background} !important;
            border:1px solid {neutral_border} !important;
            border-radius:10px !important;
            box-shadow:none !important;
            outline:none !important;
            overflow:hidden !important;
        }}
        [class*="st-key-weekly_focus_"] [data-baseweb="input"]:focus-within,
        [class*="st-key-weekly_barrier_"] [data-baseweb="input"]:focus-within {{
            border-color:{accent} !important;
        }}
        [class*="st-key-weekly_focus_"] [data-baseweb="base-input"],
        [class*="st-key-weekly_barrier_"] [data-baseweb="base-input"],
        [class*="st-key-weekly_focus_"] input,
        [class*="st-key-weekly_barrier_"] input {{
            background:transparent !important;
            background-color:transparent !important;
            border:0 !important;
            color:{input_text} !important;
            -webkit-text-fill-color:{input_text} !important;
            caret-color:{input_text} !important;
            opacity:1 !important;
        }}
        [class*="st-key-weekly_focus_"] input::placeholder,
        [class*="st-key-weekly_barrier_"] input::placeholder {{
            color:{input_placeholder} !important;
            -webkit-text-fill-color:{input_placeholder} !important;
            opacity:1 !important;
        }}
        [data-testid="stTextInput"] [data-baseweb="input"],
        [data-testid="stTextArea"] [data-baseweb="textarea"] {{
            background:{background} !important;
            background-color:{background} !important;
            border:1px solid {neutral_border} !important;
            border-radius:10px !important;
            overflow:hidden !important;
            box-shadow:none !important;
            outline:none !important;
            color:{input_text} !important;
            -webkit-text-fill-color:{input_text} !important;
            caret-color:{input_text} !important;
            opacity:1 !important;
        }}
        [data-testid="stTextInput"] [data-baseweb="input"]:focus-within,
        [data-testid="stTextArea"] [data-baseweb="textarea"]:focus-within {{
            border-color:{accent} !important;
            box-shadow:none !important;
        }}
        [data-testid="stTextInput"] [data-baseweb="input"] > div,
        [data-testid="stTextArea"] [data-baseweb="textarea"] > div,
        [data-testid="stTextInput"] [data-baseweb="base-input"],
        [data-testid="stTextArea"] [data-baseweb="base-input"],
        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea {{
            background:transparent !important;
            background-color:transparent !important;
            border:0 !important;
            border-radius:0 !important;
            box-shadow:none !important;
            outline:none !important;
            color:{input_text} !important;
            -webkit-text-fill-color:{input_text} !important;
            caret-color:{input_text} !important;
        }}
        [data-testid="stTextInput"] input::placeholder,
        [data-testid="stTextArea"] textarea::placeholder {{
            color:{input_placeholder} !important;
            -webkit-text-fill-color:{input_placeholder} !important;
            opacity:1 !important;
        }}
        [data-testid="stTextInput"] input:-webkit-autofill,
        [data-testid="stTextArea"] textarea:-webkit-autofill {{
            -webkit-box-shadow:0 0 0 1000px {input_surface} inset !important;
            -webkit-text-fill-color:{input_text} !important;
        }}
        [class*="st-key-food_note_"] textarea {{
            color:#FFFFFF !important;
            -webkit-text-fill-color:#FFFFFF !important;
            caret-color:#FFFFFF !important;
            font-weight:500 !important;
            opacity:1 !important;
        }}
        [class*="st-key-food_note_"] textarea::placeholder {{
            color:#FFFFFF !important;
            -webkit-text-fill-color:#FFFFFF !important;
            opacity:1 !important;
        }}
        [data-testid="stExpander"] details,
        [data-testid="stExpander"] details[open],
        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] details[open] summary,
        [data-testid="stExpander"] details > div {{
            background:{surface} !important;
            color:{text} !important;
            border-color:{neutral_border} !important;
        }}
        [data-testid="stExpander"] details {{
            overflow:hidden !important;
        }}
        [data-testid="stExpander"] details[open] >
        [data-testid="stExpanderDetails"] {{
            border-radius:0 0 7px 7px !important;
            overflow:hidden !important;
        }}
        [data-testid="stExpander"] summary:hover,
        [data-testid="stExpander"] summary:focus,
        [data-testid="stExpander"] details[open] summary:hover {{
            background:{secondary} !important;
            color:{text} !important;
            outline:none !important;
            box-shadow:none !important;
        }}
        [data-testid="stExpander"] summary *,
        [data-testid="stExpander"] details > div * {{
            color:{text} !important;
        }}
        [data-baseweb="popover"] > div,
        [role="listbox"] {{
            background:{surface} !important;
            color:{text} !important;
            border-color:{neutral_border} !important;
            box-shadow:0 8px 24px #00000024 !important;
        }}
        [role="option"],
        [role="option"] * {{
            background:{surface} !important;
            color:{text} !important;
            -webkit-text-fill-color:{text} !important;
        }}
        [role="option"]:hover,
        [role="option"][aria-selected="true"],
        [role="option"]:hover * ,
        [role="option"][aria-selected="true"] * {{
            background:{secondary} !important;
            color:{text} !important;
            -webkit-text-fill-color:{text} !important;
        }}
        [data-testid="stSelectbox"] [data-baseweb="select"] {{
            background:{surface} !important;
            background-color:{surface} !important;
            color:{text} !important;
            border:1px solid {neutral_border} !important;
            border-radius:8px !important;
            overflow:hidden !important;
            box-shadow:none !important;
        }}
        [data-testid="stSelectbox"] [data-baseweb="select"] > div,
        [data-testid="stSelectbox"] [data-baseweb="select"] > div:hover,
        [data-testid="stSelectbox"] [data-baseweb="select"] > div:focus-within {{
            background:{surface} !important;
            background-color:{surface} !important;
            color:{text} !important;
            border:0 !important;
            border-radius:0 !important;
            box-shadow:none !important;
        }}
        [data-testid="stSelectbox"] [data-baseweb="select"] > div * {{
            background:transparent !important;
            background-color:transparent !important;
        }}
        [data-testid="stSelectbox"] [data-baseweb="select"] input,
        [data-testid="stSelectbox"] [data-baseweb="select"] span,
        [data-testid="stSelectbox"] [data-baseweb="select"] p {{
            color:{text} !important;
            -webkit-text-fill-color:{text} !important;
        }}
        [data-testid="stSelectbox"] [data-baseweb="select"] svg {{
            color:{neutral_icon} !important;
            fill:{neutral_icon} !important;
        }}
        .st-key-additional_kpi [data-baseweb="select"] {{
            background:{background} !important;
            background-color:{background} !important;
            color:{text} !important;
            -webkit-text-fill-color:{text} !important;
            border:1px solid #FFFFFF !important;
            border-color:#FFFFFF !important;
            border-radius:8px !important;
            overflow:hidden !important;
            box-shadow:none !important;
            outline:none !important;
        }}
        .st-key-additional_kpi [data-baseweb="select"]:focus-within {{
            border:1px solid #FFFFFF !important;
            border-color:#FFFFFF !important;
            box-shadow:none !important;
            outline:none !important;
        }}
        .st-key-additional_kpi [data-baseweb="select"] > div,
        .st-key-additional_kpi [data-baseweb="select"] > div:focus-within,
        .st-key-additional_kpi [role="combobox"],
        .st-key-additional_kpi [role="combobox"]:focus,
        .st-key-additional_kpi [aria-haspopup="listbox"],
        .st-key-additional_kpi [aria-haspopup="listbox"]:focus {{
            background:transparent !important;
            background-color:transparent !important;
            border:0 !important;
            border-radius:0 !important;
            box-shadow:none !important;
            outline:none !important;
        }}
        .st-key-additional_kpi [data-baseweb="select"] span,
        .st-key-additional_kpi [data-baseweb="select"] p,
        [data-baseweb="popover"] [role="listbox"],
        [data-baseweb="popover"] [role="option"],
        [data-baseweb="popover"] [role="option"] * {{
            background-color:{background} !important;
            color:{text} !important;
            -webkit-text-fill-color:{text} !important;
        }}
        [data-baseweb="popover"] [role="option"]:hover,
        [data-baseweb="popover"] [role="option"][aria-selected="true"],
        [data-baseweb="popover"] [role="option"]:hover *,
        [data-baseweb="popover"] [role="option"][aria-selected="true"] * {{
            background-color:{secondary} !important;
            color:{text} !important;
            -webkit-text-fill-color:{text} !important;
        }}

        [data-testid="stTooltipIcon"],
        [data-testid="stTooltipIcon"] button,
        [data-testid="stWidgetLabel"] button[aria-label*="help" i] {{
            width:1.25rem !important;
            min-width:1.25rem !important;
            height:1.25rem !important;
            min-height:1.25rem !important;
            padding:0 !important;
            border:0 !important;
            border-radius:50% !important;
            background:transparent !important;
            box-shadow:none !important;
            outline:none !important;
        }}
        [data-testid="stTooltipIcon"] button:hover,
        [data-testid="stTooltipIcon"] button:focus,
        [data-testid="stWidgetLabel"] button[aria-label*="help" i]:hover,
        [data-testid="stWidgetLabel"] button[aria-label*="help" i]:focus {{
            border-radius:50% !important;
            background:{secondary} !important;
            box-shadow:none !important;
            outline:none !important;
        }}

        /* Keep help affordances circular even when their associated toggle is selected. */
        [data-testid="stTooltipIcon"],
        [data-testid="stTooltipIcon"] *,
        [data-testid="stWidgetLabel"] button[aria-label*="help" i],
        [data-testid="stWidgetLabel"] button[aria-label*="help" i] * {{
            border-radius:50% !important;
            border:0 !important;
            box-shadow:none !important;
            outline:none !important;
        }}

        .st-key-smartwatch_load button {{
            background-color:#FFFFFF !important; border-color:#00A6CE !important;
            color:#111111 !important;
        }}
        .st-key-smartwatch_load button:hover,
        .st-key-smartwatch_load button:focus {{
            background-color:#F2FAFC !important; border-color:#007CC3 !important;
            color:#111111 !important;
        }}
        .st-key-smartwatch_load button * {{ color:#111111 !important; }}

        .stButton > button,
        .stFormSubmitButton > button {{ width:100% !important; }}
        [class*="st-key-clear_"] button {{
            background:{background} !important;
            color:{text} !important;
            -webkit-text-fill-color:{text} !important;
            border:1px solid {neutral_border} !important;
            box-shadow:none !important;
        }}
        [class*="st-key-clear_"] button:hover,
        [class*="st-key-clear_"] button:focus {{
            background:{secondary} !important;
            color:{text} !important;
            -webkit-text-fill-color:{text} !important;
            border-color:{accent} !important;
            box-shadow:none !important;
        }}
        [class*="st-key-clear_"] button * {{
            color:{text} !important;
            -webkit-text-fill-color:{text} !important;
        }}

        /* Journal and coaching fields use the page colour and one rounded outer frame. */
        [class*="st-key-food_note_"] [data-testid="stTextAreaRootElement"],
        [class*="st-key-food_note_"] [data-baseweb="textarea"],
        [class*="st-key-weekly_focus_"] [data-testid="stTextInputRootElement"],
        [class*="st-key-weekly_focus_"] [data-baseweb="input"],
        [class*="st-key-weekly_barrier_"] [data-testid="stTextInputRootElement"],
        [class*="st-key-weekly_barrier_"] [data-baseweb="input"],
        [class*="st-key-weekly_if_then_"] [data-testid="stTextInputRootElement"],
        [class*="st-key-weekly_if_then_"] [data-baseweb="input"] {{
            box-sizing:border-box !important;
            background:{background} !important;
            background-color:{background} !important;
            border:1px solid {neutral_border} !important;
            border-radius:10px !important;
            overflow:hidden !important;
            box-shadow:none !important;
            outline:none !important;
        }}
        [class*="st-key-food_note_"] [data-testid="stTextAreaRootElement"]:focus-within,
        [class*="st-key-food_note_"] [data-baseweb="textarea"]:focus-within,
        [class*="st-key-weekly_focus_"] [data-testid="stTextInputRootElement"]:focus-within,
        [class*="st-key-weekly_focus_"] [data-baseweb="input"]:focus-within,
        [class*="st-key-weekly_barrier_"] [data-testid="stTextInputRootElement"]:focus-within,
        [class*="st-key-weekly_barrier_"] [data-baseweb="input"]:focus-within,
        [class*="st-key-weekly_if_then_"] [data-testid="stTextInputRootElement"]:focus-within,
        [class*="st-key-weekly_if_then_"] [data-baseweb="input"]:focus-within {{
            border-color:{accent} !important;
        }}
        [class*="st-key-food_note_"] [data-baseweb="textarea"] > div,
        [class*="st-key-food_note_"] [data-baseweb="base-input"],
        [class*="st-key-food_note_"] textarea,
        [class*="st-key-weekly_focus_"] [data-baseweb="input"] > div,
        [class*="st-key-weekly_focus_"] [data-baseweb="base-input"],
        [class*="st-key-weekly_focus_"] input,
        [class*="st-key-weekly_barrier_"] [data-baseweb="input"] > div,
        [class*="st-key-weekly_barrier_"] [data-baseweb="base-input"],
        [class*="st-key-weekly_barrier_"] input,
        [class*="st-key-weekly_if_then_"] [data-baseweb="input"] > div,
        [class*="st-key-weekly_if_then_"] [data-baseweb="base-input"],
        [class*="st-key-weekly_if_then_"] input {{
            background:transparent !important;
            background-color:transparent !important;
            border:0 !important;
            border-radius:0 !important;
            box-shadow:none !important;
            outline:none !important;
            color:#FFFFFF !important;
            -webkit-text-fill-color:#FFFFFF !important;
            caret-color:#FFFFFF !important;
            opacity:1 !important;
        }}
        [class*="st-key-food_note_"] textarea::placeholder,
        [class*="st-key-weekly_focus_"] input::placeholder,
        [class*="st-key-weekly_barrier_"] input::placeholder,
        [class*="st-key-weekly_if_then_"] input::placeholder {{
            color:#D8D8D8 !important;
            -webkit-text-fill-color:#D8D8D8 !important;
            opacity:1 !important;
        }}

        /* Current Streamlit dropdowns use React Aria rather than BaseWeb. */
        [data-testid="stSelectbox"] .react-aria-ComboBox > div {{
            box-sizing:border-box !important;
            background:{background} !important;
            background-color:{background} !important;
            border:1px solid {neutral_border} !important;
            border-radius:10px !important;
            overflow:hidden !important;
            box-shadow:none !important;
            outline:none !important;
        }}
        [data-testid="stSelectbox"] .react-aria-ComboBox > div:focus-within {{
            border-color:{accent} !important;
            box-shadow:none !important;
            outline:none !important;
        }}
        .st-key-additional_kpi .react-aria-ComboBox > div,
        .st-key-additional_kpi .react-aria-ComboBox > div:focus-within {{
            border:1px solid #FFFFFF !important;
            border-color:#FFFFFF !important;
            border-radius:10px !important;
            box-shadow:none !important;
            outline:none !important;
        }}
        [data-testid="stSelectbox"] .react-aria-ComboBox input,
        [data-testid="stSelectbox"] .react-aria-ComboBox button {{
            background:transparent !important;
            background-color:transparent !important;
            border:0 !important;
            border-radius:0 !important;
            box-shadow:none !important;
            outline:none !important;
            color:{text} !important;
            -webkit-text-fill-color:{text} !important;
        }}
        [data-testid="stSelectboxVirtualDropdown"] {{
            box-sizing:border-box !important;
            background:{background} !important;
            background-color:{background} !important;
            border:1px solid {neutral_border} !important;
            border-radius:10px !important;
            overflow:hidden !important;
            box-shadow:none !important;
        }}
        [data-testid="stSelectboxVirtualDropdown"] [role="listbox"],
        [data-testid="stSelectboxVirtualDropdown"] [role="option"],
        [data-testid="stSelectboxVirtualDropdown"] [role="option"] * {{
            background:{background} !important;
            background-color:{background} !important;
            color:{text} !important;
            -webkit-text-fill-color:{text} !important;
        }}
        [data-testid="stSelectboxVirtualDropdown"] [role="option"]:hover,
        [data-testid="stSelectboxVirtualDropdown"] [role="option"][aria-selected="true"],
        [data-testid="stSelectboxVirtualDropdown"] [role="option"]:hover *,
        [data-testid="stSelectboxVirtualDropdown"] [role="option"][aria-selected="true"] * {{
            background:{secondary} !important;
            background-color:{secondary} !important;
        }}

        /* React Aria date fields and calendars must use the selected palette, never teal. */
        [data-testid="stDateInput"] [data-testid="stDateInputField"] {{
            box-sizing:border-box !important;
            background:{background} !important;
            background-color:{background} !important;
            border:1px solid {neutral_border} !important;
            border-radius:10px !important;
            overflow:hidden !important;
            box-shadow:none !important;
            outline:none !important;
        }}
        [data-testid="stDateInput"] [data-testid="stDateInputField"]:focus-within {{
            border-color:{accent} !important;
            box-shadow:none !important;
            outline:none !important;
        }}
        [data-testid="stDateInputField"] .react-aria-DateField,
        [data-testid="stDateInputField"] [role="group"],
        [data-testid="stDateInputField"] input {{
            background:transparent !important;
            background-color:transparent !important;
            border:0 !important;
            box-shadow:none !important;
            outline:none !important;
            color:{text} !important;
            -webkit-text-fill-color:{text} !important;
        }}
        [data-testid="stDateInputField"] [role="spinbutton"]:focus {{
            background:{secondary} !important;
            background-color:{secondary} !important;
            color:{text} !important;
            -webkit-text-fill-color:{text} !important;
            border-radius:4px !important;
        }}
        [data-testid="stDateInputCalendar"] {{
            box-sizing:border-box !important;
            background:{background} !important;
            background-color:{background} !important;
            border:1px solid {neutral_border} !important;
            border-radius:10px !important;
            overflow:hidden !important;
            box-shadow:0 8px 24px #00000055 !important;
            color:{text} !important;
        }}
        [data-testid="stDateInputCalendar"] [role="application"],
        [data-testid="stDateInputCalendar"] [role="grid"],
        [data-testid="stDateInputCalendar"] [role="row"],
        [data-testid="stDateInputCalendar"] [role="gridcell"] {{
            background:transparent !important;
            background-color:transparent !important;
            color:{text} !important;
        }}
        [data-testid="stDateInputCalendar"] [role="button"] {{
            background:transparent !important;
            background-color:transparent !important;
            border:0 !important;
            box-shadow:none !important;
            outline:none !important;
            color:{text} !important;
            -webkit-text-fill-color:{text} !important;
        }}
        [data-testid="stDateInputCalendar"] [role="gridcell"] [role="button"]:hover,
        [data-testid="stDateInputCalendar"] [role="gridcell"] [role="button"]:focus {{
            background:{secondary} !important;
            background-color:{secondary} !important;
            color:{text} !important;
            -webkit-text-fill-color:{text} !important;
        }}
        [data-testid="stDateInputCalendar"] [role="gridcell"][aria-selected="true"]
        [role="button"],
        [data-testid="stDateInputCalendar"] [role="gridcell"] [data-selected="true"] {{
            background:{accent} !important;
            background-color:{accent} !important;
            color:{accent_text} !important;
            -webkit-text-fill-color:{accent_text} !important;
            border-color:{accent} !important;
            box-shadow:none !important;
            outline:none !important;
        }}
        [data-testid="stDateInputCalendar"] [role="gridcell"] [data-today="true"] {{
            border:1px solid {accent} !important;
        }}

        /* Success confirmations can use light green or match primary Save buttons. */
        [data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"])
        [data-testid="stAlertContainer"],
        [data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"])
        [data-testid="stAlertContentSuccess"] {{
            background:{success_background} !important;
            background-color:{success_background} !important;
            border-color:{success_border} !important;
            color:{success_text} !important;
            -webkit-text-fill-color:{success_text} !important;
        }}
        [data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]) *,
        [data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]) svg {{
            color:{success_text} !important;
            fill:{success_text} !important;
            stroke:{success_text} !important;
            -webkit-text-fill-color:{success_text} !important;
        }}

        /* The side menu uses the same base colour as primary Save buttons. */
        [data-testid="stSidebar"],
        [data-testid="stSidebar"] > div {{
            background:{accent} !important;
            background-color:{accent} !important;
        }}
        [data-testid="stSidebar"] * {{
            color:{accent_text} !important;
            -webkit-text-fill-color:{accent_text} !important;
        }}
        [data-testid="stSpinner"] [data-testid="stSpinnerIcon"],
        [data-testid="stSpinner"] [data-testid="stSpinnerIcon"] * {{
            color:{accent} !important;
            fill:{accent} !important;
            stroke:{accent} !important;
        }}

        /* This rule comes last so dark-mode sidebar inheritance cannot recolour the arrows. */
        [data-testid="stExpandSidebarButton"],
        [data-testid="stExpandSidebarButton"] *,
        [data-testid="stSidebarCollapsedControl"] button,
        [data-testid="stSidebarCollapsedControl"] button *,
        [data-testid="stSidebarCollapseButton"] button,
        [data-testid="stSidebarCollapseButton"] button *,
        [data-testid="stSidebarHeader"] button,
        [data-testid="stSidebarHeader"] button * {{
            color:{sidebar_icon} !important;
            -webkit-text-fill-color:{sidebar_icon} !important;
        }}
        [data-testid="stExpandSidebarButton"] svg,
        [data-testid="stSidebarCollapsedControl"] button svg,
        [data-testid="stSidebarCollapseButton"] button svg,
        [data-testid="stSidebarHeader"] button svg {{
            color:{sidebar_icon} !important;
            fill:{sidebar_icon} !important;
            stroke:{sidebar_icon} !important;
        }}

        /* Use the brand mark as the collapsed sidebar's reopen control. */
        [data-testid="stExpandSidebarButton"],
        [data-testid="stSidebarCollapsedControl"] button {{
            display:flex !important; visibility:visible !important; opacity:1 !important;
            position:relative !important; align-items:center !important;
            justify-content:center !important;
            width:2.75rem !important; min-width:2.75rem !important;
            height:2.75rem !important; min-height:2.75rem !important;
            background-color:transparent !important;
            border:0 !important; box-shadow:none !important;
        }}
        [data-testid="stExpandSidebarButton"]::before,
        [data-testid="stSidebarCollapsedControl"] button::before {{
            content:""; display:block; width:1.35rem; height:2.25rem;
            {brand_mark_css}
            background-repeat:no-repeat !important;
            background-position:center !important;
            background-size:contain !important;
        }}
        [data-testid="stExpandSidebarButton"] span,
        [data-testid="stExpandSidebarButton"] svg,
        [data-testid="stSidebarCollapsedControl"] button span,
        [data-testid="stSidebarCollapsedControl"] button svg {{
            visibility:hidden !important; opacity:0 !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
