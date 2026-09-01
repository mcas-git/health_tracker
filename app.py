from __future__ import annotations

import io
import json
import math
from datetime import datetime, timedelta
from html import escape

import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy.orm import Session

from health_tracker.analytics import (
    adaptive_target_review,
    bmi_status,
    evening_checkin_complete,
    excel_safe_data,
    health_journey_score,
    load_data,
    monthly_weight_goal,
    morning_checkin_complete,
    nutrition_period_bounds,
    projected_target_date,
    recent_kpi_table,
    weekly_coaching_summary,
    weight_milestones,
)
from health_tracker.auth import require_login, sign_out
from health_tracker.backups import (
    backup_filename,
    create_encrypted_backup,
    inspect_encrypted_backup,
    restore_encrypted_backup,
)
from health_tracker.config import LONDON, Profile, setting
from health_tracker.config import PROFILE as DEFAULT_PROFILE
from health_tracker.db import (
    apply_target_adjustment,
    engine,
    get_daily,
    get_nutrition,
    get_target_adjustment,
    get_weekly_plan,
    init_db,
    upsert_daily,
    upsert_weekly_plan,
)
from health_tracker.garmin import sync_day
from health_tracker.models import AppPreferences, GoalSettings
from health_tracker.nutrition import analyse_day, save_estimate
from health_tracker.quotes import QUOTES, weekly_item
from health_tracker.research import RESEARCH_INSIGHTS
from health_tracker.theme import (
    FONTS,
    apply_theme,
    collapse_sidebar_after_page_change,
    derived_palette,
    normalize_color,
)

PALETTE_PREFERENCES = {
    "background_color": "background",
    "surface_color": "surface",
    "text_color": "foreground",
    "muted_color": "muted",
    "link_color": "link",
    "border_color": "border",
}
PALETTE_WIDGETS = {
    "palette_background": "background",
    "palette_surface": "surface",
    "palette_text": "foreground",
    "palette_muted": "muted",
    "palette_link": "link",
    "palette_border": "border",
}
JOURNAL_STATUS_LABELS = {
    "Complete day": "complete",
    "Estimated complete day": "estimated",
    "Partial day": "partial",
}

st.set_page_config(
    page_title="Health Journey",
    page_icon="⚕️",
    layout="wide",
)


@st.cache_resource(show_spinner=False)
def initialize_database() -> bool:
    """Run schema creation and lightweight migrations once per app process."""
    init_db()
    return True


@st.cache_data(ttl=45, show_spinner=False)
def cached_load_data() -> pd.DataFrame:
    """Reuse the journey dataset briefly while navigating between pages."""
    return load_data()


def invalidate_data_cache() -> None:
    cached_load_data.clear()


PREFERENCE_CACHE_KEY = "_startup_preferences"
STARTUP_PREFERENCE_FIELDS = (
    "accent",
    "font_family",
    "smooth_charts",
    "success_matches_accent",
    "show_placeholders",
    "show_page_toggles",
    "age",
    "sex",
    "height_cm",
    "start_weight_kg",
    "target_weight_kg",
    "target_date",
    *PALETTE_PREFERENCES,
)


def startup_preferences() -> dict[str, object]:
    """Keep stable appearance/profile settings in this browser session."""
    if PREFERENCE_CACHE_KEY not in st.session_state:
        with Session(engine) as session:
            preferences = session.get(AppPreferences, 1)
            st.session_state[PREFERENCE_CACHE_KEY] = {
                field: getattr(preferences, field, None) for field in STARTUP_PREFERENCE_FIELDS
            }
    return st.session_state[PREFERENCE_CACHE_KEY]


def invalidate_preferences_cache() -> None:
    st.session_state.pop(PREFERENCE_CACHE_KEY, None)


initialize_database()
_preferences = startup_preferences()
_theme_values = (
    "dark",
    str(_preferences["accent"]),
    str(_preferences["font_family"]),
)
_palette_overrides = {
    palette_key: color
    for preference_key, palette_key in PALETTE_PREFERENCES.items()
    if (color := _preferences.get(preference_key))
}
_smooth_charts = bool(_preferences["smooth_charts"])
_success_matches_accent = bool(_preferences["success_matches_accent"])
_show_placeholders = bool(_preferences["show_placeholders"])
_show_page_toggles = bool(_preferences["show_page_toggles"])
_profile = Profile(
    age=int(_preferences["age"] or DEFAULT_PROFILE.age),
    sex=str(_preferences["sex"] or DEFAULT_PROFILE.sex),
    height_cm=float(_preferences["height_cm"] or DEFAULT_PROFILE.height_cm),
    start_weight_kg=float(_preferences["start_weight_kg"] or DEFAULT_PROFILE.start_weight_kg),
    target_weight_kg=float(_preferences["target_weight_kg"] or DEFAULT_PROFILE.target_weight_kg),
    target_date=_preferences["target_date"] or DEFAULT_PROFILE.target_date,
)
apply_theme(
    *_theme_values,
    _success_matches_accent,
    palette_overrides=_palette_overrides,
)
auth_context = require_login()


def app_palette() -> dict[str, str | list[str]]:
    return derived_palette(*_theme_values[:2], overrides=_palette_overrides)


def reset_palette_controls() -> None:
    generated = derived_palette("dark", normalize_color(st.session_state["base_palette_color"]))
    for widget_key, palette_key in PALETTE_WIDGETS.items():
        st.session_state[widget_key] = str(generated[palette_key])


def value(item, name, default=None):
    result = getattr(item, name, None) if item is not None else None
    return default if result is None else result


def clear_text(key: str) -> None:
    st.session_state[key] = ""


def status_heading(
    label: str,
    message: str | None = None,
    level: int = 1,
    help_text: str | None = None,
) -> None:
    """Render a heading with optional accessible saved-status and help badges."""
    if not message and not help_text:
        if level == 1:
            st.title(label)
        else:
            st.subheader(label)
        return
    safe_label = escape(label)
    help_badge = ""
    if help_text:
        safe_help = escape(help_text, quote=True)
        help_badge = (
            f'<span class="heading-help-badge" tabindex="0" role="note" '
            f'aria-label="{safe_help}" data-message="{safe_help}">?</span>'
        )
    saved_badge = ""
    if message:
        safe_message = escape(message, quote=True)
        saved_badge = (
            f'<span class="saved-status-badge" tabindex="0" role="status" '
            f'aria-label="{safe_message}" data-message="{safe_message}">✓</span>'
        )
    st.markdown(
        f'<div class="status-heading status-heading-{level}">'
        f"<h{level}>{safe_label}</h{level}>"
        f"{help_badge}{saved_badge}"
        f"</div>",
        unsafe_allow_html=True,
    )


def example_placeholder(example: str) -> str | None:
    return f"Example: {example}" if _show_placeholders else None


def rating_input(
    label: str,
    key: str,
    initial: int | None,
    control_key: str,
) -> int | None:
    """Render a nullable, directly editable rating bounded from 0 to 10."""
    with st.container(key=f"rating_control_{control_key}"):
        return st.number_input(
            label,
            min_value=0,
            max_value=10,
            value=max(0, min(10, int(initial))) if initial is not None else None,
            step=1,
            key=key,
        )


def kpi_goal(field: str) -> dict:
    sex_adjustment = 5 if _profile.sex == "male" else -161 if _profile.sex == "female" else -78
    goal_burn = round(
        (
            10 * _profile.target_weight_kg
            + 6.25 * _profile.height_cm
            - 5 * _profile.age
            + sex_adjustment
        )
        * 1.35
    )
    goal_bmi = _profile.target_weight_kg / ((_profile.height_cm / 100) ** 2)
    step_goal = 7000 if _profile.age >= 60 else 8000
    goals = {
        "bmi": {
            "value": goal_bmi,
            "direction": "lower",
            "label": f"{goal_bmi:.1f} BMI at the saved goal weight",
            "note": "The general healthy adult BMI range is 18.5–24.9; BMI is a screening tool.",
            "url": "https://www.nhs.uk/live-well/healthy-weight/bmi-calculator/",
        },
        "waist_cm": {
            "value": _profile.height_cm * 0.49,
            "direction": "lower",
            "label": f"{_profile.height_cm * 0.49:.1f} cm",
            "note": "This represents a waist-to-height ratio below 0.5.",
            "url": "https://www.nice.org.uk/guidance/ng246/chapter/Rationale-and-impact",
        },
        "steps": {
            "value": float(step_goal),
            "direction": "higher",
            "label": f"{step_goal:,} steps/day",
            "note": (
                "Evidence suggests benefits level off around 6,000–8,000 for older adults "
                "and 8,000–10,000 for younger adults."
            ),
            "url": "https://pubmed.ncbi.nlm.nih.gov/35247352/",
        },
        "sleep_hours": {
            "value": 7.0,
            "direction": "range",
            "upper": 9.0,
            "label": "7–9 hours",
            "note": "The NHS describes 7–9 hours as the usual range for healthy adults.",
            "url": "https://www.nhs.uk/every-mind-matters/mental-health-issues/sleep/",
        },
        "calories_burned": {
            "value": float(goal_burn),
            "direction": "lower",
            "label": f"about {goal_burn:,} kcal/day",
            "note": (
                "This is a personalised sedentary energy estimate at goal weight, not a "
                "clinical target."
            ),
            "url": "https://pubmed.ncbi.nlm.nih.gov/2305711/",
        },
        "mood": {
            "value": 10.0,
            "direction": "higher",
            "label": "10/10",
            "note": "This is the top of the app's personal rating scale, not a medical standard.",
            "url": None,
        },
        "energy": {
            "value": 10.0,
            "direction": "higher",
            "label": "10/10",
            "note": "This is the top of the app's personal rating scale, not a medical standard.",
            "url": None,
        },
        "resting_heart_rate": {
            "value": 60.0,
            "direction": "lower",
            "label": "60 bpm",
            "note": "The usual adult resting range is 60–100 bpm; lower is not always better.",
            "url": "https://www.bhf.org.uk/informationsupport/how-a-healthy-heart-works/your-heart-rate",
        },
        "systolic": {
            "value": 120.0,
            "direction": "lower",
            "label": "120 mmHg",
            "note": "This is the upper end of the NHS normal 90/60–120/80 range.",
            "url": "https://www.nhs.uk/conditions/high-blood-pressure/",
        },
        "diastolic": {
            "value": 80.0,
            "direction": "lower",
            "label": "80 mmHg",
            "note": "This is the upper end of the NHS normal 90/60–120/80 range.",
            "url": "https://www.nhs.uk/conditions/high-blood-pressure/",
        },
    }
    return goals[field]


def kpi_axis_domain(field: str, values: pd.Series) -> list[float]:
    goal = kpi_goal(field)
    first = float(values.iloc[0])
    if goal["direction"] == "higher":
        return [
            min(float(math.floor(first)), float(values.min())),
            max(float(goal["value"]), float(values.max())),
        ]
    if goal["direction"] == "range":
        return [
            min(float(goal["value"]), float(values.min())),
            max(float(goal["upper"]), float(values.max())),
        ]
    return [
        min(float(goal["value"]), float(values.min())),
        max(float(math.ceil(first)), float(values.max())),
    ]


def style_chart(chart):
    palette = app_palette()
    foreground = palette["foreground"]
    grid = palette["grid"]
    accent = palette["accent"]
    secondary = palette["series"][1]
    chart_font = FONTS.get(_theme_values[2], FONTS["Modern sans"])
    return (
        chart.configure(background="transparent", font=chart_font)
        .configure_view(strokeOpacity=0)
        .configure_line(color=accent)
        .configure_point(filled=True, fill=accent, stroke=accent, strokeWidth=2, size=72)
        .configure_rule(color=secondary)
        .configure_text(font=chart_font)
        .configure_axis(
            labelColor=foreground,
            titleColor=foreground,
            labelFont=chart_font,
            titleFont=chart_font,
            domainColor=grid,
            tickColor=grid,
            gridColor=grid,
            gridOpacity=0.35,
        )
        .configure_axisX(grid=False)
        .configure_legend(
            orient="bottom",
            direction="horizontal",
            labelColor=foreground,
            titleColor=foreground,
            labelFont=chart_font,
            titleFont=chart_font,
            symbolStrokeColor=foreground,
            padding=12,
        )
        .configure_title(color=foreground, font=chart_font)
        .configure_header(
            labelColor=foreground,
            titleColor=foreground,
            labelFont=chart_font,
            titleFont=chart_font,
        )
    )


def health_status_cards(data: pd.DataFrame, item, targets: dict[str, float]) -> None:
    indicator = health_journey_score(data, _profile, targets)
    if indicator:
        score, score_label, domains, _, _ = indicator
        score_color = {
            "Strong": "#4F8A55",
            "Watch": "#C5A33B",
            "Limited data": "#C5A33B",
            "Needs attention": "#B64B4B",
        }[score_label]
        domain_summary = " · ".join(
            f"{domain} {domain_score}" for domain, domain_score in domains.items()
        )
        st.markdown(
            f"<div class='health-score' style='--score-color:{score_color}'>"
            f"<span>Health indicator</span><strong>{score}/100 · {score_label}</strong>"
            f"<small>{domain_summary}. "
            f"<em>This is not a diagnosis.</em></small></div>",
            unsafe_allow_html=True,
        )
    weight_status = bmi_status(value(item, "bmi")) if item is not None else None
    if weight_status:
        status_label, status_tone, status_context = weight_status
        status_color = {
            "strong": "#4F8A55",
            "watch": "#C5A33B",
            "attention": "#B64B4B",
        }[status_tone]
        st.markdown(
            f"<div class='health-score' style='--score-color:{status_color}'>"
            f"<span>BMI weight status</span><strong>{item.bmi:.1f} · {status_label}</strong>"
            f"<small>{status_context}. <em>This is not a diagnosis.</em></small></div>",
            unsafe_allow_html=True,
        )


def home():
    london_day = datetime.now(LONDON).date()
    research = weekly_item(RESEARCH_INSIGHTS, london_day)
    quote = weekly_item(QUOTES, london_day)
    st.markdown(
        f"""
        <div class="motivation-card">
          <div class="research-motivation-label">THIS WEEK'S QUOTE</div>
          <div class="research-motivation">“{quote}”</div>
        </div>
        <div class="quote-card">
          <div class="quote-label">RESEARCH NOTE</div>
          <div class="quote-text">{research["insight"]}</div>
          <p><a href="{research["url"]}" target="_blank">{research["source"]}</a></p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def dashboard():
    st.title("Your health journey")
    st.caption(
        f"One calm day at a time · Goal: {_profile.target_weight_kg:g} kg by "
        f"{_profile.target_date:%d %b %Y}"
    )
    df = cached_load_data()
    latest_weight = (
        df.weight_kg.dropna().iloc[-1] if "weight_kg" in df and df.weight_kg.notna().any() else None
    )
    goal_range = _profile.start_weight_kg - _profile.target_weight_kg
    progress = (
        (_profile.start_weight_kg - latest_weight) / goal_range
        if latest_weight is not None and goal_range > 0
        else 0
    )
    projection = projected_target_date(df, _profile)
    dashboard_today = datetime.now(LONDON).date()
    projection_label = "Need more data"
    if projection:
        projection_label = (
            projection.strftime("%d %b")
            if projection.year in {dashboard_today.year, dashboard_today.year + 1}
            else projection.strftime("%d %b %Y")
        )
    recent_completion = weekly_coaching_summary(df, profile=_profile)["completion"]
    a, b, c, d = st.columns(4)
    a.metric("Current weight", f"{latest_weight:.1f} kg" if latest_weight else "—")
    b.metric("Goal progress", f"{max(0, min(100, progress * 100)):.0f}%")
    c.metric("7-day completion", f"{recent_completion}%")
    d.metric("Projected goal", projection_label)
    st.progress(max(0.0, min(1.0, progress)))
    month_goal = monthly_weight_goal(df, dashboard_today, _profile)
    if month_goal:
        with st.container(border=True):
            st.subheader(f"{month_goal['month_label']} checkpoint")
            month_cols = st.columns(3)
            month_cols[0].metric("End-of-month goal", f"{month_goal['target_weight_kg']:.1f} kg")
            month_cols[1].metric("Monthly progress", f"{month_goal['progress'] * 100:.0f}%")
            month_cols[2].metric("Remaining", f"{month_goal['remaining_kg']:.1f} kg")
            st.progress(month_goal["progress"])
            st.caption(
                f"On-plan checkpoint for {month_goal['goal_date']:%d %b %Y} · "
                f"{month_goal['days_left']} days remaining."
            )
    latest_measurements = (
        df.dropna(subset=["bmi"]).sort_values("entry_date").iloc[-1]
        if "bmi" in df and df["bmi"].notna().any()
        else None
    )
    with Session(engine) as session:
        dashboard_goals = session.get(GoalSettings, 1)
        health_targets = {
            "calories": dashboard_goals.calorie_target,
            "protein_g": dashboard_goals.protein_target_g,
            "fibre_g": dashboard_goals.fibre_target_g,
        }
    health_status_cards(df, latest_measurements, health_targets)

    if df.empty:
        st.info("Add your first daily entry to begin the dashboard.")
        return
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    chart_height = 320
    accent = _theme_values[1]
    palette = app_palette()
    series_colors = palette["series"]
    journey_start = pd.Timestamp(df.entry_date.min()).normalize()
    journey_end = max(pd.Timestamp(_profile.target_date), journey_start)
    date_scale = alt.Scale(domain=[journey_start, journey_end])
    month_ticks = list(pd.date_range(journey_start, journey_end, freq=pd.DateOffset(months=2)))
    date_axis = alt.Axis(
        title=None,
        format="%b",
        labelAngle=0,
        values=month_ticks,
        labelOverlap="greedy",
        grid=False,
    )
    # Keep the plotting areas aligned when dashboard charts are stacked. Without a
    # fixed axis extent, Vega-Lite reserves different widths for values such as
    # weight (three digits) and steps (five digits).
    dashboard_y_axis = alt.Axis(
        labels=True,
        ticks=False,
        domain=False,
        grid=True,
        minExtent=20,
        maxExtent=20,
        labelLimit=48,
        labelExpr="abs(datum.value) >= 10000 ? format(datum.value, '~s') : datum.label",
    )

    st.subheader("Weight trend")
    milestones, weekly_pace = weight_milestones(journey_start.date(), _profile)
    show_milestones = False
    if _show_page_toggles:
        show_milestones = st.toggle(
            "Show weight milestones",
            value=False,
            help=(
                f"Milestones use the {weekly_pace:.2f} kg/week pace required by your plan, "
                "within [NHS guidance of 0.5–1 kg/week](https://www.nhs.uk/live-well/"
                "healthy-weight/managing-your-weight/tips-to-help-you-lose-weight/)."
            ),
        )
    weight = df[["entry_date", "weight_kg"]].dropna().copy()
    if not weight.empty:
        weight_scale = alt.Scale(
            domain=[
                min(_profile.target_weight_kg, float(weight.weight_kg.min())),
                max(
                    _profile.target_weight_kg + 1,
                    math.ceil(float(weight.weight_kg.iloc[0])),
                    float(weight.weight_kg.max()),
                ),
            ],
            nice=False,
        )
        weight["display_value"] = (
            weight.weight_kg.rolling(7, min_periods=1).mean()
            if _smooth_charts
            else weight.weight_kg
        )
        weight_line = (
            alt.Chart(weight)
            .mark_line(
                point=False,
                color=accent,
                strokeWidth=4,
            )
            .encode(
                x=alt.X("entry_date:T", axis=date_axis, scale=date_scale),
                y=alt.Y(
                    "display_value:Q",
                    title=None,
                    axis=dashboard_y_axis,
                    scale=weight_scale,
                ),
                tooltip=[
                    alt.Tooltip("entry_date:T", title="Date"),
                    alt.Tooltip("display_value:Q", title="Weight (kg)", format=".1f"),
                ],
            )
        )
        weight_chart = weight_line
        weight_hover_targets = (
            alt.Chart(weight)
            .mark_point(opacity=0, size=180)
            .encode(
                x=alt.X("entry_date:T", axis=date_axis, scale=date_scale),
                y=alt.Y("weight_kg:Q", title=None, scale=weight_scale),
                tooltip=[
                    alt.Tooltip("entry_date:T", title="Date"),
                    alt.Tooltip("weight_kg:Q", title="Recorded weight (kg)", format=".1f"),
                ],
            )
        )
        weight_chart = weight_chart + weight_hover_targets
        if show_milestones:
            milestone_frame = pd.DataFrame(milestones)
            milestone_frame["milestone_date"] = pd.to_datetime(milestone_frame["milestone_date"])
            milestone_frame["display_label"] = milestone_frame.apply(
                lambda row: f"{row['label']} · {row['weight_kg']:.1f} kg", axis=1
            )
            milestone_points = (
                alt.Chart(milestone_frame)
                .mark_point(filled=True, size=150, color=series_colors[1])
                .encode(
                    x=alt.X("milestone_date:T", axis=date_axis, scale=date_scale),
                    y=alt.Y("weight_kg:Q", title=None, scale=weight_scale),
                    tooltip=[
                        alt.Tooltip("label:N", title="Milestone"),
                        alt.Tooltip("milestone_date:T", title="Date"),
                        alt.Tooltip("weight_kg:Q", title="Target weight", format=".1f"),
                    ],
                )
            )
            milestone_labels = (
                alt.Chart(milestone_frame)
                .mark_text(dy=-14, color=series_colors[1], fontWeight=600)
                .encode(
                    x=alt.X("milestone_date:T", axis=date_axis, scale=date_scale),
                    y=alt.Y("weight_kg:Q", title=None, scale=weight_scale),
                    text="display_label:N",
                )
            )
            weight_chart = weight_chart + milestone_points + milestone_labels
        st.altair_chart(
            style_chart(weight_chart.properties(height=chart_height)),
            width="stretch",
            theme=None,
        )
        latest_weight_row = weight.iloc[-1]
        weight_change = latest_weight_row["weight_kg"] - _profile.start_weight_kg
        st.caption(
            f"Latest recorded weight: {latest_weight_row['weight_kg']:.1f} kg on "
            f"{latest_weight_row['entry_date']:%d %b %Y}.<br>"
            f"This is {weight_change:+.1f} kg from the beginning.",
            unsafe_allow_html=True,
        )
    else:
        st.caption("No weight entries yet.")

    show_additional_kpi = False
    if _show_page_toggles:
        show_additional_kpi = st.toggle(
            "Show additional KPI",
            value=False,
            key="show_additional_kpi",
        )
    if show_additional_kpi:
        st.subheader("Additional KPI")
        labels = {
            "bmi": "BMI",
            "waist_cm": "Waist",
            "steps": "Steps",
            "sleep_hours": "Sleep",
            "calories_burned": "Calories burned",
            "mood": "Mood",
            "energy": "Energy",
            "resting_heart_rate": "Resting heart rate",
            "systolic": "Blood pressure (systolic)",
            "diastolic": "Blood pressure (diastolic)",
        }
        available = {
            label: field
            for field, label in labels.items()
            if field in df and df[field].notna().any()
        }
        if available:
            selected_label = st.selectbox(
                "Additional KPI", available, label_visibility="collapsed", key="additional_kpi"
            )
            selected_kpi = available[selected_label]
            recent = df[["entry_date", selected_kpi]].dropna().copy()
            recent["display_value"] = (
                recent[selected_kpi].rolling(7, min_periods=1).mean()
                if _smooth_charts
                else recent[selected_kpi]
            )
            kpi_scale = alt.Scale(
                domain=kpi_axis_domain(selected_kpi, recent[selected_kpi]), nice=False
            )
            kpi_chart = (
                alt.Chart(recent)
                .mark_line(
                    point=False,
                    color=accent,
                    strokeWidth=4,
                )
                .encode(
                    x=alt.X("entry_date:T", axis=date_axis, scale=date_scale),
                    y=alt.Y(
                        "display_value:Q",
                        title=None,
                        axis=dashboard_y_axis,
                        scale=kpi_scale,
                    ),
                    tooltip=[
                        alt.Tooltip("entry_date:T", title="Date"),
                        alt.Tooltip("display_value:Q", title=selected_label, format=".1f"),
                    ],
                )
                .properties(height=chart_height)
            )
            kpi_hover_targets = (
                alt.Chart(recent)
                .mark_point(opacity=0, size=180)
                .encode(
                    x=alt.X("entry_date:T", axis=date_axis, scale=date_scale),
                    y=alt.Y("display_value:Q", title=None, scale=kpi_scale),
                    tooltip=[
                        alt.Tooltip("entry_date:T", title="Date"),
                        alt.Tooltip("display_value:Q", title=selected_label, format=".1f"),
                    ],
                )
            )
            goal = kpi_goal(selected_kpi)
            goal_value = float(goal["value"])
            kpi_layers = kpi_chart + kpi_hover_targets
            if goal_value > kpi_scale.domain[0]:
                ideal_line = (
                    alt.Chart(pd.DataFrame({"ideal": [goal_value]}))
                    .mark_rule(color=series_colors[1], strokeDash=[6, 5], strokeWidth=2)
                    .encode(
                        y=alt.Y("ideal:Q", scale=kpi_scale),
                        tooltip=[alt.Tooltip("ideal:Q", title="Ideal value", format=".1f")],
                    )
                )
                kpi_layers = kpi_layers + ideal_line
            st.altair_chart(style_chart(kpi_layers), width="stretch", theme=None)
            reference = f" [Reference]({goal['url']})" if goal["url"] else ""
            st.caption(f"Goal anchor: **{goal['label']}** — {goal['note']}{reference}")
        else:
            st.caption("Add another measurement to display a recent KPI trend.")

    recent_table = recent_kpi_table(df)
    st.download_button(
        "Download recent KPI table",
        recent_table.to_csv(index=False).encode(),
        "recent-health-kpis.csv",
        "text/csv",
        use_container_width=True,
    )


def daily_entry():
    title_area = st.empty()
    error_area = st.empty()
    london_now = datetime.now(LONDON)
    today = london_now.date()
    update_another_day = False
    if _show_page_toggles:
        update_another_day = st.toggle(
            "Update a different day",
            value=False,
            help="Turn this on only to review or correct a previous daily check-in.",
            key="update_another_day",
        )
        if update_another_day:
            selected = st.date_input(
                "Date to update",
                value=today - timedelta(days=1),
                max_value=today,
                key="historical_entry_date",
            )
    if update_another_day:
        st.caption(f"Updating the saved check-in for {selected:%A, %d %B %Y}.")
    else:
        selected = today
        st.caption(f"Recording today · {today:%A, %d %B %Y}")
    smartwatch_confirmation = None
    smartwatch_error = None
    if requested_date := st.session_state.pop("smartwatch_sync_requested", None):
        try:
            with st.spinner("Loading smartwatch data…"):
                smartwatch_data = sync_day(requested_date)
            st.session_state.garmin_sync = {"date": requested_date, "data": smartwatch_data}
            revision_key = f"garmin_sync_revision_{requested_date.isoformat()}"
            st.session_state[revision_key] = int(st.session_state.get(revision_key, 0)) + 1
            smartwatch_confirmation = (
                f"Smartwatch data loaded for {requested_date:%d %b %Y} · "
                f"{len(smartwatch_data['activities'])} activities."
            )
        except Exception as exc:
            smartwatch_error = f"Smartwatch sync failed: {exc}"
    item = get_daily(selected)
    with title_area:
        status_heading("Check-in")
    with error_area:
        if smartwatch_error:
            st.error(smartwatch_error)
    sync_record = st.session_state.get("garmin_sync", {})
    synced = sync_record.get("data", {}) if sync_record.get("date") == selected else {}
    if synced and not smartwatch_confirmation:
        smartwatch_confirmation = (
            f"Smartwatch data loaded for {selected:%d %b %Y} · "
            f"{len(synced.get('activities', []))} activities."
        )
    date_key = selected.isoformat()
    sync_revision = int(st.session_state.get(f"garmin_sync_revision_{date_key}", 0))

    morning_complete = morning_checkin_complete(item)
    morning_label = "Morning check-in ✓" if morning_complete else "Morning check-in"
    with st.expander(morning_label, expanded=not morning_complete):
        st.caption("Record weight, waist and blood pressure. Blank fields are saved as missing.")
        with st.form(f"morning_form_{date_key}"):
            morning_item = item if update_another_day else None
            morning_key_mode = "historical" if update_another_day else "today_blank_v2"
            morning_keys = {
                field: f"{field}_{morning_key_mode}_{date_key}"
                for field in ("weight", "waist", "systolic", "diastolic")
            }
            c1, c2 = st.columns(2)
            weight_value = value(morning_item, "weight_kg")
            weight = c1.number_input(
                "Weight (kg)",
                min_value=30.0,
                max_value=250.0,
                value=float(weight_value) if weight_value is not None else None,
                step=0.1,
                key=morning_keys["weight"],
            )
            waist_value = value(morning_item, "waist_cm")
            waist = c2.number_input(
                "Waist (cm)",
                min_value=30.0,
                max_value=250.0,
                value=float(waist_value) if waist_value is not None else None,
                step=0.1,
                key=morning_keys["waist"],
            )
            bmi = weight / ((_profile.height_cm / 100) ** 2) if weight is not None else None
            c1, c2 = st.columns(2)
            systolic_value = value(morning_item, "systolic")
            systolic = c1.number_input(
                "Blood pressure · systolic",
                min_value=60,
                max_value=250,
                value=int(systolic_value) if systolic_value is not None else None,
                key=morning_keys["systolic"],
            )
            diastolic_value = value(morning_item, "diastolic")
            diastolic = c2.number_input(
                "Blood pressure · diastolic",
                min_value=30,
                max_value=160,
                value=int(diastolic_value) if diastolic_value is not None else None,
                key=morning_keys["diastolic"],
            )
            morning_submitted = st.form_submit_button(
                "Save morning check-in", use_container_width=True, type="primary"
            )
        if morning_submitted:
            with st.spinner("Saving morning check-in…"):
                upsert_daily(
                    {
                        "entry_date": selected,
                        "weight_kg": weight,
                        "waist_cm": waist,
                        "bmi": bmi,
                        "morning_submitted": True,
                        "systolic": systolic,
                        "diastolic": diastolic,
                    }
                )
                invalidate_data_cache()
            for morning_key in morning_keys.values():
                st.session_state.pop(morning_key, None)
            st.rerun()

    evening_complete = evening_checkin_complete(item)
    evening_label = "Evening check-in ✓" if evening_complete else "Evening check-in"
    with st.expander(evening_label, expanded=False):
        evening_item = item if update_another_day else None
        evening_key_mode = "historical" if update_another_day else "today_blank_v2"

        def smartwatch_value(field):
            imported = synced.get(field)
            return imported if imported is not None else value(evening_item, field)

        smartwatch_result_caption = None
        if synced:
            active_calories = synced.get("active_calories")
            resting_calories = synced.get("resting_calories")
            steps_label = "—" if synced.get("steps") is None else f"{synced['steps']:,}"
            sleep_label = (
                "—" if synced.get("sleep_hours") is None else f"{synced['sleep_hours']:.2f}"
            )
            heart_label = (
                "—"
                if synced.get("resting_heart_rate") is None
                else f"{synced['resting_heart_rate']}"
            )
            total_calorie_label = (
                "—"
                if synced.get("calories_burned") is None
                else f"{synced['calories_burned']:,.0f}"
            )
            calorie_detail = ""
            if active_calories is not None or resting_calories is not None:
                calorie_detail = (
                    f" · {active_calories or 0:,.0f} active + "
                    f"{resting_calories or 0:,.0f} resting kcal"
                )
            smartwatch_result_caption = (
                f"Garmin Connect returned {steps_label} steps · "
                f"{sleep_label} h sleep · {heart_label} bpm resting · "
                f"{total_calorie_label} total kcal{calorie_detail}."
            )

        with st.form(f"evening_form_{date_key}", border=False):
            evening_keys = {
                "resting_hr": f"resting_hr_{evening_key_mode}_{date_key}_{sync_revision}",
                "sleep": f"sleep_{evening_key_mode}_{date_key}_{sync_revision}",
                "steps": f"steps_{evening_key_mode}_{date_key}_{sync_revision}",
                "burned": f"burned_{evening_key_mode}_{date_key}_{sync_revision}",
                "mood": f"mood_{evening_key_mode}_{date_key}",
                "energy": f"energy_{evening_key_mode}_{date_key}",
                "cravings": f"cravings_{evening_key_mode}_{date_key}",
                "satisfaction": f"diet_satisfaction_{evening_key_mode}_{date_key}",
            }
            with st.container(border=True):
                with st.container(key="smartwatch_intro"):
                    status_heading(
                        "Smartwatch data",
                        smartwatch_confirmation,
                        level=3,
                    )
                with st.container(key="smartwatch_load"):
                    garmin_submitted = st.form_submit_button(
                        "Load smartwatch data from Garmin",
                        use_container_width=True,
                        key=f"load_garmin_{date_key}",
                    )
                if smartwatch_result_caption:
                    with st.container(key="smartwatch_result"):
                        st.caption(smartwatch_result_caption)
                c1, c2, c3, c4 = st.columns(4)
                resting_value = smartwatch_value("resting_heart_rate")
                resting_hr = c1.number_input(
                    "Resting heart rate",
                    30,
                    220,
                    value=int(resting_value) if resting_value is not None else None,
                    disabled=True,
                    key=evening_keys["resting_hr"],
                )
                sleep_value = smartwatch_value("sleep_hours")
                sleep = c2.number_input(
                    "Sleep (hours)",
                    0.0,
                    24.0,
                    value=float(sleep_value) if sleep_value is not None else None,
                    step=0.01,
                    disabled=True,
                    key=evening_keys["sleep"],
                )
                steps_value = smartwatch_value("steps")
                steps = c3.number_input(
                    "Steps",
                    0,
                    100000,
                    value=int(steps_value) if steps_value is not None else None,
                    disabled=True,
                    key=evening_keys["steps"],
                )
                burned_value = smartwatch_value("calories_burned")
                burned = c4.number_input(
                    "Total calories burned",
                    0,
                    10000,
                    value=int(burned_value) if burned_value is not None else None,
                    disabled=True,
                    key=evening_keys["burned"],
                )

            with st.container(border=True):
                st.subheader("Evening measurements")
                mood = rating_input(
                    "Mood", evening_keys["mood"], value(evening_item, "mood"), "mood"
                )
                energy = rating_input(
                    "Energy level",
                    evening_keys["energy"],
                    value(evening_item, "energy"),
                    "energy",
                )
                cravings = rating_input(
                    "Cravings",
                    evening_keys["cravings"],
                    value(evening_item, "cravings"),
                    "cravings",
                )
                satisfaction = rating_input(
                    "Diet satisfaction",
                    evening_keys["satisfaction"],
                    value(evening_item, "diet_satisfaction"),
                    "satisfaction",
                )

            with st.container(border=True):
                st.subheader("Habits")
                cols = st.columns(4)
                habits = {}
                for idx, (key, label) in enumerate(
                    [
                        ("gym", "Gym"),
                        ("cardio", "Cardio"),
                        ("supplements", "Supplements"),
                        ("protein_powder", "Protein powder"),
                        ("alcohol_free", "Alcohol-free"),
                        ("physio", "Physio"),
                        ("drugs", "Drugs"),
                        ("fasted", "Fasting"),
                    ]
                ):
                    habits[key] = cols[idx % 4].checkbox(
                        label,
                        value=bool(value(item, key, False)),
                        key=f"{key}_{date_key}",
                    )

            with st.container(border=True):
                st.subheader("Extenuating circumstances")
                circumstance_cols = st.columns(3)
                circumstances = {}
                for idx, (key, label) in enumerate(
                    [
                        ("illness", "Illness"),
                        ("injury", "Injury"),
                        ("travel", "Travel"),
                        ("unusual_day", "Unusual day"),
                        ("holiday", "Holiday"),
                    ]
                ):
                    circumstances[key] = circumstance_cols[idx % 3].checkbox(
                        label,
                        value=bool(value(item, key, False)),
                        key=f"{key}_{date_key}",
                    )

            evening_submitted = st.form_submit_button(
                "Save evening check-in", use_container_width=True, type="primary"
            )
        if garmin_submitted:
            st.session_state.smartwatch_sync_requested = selected
            st.rerun()
        elif evening_submitted:
            with st.spinner("Saving evening check-in…"):
                upsert_daily(
                    {
                        "entry_date": selected,
                        "resting_heart_rate": resting_hr,
                        "sleep_hours": sleep,
                        "steps": steps,
                        "calories_burned": burned,
                        "mood": mood,
                        "energy": energy,
                        "cravings": cravings,
                        "diet_satisfaction": satisfaction,
                        "evening_submitted": True,
                        **habits,
                        **circumstances,
                    }
                )
                invalidate_data_cache()
            st.session_state.pop("garmin_sync", None)
            for evening_key in evening_keys.values():
                st.session_state.pop(evening_key, None)
            st.rerun()


def weekly_coaching():
    weekly_saved_message = st.session_state.pop("weekly_plan_saved", None)
    status_heading("Weekly coaching", weekly_saved_message)
    st.caption("Review the trend, choose one focus, and plan around real-life barriers")
    today = datetime.now(LONDON).date()
    week_start = today - timedelta(days=today.weekday())
    df = cached_load_data()
    summary = weekly_coaching_summary(df, today, _profile)
    with Session(engine) as session:
        coaching_goals = session.get(GoalSettings, 1)
        current_calorie_target = coaching_goals.calorie_target
    target_review = adaptive_target_review(df, current_calorie_target, today, _profile)

    with st.container(border=True):
        st.subheader("This week's evidence")
        cols = st.columns(4)
        cols[0].metric("Days logged", f"{summary['logged_days']}/7")
        cols[1].metric("Completion", f"{summary['completion']}%")
        change = summary.get("weight_change")
        cols[2].metric("Weekly weight trend", f"{change:+.1f} kg" if change is not None else "—")
        cols[3].metric("Weight lost", f"{summary.get('loss_percent', 0):.1f}%")
        if summary.get("milestone"):
            st.success(f"Milestone reached: {summary['milestone']}% of starting weight lost.")
        if summary.get("plateau"):
            st.markdown(
                "<div class='neutral-note'>The four-week weight trend is broadly flat. Review "
                "logging completeness, portions, weekends and activity before lowering "
                "calories.</div>",
                unsafe_allow_html=True,
            )
        averages = summary.get("averages", {})
        habits = summary.get("habits", {})
        evidence = st.columns(4)
        evidence[0].metric("Average steps", f"{averages.get('steps', 0):,.0f}")
        evidence[1].metric("Average sleep", f"{averages.get('sleep_hours', 0):.1f} h")
        evidence[2].metric("Gym sessions", habits.get("gym", 0))
        evidence[3].metric("Alcohol-free days", habits.get("alcohol_free", 0))
        st.markdown(
            f"<div class='neutral-note'><strong>Suggested next action:</strong> "
            f"{summary['recommendation']}</div>",
            unsafe_allow_html=True,
        )
        st.caption(
            "How it is chosen: the first area needing attention is selected in this order—"
            "at least five logged days, protein averaging 1.5 g per kg of goal weight, "
            "7,000 daily steps, then seven hours of sleep. A sustained four-week weight "
            "plateau takes priority and prompts a review before calorie targets are changed."
        )

    target_update_message = st.session_state.pop("target_adjustment_saved", None)
    with st.container(border=True):
        status_heading("Adaptive target review", target_update_message, level=2)
        review_metrics = st.columns(4)
        review_metrics[0].metric("Usable food days", f"{target_review['usable_nutrition_days']}/7")
        review_metrics[1].metric("Weight entries", target_review["weight_measurements"])
        actual_loss = target_review["actual_weekly_loss_kg"]
        target_loss = target_review["target_weekly_loss_kg"]
        review_metrics[2].metric(
            "Weight-loss pace", f"{actual_loss:+.2f} kg/week" if actual_loss is not None else "—"
        )
        review_metrics[3].metric(
            "Planned weekly pace", f"{target_loss:.2f} kg/week" if target_loss is not None else "—"
        )
        st.markdown(
            f"<div class='neutral-note'><strong>{target_review['confidence']} confidence.</strong> "
            f"{target_review['message']}</div>",
            unsafe_allow_html=True,
        )
        applied_adjustment = get_target_adjustment(week_start)
        if applied_adjustment:
            st.caption(
                f"Applied this week: {applied_adjustment.previous_calorie_target:,} → "
                f"{applied_adjustment.new_calorie_target:,} kcal/day."
            )
        elif target_review["status"] == "ready":
            if st.button(
                f"Apply {target_review['recommended_calories']:,} kcal/day target",
                type="primary",
                use_container_width=True,
            ):
                with st.spinner("Updating reviewed targets…"):
                    apply_target_adjustment(
                        week_start=week_start,
                        recommended_calories=target_review["recommended_calories"],
                        actual_weekly_loss_kg=target_review["actual_weekly_loss_kg"],
                        target_weekly_loss_kg=target_review["target_weekly_loss_kg"],
                        usable_nutrition_days=target_review["usable_nutrition_days"],
                        weight_measurements=target_review["weight_measurements"],
                    )
                st.session_state.target_adjustment_saved = "Weekly target update applied."
                st.rerun()
        st.caption(
            "Partial journals are excluded. Suggestions are capped at 150 kcal/day per week "
            "with a 1,500 kcal/day floor, and are never applied automatically. The estimate "
            "uses your recent complete-day intake and 21-day weight trend."
        )

    saved = get_weekly_plan(week_start)
    with st.form("weekly_plan"):
        st.subheader("Plan this week")
        week_key = week_start.isoformat()
        c1, c2 = st.columns(2)
        gym_sessions = c1.number_input(
            "Planned gym sessions", 0, 7, int(value(saved, "planned_gym_sessions", 3))
        )
        cardio_sessions = c2.number_input(
            "Planned cardio sessions", 0, 7, int(value(saved, "planned_cardio_sessions", 2))
        )
        focus_key = f"weekly_focus_{week_key}"
        focus = st.text_input(
            "One behaviour to focus on",
            value=value(saved, "focus", ""),
            placeholder=example_placeholder("Take a 20-minute walk after lunch."),
            key=focus_key,
        )
        st.form_submit_button(
            "Clean response",
            key=f"clear_{focus_key}",
            on_click=clear_text,
            args=(focus_key,),
            use_container_width=True,
        )
        barrier_key = f"weekly_barrier_{week_key}"
        barrier = st.text_input(
            "Anticipated barrier",
            value=value(saved, "anticipated_barrier", ""),
            placeholder=example_placeholder("A late meeting could disrupt dinner."),
            key=barrier_key,
        )
        st.form_submit_button(
            "Clean response",
            key=f"clear_{barrier_key}",
            on_click=clear_text,
            args=(barrier_key,),
            use_container_width=True,
        )
        if_then_key = f"weekly_if_then_{week_key}"
        if_then = st.text_input(
            "If–then response",
            value=value(saved, "if_then_plan", ""),
            placeholder=example_placeholder(
                "If work runs late, then I will use the prepared dinner."
            ),
            key=if_then_key,
        )
        st.form_submit_button(
            "Clean response",
            key=f"clear_{if_then_key}",
            on_click=clear_text,
            args=(if_then_key,),
            use_container_width=True,
        )
        if st.form_submit_button("Save weekly plan", type="primary", use_container_width=True):
            with st.spinner("Saving weekly plan…"):
                upsert_weekly_plan(
                    {
                        "week_start": week_start,
                        "focus": focus,
                        "planned_gym_sessions": gym_sessions,
                        "planned_cardio_sessions": cardio_sessions,
                        "anticipated_barrier": barrier,
                        "if_then_plan": if_then,
                    }
                )
            st.session_state.weekly_plan_saved = "Weekly plan saved."
            st.rerun()


def food_log():
    saved_message = st.session_state.pop("food_journal_saved", None)
    status_heading("Food journal", saved_message)
    st.caption("Paste your full day of notes. Meals and nutrition will be inferred automatically.")
    today = datetime.now(LONDON).date()
    update_another_day = False
    if _show_page_toggles:
        update_another_day = st.toggle(
            "Update a different day",
            value=False,
            help="Turn this on only to review or replace a previous food journal.",
            key="food_update_another_day",
        )
        if update_another_day:
            selected = st.date_input(
                "Date to update",
                value=today - timedelta(days=1),
                max_value=today,
                key="historical_food_date",
            )
    if not update_another_day:
        selected = today
    existing = get_nutrition(selected)
    saved_status = value(existing, "logging_status", "complete")
    saved_status_label = next(
        (
            label
            for label, status_value in JOURNAL_STATUS_LABELS.items()
            if status_value == saved_status
        ),
        "Complete day",
    )
    journal_status_label = st.selectbox(
        "Journal completeness",
        list(JOURNAL_STATUS_LABELS),
        index=list(JOURNAL_STATUS_LABELS).index(saved_status_label),
        help=(
            "Complete and estimated-complete days can inform weekly target suggestions. "
            "Partial days remain visible but are excluded from that calculation."
        ),
        key=f"food_completeness_{selected.isoformat()}",
    )
    journal_status = JOURNAL_STATUS_LABELS[journal_status_label]
    food_note_key = f"food_note_{selected.isoformat()}"
    note = st.text_area(
        "Full-day food journal",
        value=existing.raw_note if existing else "",
        height=220,
        placeholder=example_placeholder(
            "Breakfast was porridge with banana; lunch was soup and bread."
        ),
        key=food_note_key,
        label_visibility="collapsed",
    )
    st.button(
        "Clean response",
        key=f"clear_{food_note_key}",
        on_click=clear_text,
        args=(food_note_key,),
        use_container_width=True,
    )
    if st.button(
        "Recalculate and replace" if existing else "Analyse and save day",
        type="primary",
        use_container_width=True,
    ):
        if not note.strip():
            st.warning("Add your food notes before analysing the day.")
        elif not setting("OPENAI_API_KEY"):
            st.error("OPENAI_API_KEY is not configured.")
        else:
            try:
                with st.spinner("Estimating meals and nutrition…"):
                    estimate, model = analyse_day(note)
                    save_estimate(selected, note, estimate, model, journal_status)
                    invalidate_data_cache()
                st.session_state.food_journal_saved = (
                    f"Food journal and nutrition estimate saved for {selected:%d %b %Y}."
                )
                st.rerun()
            except Exception as exc:
                st.error(f"Analysis failed: {exc}")
    existing = get_nutrition(selected)
    if existing:
        st.subheader("Estimated day")
        cols = st.columns(5)
        for col, label, amount in zip(
            cols,
            ["Calories", "Protein", "Carbs", "Fat", "Fibre"],
            [
                f"{existing.calories} kcal",
                f"{existing.protein_g:g} g",
                f"{existing.carbs_g:g} g",
                f"{existing.fat_g:g} g",
                f"{existing.fibre_g:g} g",
            ],
            strict=True,
        ):
            col.metric(label, amount)
        completeness_label = {
            "complete": "Complete day",
            "estimated": "Estimated complete day",
            "partial": "Partial day",
        }.get(value(existing, "logging_status", "complete"), "Complete day")
        st.caption(
            f"{completeness_label} · AI confidence: {existing.confidence.title()} · "
            f"{existing.summary}"
        )
        for meal in json.loads(existing.meals_json):
            with st.expander(f"{meal['label']} · {meal['calories']} kcal"):
                st.write(", ".join(meal["foods"]))
                st.caption(
                    f"P {meal['protein_g']:g}g · C {meal['carbs_g']:g}g · "
                    f"F {meal['fat_g']:g}g · Fibre {meal['fibre_g']:g}g"
                )
        st.markdown(
            "<div class='neutral-note'>AI nutrition values are estimates and are not medical "
            "advice.</div>",
            unsafe_allow_html=True,
        )


def nutrition_insights():
    st.title("Trends")
    st.caption("Daily estimates compared with targets")
    df = cached_load_data()
    with Session(engine) as session:
        goals = session.get(GoalSettings, 1)
        targets = {
            "Calories": goals.calorie_target,
            "Protein": goals.protein_target_g,
            "Carbs": goals.carbs_target_g,
            "Fat": goals.fat_target_g,
            "Fibre": goals.fibre_target_g,
        }
    fields = {
        "Calories": "calories",
        "Protein": "protein_g",
        "Carbs": "carbs_g",
        "Fat": "fat_g",
        "Fibre": "fibre_g",
    }
    if df.empty or "calories" not in df or df["calories"].dropna().empty:
        st.info("Add food-journal estimates to unlock nutrition charts.")
        return
    nutrition = df[["entry_date", *fields.values()]].dropna(subset=["calories"]).copy()
    nutrition["entry_date"] = pd.to_datetime(nutrition["entry_date"])
    last_entry = nutrition["entry_date"].max().date()
    inspect_another_day = False
    if _show_page_toggles:
        inspect_another_day = st.toggle(
            "Inspect another day",
            value=False,
            help="Turn this on to inspect nutrition estimates for another date.",
            key="nutrition_inspect_another_day",
        )
        if inspect_another_day:
            selected = st.date_input(
                "Date to inspect",
                value=last_entry,
                max_value=datetime.now(LONDON).date(),
                key="nutrition_inspect_date",
                width="stretch",
            )
    if not inspect_another_day:
        selected = last_entry
    period_options = ["Week", "Two weeks", "Month"]
    period_view = st.session_state.get("nutrition_period_view", "Week")
    if period_view not in period_options:
        period_view = "Week"

    status_colors = {
        "Low": "#C5A33B",
        "On target": "#4F8A55",
        "High": "#B64B4B",
    }
    nutrient_colors = {
        "Calories": "#C5A33B",
        "Protein": "#6FAED9",
        "Carbs": "#B8755A",
        "Fat": "#9A6C8A",
        "Fibre": "#4F8A55",
    }
    day = nutrition[nutrition.entry_date.dt.date == selected]
    st.subheader("Last entry" if selected == last_entry else "Selected day")
    if day.empty:
        st.info("No food estimate exists for this day.")
    else:
        cols = st.columns(5)
        for col, (label, field) in zip(cols, fields.items(), strict=True):
            actual = float(day.iloc[-1][field])
            ratio = actual / targets[label] if targets[label] else 0
            status = "Low" if ratio < 0.8 else "High" if ratio > 1.2 else "On target"
            unit = "kcal" if label == "Calories" else "g"
            col.markdown(
                f"""
                <div class="nutrition-metric-card"
                     style="--nutrient-color:{nutrient_colors[label]}">
                  <div class="nutrition-metric-title">{label} ({unit})</div>
                  <div class="nutrition-metric-value">{actual:.0f}</div>
                  <div class="nutrition-metric-status">{ratio * 100:.0f}% · {status}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.subheader("Trends and averages")
    period_view = (
        st.segmented_control(
            "View",
            period_options,
            default=period_view,
            key="nutrition_period_view",
            label_visibility="collapsed",
            width="stretch",
        )
        or "Week"
    )

    window_days = {"Week": 7, "Two weeks": 14, "Month": 30}[period_view]
    period_start, period_end = nutrition_period_bounds(
        nutrition["entry_date"], selected, window_days
    )
    selected_period = nutrition[
        nutrition.entry_date.dt.normalize().between(period_start, period_end)
    ].copy()
    period_rows = [
        {
            "Day": row.entry_date.normalize(),
            "Nutrient": label,
            "% of target": row[field] / targets[label] * 100,
        }
        for _, row in selected_period.iterrows()
        for label, field in fields.items()
        if pd.notna(row[field])
    ]
    tick_step = {"Week": 1, "Two weeks": 2, "Month": 5}[period_view]
    tick_values = list(pd.date_range(period_start, period_end, freq=f"{tick_step}D"))

    st.caption(f"{period_start:%d %b %Y}–{period_end:%d %b %Y}")
    if period_rows:
        period_frame = pd.DataFrame(period_rows)
        trend_chart = (
            alt.Chart(period_frame)
            .mark_line(point=False, strokeWidth=3)
            .encode(
                x=alt.X(
                    "Day:T",
                    title=None,
                    scale=alt.Scale(domain=[period_start, period_end]),
                    axis=alt.Axis(
                        format="%d",
                        values=tick_values,
                        labelAngle=0,
                        grid=False,
                    ),
                ),
                y=alt.Y(
                    "% of target:Q",
                    title=None,
                    axis=alt.Axis(orient="right", minExtent=42, maxExtent=42),
                ),
                color=alt.Color(
                    "Nutrient:N",
                    sort=list(fields),
                    scale=alt.Scale(domain=list(fields), range=list(nutrient_colors.values())),
                    legend=None,
                ),
                tooltip=[
                    alt.Tooltip("Day:T", title="Day", format="%A, %d %b"),
                    "Nutrient:N",
                    alt.Tooltip("% of target:Q", title="Target", format=".0f"),
                ],
            )
            .properties(height=280, width="container")
        )
        trend_target = (
            alt.Chart(pd.DataFrame({"target": [100]}))
            .mark_rule(
                color="#D8D8D8",
                strokeWidth=2,
                strokeDash=[6, 5],
                opacity=0.7,
            )
            .encode(y="target:Q")
        )
        period_average = []
        for label, field in fields.items():
            values = selected_period[field].dropna()
            if values.empty:
                continue
            percent = values.mean() / targets[label] * 100
            status = "Low" if percent < 80 else "High" if percent > 120 else "On target"
            period_average.append({"Nutrient": label, "% of target": percent, "Status": status})
        average_frame = pd.DataFrame(period_average)
        muted_bar = app_palette()["grid"]
        average_bars = (
            alt.Chart(average_frame)
            .mark_bar(cornerRadiusEnd=8)
            .encode(
                x=alt.X(
                    "% of target:Q",
                    title=None,
                    scale=alt.Scale(domain=[0, 200], clamp=True),
                    axis=alt.Axis(
                        grid=False,
                        values=list(range(25, 201, 25)),
                    ),
                ),
                y=alt.Y(
                    "Nutrient:N",
                    sort=list(fields),
                    title=None,
                    axis=alt.Axis(
                        orient="right",
                        labels=False,
                        ticks=False,
                        domain=False,
                        minExtent=42,
                        maxExtent=42,
                    ),
                ),
                color=alt.Color(
                    "Status:N",
                    scale=alt.Scale(
                        domain=["Low", "On target", "High"],
                        range=[status_colors["Low"], muted_bar, status_colors["High"]],
                    ),
                    legend=None,
                ),
                opacity=alt.value(0.72),
                tooltip=[
                    "Nutrient:N",
                    "Status:N",
                    alt.Tooltip("% of target:Q", title="Average", format=".0f"),
                ],
            )
            .properties(height=180, width="container")
        )
        average_target = (
            alt.Chart(pd.DataFrame({"target": [100]}))
            .mark_rule(color="#D8D8D8", strokeWidth=2, opacity=0.7)
            .encode(x="target:Q")
        )
        average_labels = (
            alt.Chart(average_frame)
            .mark_text(
                align="left",
                baseline="middle",
                dx=8,
                color=str(app_palette()["foreground"]),
                fontWeight=600,
            )
            .encode(
                x=alt.value(0),
                y=alt.Y(
                    "Nutrient:N",
                    sort=list(fields),
                    axis=alt.Axis(
                        orient="right",
                        labels=False,
                        ticks=False,
                        domain=False,
                        minExtent=42,
                        maxExtent=42,
                    ),
                ),
                text=alt.Text("Nutrient:N"),
            )
        )
        combined_chart = alt.vconcat(
            trend_chart + trend_target,
            average_bars + average_target + average_labels,
            spacing=48,
            bounds="flush",
        ).resolve_scale(color="independent")
    with st.container(key="nutrition_visual_stack"):
        if period_rows:
            with st.container(key="nutrition_charts"):
                st.altair_chart(
                    style_chart(combined_chart),
                    width="stretch",
                    theme=None,
                )
        else:
            st.info("No food estimates exist in the selected period.")
        st.markdown(
            "<div class='neutral-note'>Indicators use AI food estimates and are informational, "
            "not medical advice.</div>",
            unsafe_allow_html=True,
        )


def appearance_page():
    appearance_saved = st.session_state.pop("appearance_saved", False)
    status_heading(
        "Appearance",
        "Appearance settings saved." if appearance_saved else None,
    )
    st.caption("Make the tracker feel like your own")
    with Session(engine) as session:
        prefs = session.get(AppPreferences, 1)
        picked_color = st.color_picker(
            "Base palette colour",
            prefs.accent,
            key="base_palette_color",
            on_change=reset_palette_controls,
        )
        hide_example_placeholders = st.toggle(
            "Hide example placeholders",
            value=not bool(getattr(prefs, "show_placeholders", True)),
            help="Turn this on to remove example text from empty fields throughout the app.",
        )
        hide_palette_preview = st.toggle(
            "Hide palette colour controls",
            value=not bool(getattr(prefs, "show_palette_preview", True)),
            help="Turn this on to hide the additional editable colours.",
        )
        hide_page_toggles = st.toggle(
            "Hide optional page toggles",
            value=not bool(getattr(prefs, "show_page_toggles", True)),
            help=(
                "Turn this on to use the default view on each page without showing its "
                "optional toggle controls. Appearance controls remain available."
            ),
        )
        preview_accent = normalize_color(picked_color)
        base_color_changed = preview_accent != normalize_color(prefs.accent)
        stored_palette_overrides = {
            palette_key: color
            for preference_key, palette_key in PALETTE_PREFERENCES.items()
            if (color := getattr(prefs, preference_key, None))
        }
        if base_color_changed:
            stored_palette_overrides = {}
        preview_palette = derived_palette(
            "dark", preview_accent, overrides=stored_palette_overrides
        )
        selected_palette_colors = None
        if not hide_palette_preview:
            st.caption("Palette colours · editable")

            def palette_color_picker(column, label, palette_key, widget_key):
                if widget_key not in st.session_state:
                    st.session_state[widget_key] = str(preview_palette[palette_key])
                return column.color_picker(label, key=widget_key)

            palette_columns = st.columns(3)
            page_color = palette_color_picker(
                palette_columns[0], "Page", "background", "palette_background"
            )
            surface_color = palette_color_picker(
                palette_columns[1], "Cards and hover", "surface", "palette_surface"
            )
            text_color = palette_color_picker(
                palette_columns[2], "Text", "foreground", "palette_text"
            )
            palette_columns = st.columns(3)
            muted_color = palette_color_picker(
                palette_columns[0], "Muted text", "muted", "palette_muted"
            )
            link_color = palette_color_picker(palette_columns[1], "Links", "link", "palette_link")
            border_color = palette_color_picker(
                palette_columns[2], "Borders", "border", "palette_border"
            )
            selected_palette_colors = {
                "background_color": page_color,
                "surface_color": surface_color,
                "text_color": text_color,
                "muted_color": muted_color,
                "link_color": link_color,
                "border_color": border_color,
            }
        font = st.selectbox(
            "Font",
            list(FONTS),
            index=(list(FONTS).index(prefs.font_family) if prefs.font_family in FONTS else 0),
            key="font_picker",
        )
        st.html(
            f"""
            <style>
            .st-key-font_picker input,
            .st-key-font_picker [role="combobox"],
            .st-key-font_picker [role="combobox"] *,
            .st-key-font_picker [data-baseweb="select"] * {{
                font-family:{FONTS[font]} !important;
            }}
            </style>
            """
        )
        smooth_charts = st.toggle(
            "Smooth line graphs",
            value=bool(prefs.smooth_charts),
            help=(
                "Use seven-entry rolling averages. Turn off to plot every recorded value directly."
            ),
        )
        success_matches_accent = st.toggle(
            "Match confirmation bubbles to save buttons",
            value=bool(getattr(prefs, "success_matches_accent", False)),
            help=(
                "Turn on to use the selected palette colour for saved-entry ticks and their "
                "hover messages. Turn off to use a lighter green."
            ),
        )
        if st.button("Save appearance", type="primary", use_container_width=True):
            try:
                prefs.accent = normalize_color(picked_color)
                prefs.color_mode = "dark"
                prefs.font_family = font
                prefs.smooth_charts = smooth_charts
                prefs.success_matches_accent = success_matches_accent
                prefs.show_placeholders = not hide_example_placeholders
                prefs.show_palette_preview = not hide_palette_preview
                prefs.show_page_toggles = not hide_page_toggles
                palette_colors_to_save = selected_palette_colors
                if palette_colors_to_save is None and base_color_changed:
                    generated_palette = derived_palette("dark", preview_accent)
                    palette_colors_to_save = {
                        preference_key: str(generated_palette[palette_key])
                        for preference_key, palette_key in PALETTE_PREFERENCES.items()
                    }
                if palette_colors_to_save is not None:
                    for preference_key, color in palette_colors_to_save.items():
                        setattr(prefs, preference_key, normalize_color(color))
                session.commit()
                invalidate_preferences_cache()
                st.session_state.appearance_saved = True
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


def settings_page():
    targets_message = st.session_state.pop("targets_saved", None)
    backup_message = st.session_state.pop("backup_restored", None)
    settings_message = targets_message or backup_message
    status_heading(
        "Targets, backup and privacy",
        settings_message,
    )
    with Session(engine) as session:
        goals = session.get(GoalSettings, 1)
        preferences = session.get(AppPreferences, 1)
        with st.form("profile_settings"):
            st.subheader("Profile and weight goal")
            profile_cols = st.columns(3)
            age = profile_cols[0].number_input(
                "Age",
                18,
                100,
                getattr(preferences, "age", DEFAULT_PROFILE.age),
                key="target_age",
            )
            sex_options = ["male", "female", "other"]
            sex = profile_cols[1].selectbox(
                "Gender",
                sex_options,
                index=(
                    sex_options.index(getattr(preferences, "sex", DEFAULT_PROFILE.sex))
                    if getattr(preferences, "sex", DEFAULT_PROFILE.sex) in sex_options
                    else 2
                ),
                format_func=str.title,
                key="target_gender",
            )
            height = profile_cols[2].number_input(
                "Height (cm)",
                120.0,
                230.0,
                getattr(preferences, "height_cm", DEFAULT_PROFILE.height_cm),
                0.5,
                key="target_height",
            )
            goal_cols = st.columns(3)
            starting_weight = goal_cols[0].number_input(
                "Starting weight (kg)",
                30.0,
                300.0,
                getattr(preferences, "start_weight_kg", DEFAULT_PROFILE.start_weight_kg),
                0.1,
                key="target_starting_weight",
            )
            goal_weight = goal_cols[1].number_input(
                "Final goal (kg)",
                30.0,
                300.0,
                getattr(preferences, "target_weight_kg", DEFAULT_PROFILE.target_weight_kg),
                0.1,
                key="target_goal_weight",
            )
            goal_date = goal_cols[2].date_input(
                "Goal date", getattr(preferences, "target_date", DEFAULT_PROFILE.target_date)
            )
            if st.form_submit_button(
                "Save profile and goal", type="primary", use_container_width=True
            ):
                if goal_weight >= starting_weight:
                    st.error("Final goal must be lower than starting weight.")
                else:
                    preferences.age = age
                    preferences.sex = sex
                    preferences.height_cm = height
                    preferences.start_weight_kg = starting_weight
                    preferences.target_weight_kg = goal_weight
                    preferences.target_date = goal_date
                    with st.spinner("Saving profile and goal…"):
                        session.commit()
                    invalidate_preferences_cache()
                    st.session_state.targets_saved = "Profile and goal saved."
                    st.rerun()
        with st.form("goals"):
            st.subheader("Daily targets")
            cols = st.columns(4)
            calories = cols[0].number_input(
                "Calories", 1000, 5000, goals.calorie_target, 50, key="target_calories"
            )
            protein = cols[1].number_input(
                "Protein (g)", 20, 400, goals.protein_target_g, key="target_protein"
            )
            carbs = cols[2].number_input(
                "Carbs (g)", 20, 600, goals.carbs_target_g, key="target_carbs"
            )
            fat = cols[3].number_input("Fat (g)", 20, 300, goals.fat_target_g, key="target_fat")
            fibre = st.number_input("Fibre (g)", 0, 100, goals.fibre_target_g, key="target_fibre")
            if st.form_submit_button("Save targets", type="primary", use_container_width=True):
                goals.calorie_target, goals.protein_target_g = calories, protein
                goals.carbs_target_g, goals.fat_target_g = carbs, fat
                goals.fibre_target_g = fibre
                with st.spinner("Saving targets…"):
                    session.commit()
                st.session_state.targets_saved = "Targets saved."
                st.rerun()
    st.subheader("Export")
    data = cached_load_data()
    export = data.copy()
    if "fasted" in export:
        export["fasting_status"] = export.pop("fasted").map({True: "Fasted", False: "Did not fast"})
    if "fast_end" in export:
        export = export.rename(columns={"fast_end": "fast_broken_at"})
    csv = export.to_csv(index=False).encode()
    st.download_button(
        "Download all data as CSV", csv, "health-journey.csv", "text/csv", use_container_width=True
    )
    with st.spinner("Preparing Excel export…"):
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            excel_safe_data(export).to_excel(writer, index=False, sheet_name="Journey")
    st.download_button(
        "Download all data as Excel",
        buffer.getvalue(),
        "health-journey.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    st.subheader("Encrypted backup and restore")
    backup_key = setting("BACKUP_ENCRYPTION_KEY")
    if backup_key:
        try:
            encrypted_backup = create_encrypted_backup(backup_key)
            st.download_button(
                "Download encrypted full backup",
                encrypted_backup,
                backup_filename(datetime.now(LONDON).date()),
                "application/octet-stream",
                use_container_width=True,
            )
        except ValueError as exc:
            st.error(str(exc))
        uploaded_backup = st.file_uploader(
            "Restore from an encrypted Health Journey backup",
            help="The restore merges the backup into the database; unrelated newer records remain.",
        )
        if uploaded_backup is not None:
            try:
                uploaded_bytes = uploaded_backup.getvalue()
                backup_summary = inspect_encrypted_backup(uploaded_bytes, backup_key)
                st.caption(
                    f"Valid encrypted backup · {backup_summary['total_rows']} records · "
                    f"created {backup_summary['created_at']}."
                )
                confirm_restore = st.checkbox(
                    "I understand that matching dates and settings will be replaced"
                )
                if st.button(
                    "Merge this backup",
                    disabled=not confirm_restore,
                    use_container_width=True,
                ):
                    with st.spinner("Validating and restoring backup…"):
                        restored = restore_encrypted_backup(uploaded_bytes, backup_key)
                    invalidate_data_cache()
                    invalidate_preferences_cache()
                    st.session_state.backup_restored = (
                        f"Backup restored: {restored['created']} added, "
                        f"{restored['updated']} updated."
                    )
                    st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    else:
        st.caption(
            "Add BACKUP_ENCRYPTION_KEY to enable full encrypted downloads, restore, and the "
            "monthly emailed backup. CSV and Excel exports remain available above."
        )
    st.markdown(
        "<div class='neutral-note'>BMI, calorie targets, and AI nutrition estimates are "
        "informational only—not medical advice.</div>",
        unsafe_allow_html=True,
    )


def log_out_page():
    sign_out(auth_context)


home_page = st.Page(home, title="Home", default=True)
dashboard_page = st.Page(dashboard, title="Dashboard")
check_in_page = st.Page(daily_entry, title="Check-in")
journal_page = st.Page(food_log, title="Journal")
nutrition_page = st.Page(nutrition_insights, title="Trends")
coaching_page = st.Page(weekly_coaching, title="Coaching")
targets_page = st.Page(settings_page, title="Targets")
appearance = st.Page(appearance_page, title="Appearance")
log_out = st.Page(log_out_page, title="Log out")
standard_pages = [
    home_page,
    dashboard_page,
    check_in_page,
    journal_page,
    nutrition_page,
    coaching_page,
]
page = st.navigation([*standard_pages, targets_page, appearance, log_out], position="hidden")
with st.sidebar:
    for navigation_page in standard_pages:
        st.page_link(navigation_page, use_container_width=True)
    with st.container(key="sidebar_bottom_actions"):
        st.page_link(
            targets_page,
            icon=":material/track_changes:",
            use_container_width=True,
        )
        st.page_link(
            appearance,
            icon=":material/palette:",
            use_container_width=True,
        )
        st.page_link(
            log_out,
            icon=":material/logout:",
            use_container_width=True,
        )
collapse_sidebar_after_page_change(page.url_path)
page.run()
