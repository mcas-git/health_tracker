from __future__ import annotations

import io
import json
import math
from datetime import datetime, timedelta

import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy.orm import Session

from health_tracker.analytics import (
    bmi_status,
    daily_health_score,
    excel_safe_data,
    load_data,
    projected_target_date,
    weekly_coaching_summary,
    weight_milestones,
)
from health_tracker.auth import require_login
from health_tracker.config import LONDON, Profile, setting
from health_tracker.config import PROFILE as DEFAULT_PROFILE
from health_tracker.db import (
    engine,
    get_daily,
    get_latest_daily_before,
    get_nutrition,
    get_weekly_plan,
    init_db,
    upsert_daily,
    upsert_weekly_plan,
)
from health_tracker.garmin import sync_day
from health_tracker.models import AppPreferences, GoalSettings
from health_tracker.nutrition import analyse_day, save_estimate
from health_tracker.quotes import daily_item
from health_tracker.research import RESEARCH_INSIGHTS
from health_tracker.theme import FONTS, apply_theme, derived_palette, normalize_color

st.set_page_config(
    page_title="Health Journey",
    layout="wide",
)
init_db()
require_login()

with Session(engine) as _theme_session:
    _preferences = _theme_session.get(AppPreferences, 1)
    _theme_values = ("dark", _preferences.accent, _preferences.font_family)
    _smooth_charts = bool(_preferences.smooth_charts)
    _profile = Profile(
        age=getattr(_preferences, "age", DEFAULT_PROFILE.age),
        sex=getattr(_preferences, "sex", DEFAULT_PROFILE.sex),
        height_cm=getattr(_preferences, "height_cm", DEFAULT_PROFILE.height_cm),
        start_weight_kg=getattr(
            _preferences, "start_weight_kg", DEFAULT_PROFILE.start_weight_kg
        ),
        target_weight_kg=getattr(
            _preferences, "target_weight_kg", DEFAULT_PROFILE.target_weight_kg
        ),
        target_date=getattr(_preferences, "target_date", DEFAULT_PROFILE.target_date),
    )
apply_theme(*_theme_values)


def value(item, name, default=None):
    result = getattr(item, name, None) if item is not None else None
    return default if result is None else result


def clear_text(key: str) -> None:
    st.session_state[key] = ""


def rating_input(label: str, key: str, initial: int) -> int:
    return st.number_input(
        label,
        min_value=1,
        max_value=10,
        value=max(1, min(10, int(initial))),
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
    palette = derived_palette(_theme_values[0], _theme_values[1])
    foreground = palette["foreground"]
    grid = palette["grid"]
    accent = palette["accent"]
    secondary = palette["series"][1]
    return (
        chart.configure(background="transparent")
        .configure_view(strokeOpacity=0)
        .configure_line(color=accent)
        .configure_point(filled=True, fill=accent, stroke=accent, strokeWidth=2, size=72)
        .configure_rule(color=secondary)
        .configure_axis(
            labelColor=foreground,
            titleColor=foreground,
            domainColor=grid,
            tickColor=grid,
            gridColor=grid,
            gridOpacity=0.35,
        )
        .configure_legend(
            orient="bottom",
            direction="horizontal",
            labelColor=foreground,
            titleColor=foreground,
            symbolStrokeColor=foreground,
            padding=12,
        )
        .configure_title(color=foreground)
    )


def health_status_cards(item) -> None:
    indicator = daily_health_score(item, _profile) if item is not None else None
    if indicator:
        score, score_label, included = indicator
        score_color = "#4F8A55" if score >= 75 else "#C5A33B" if score >= 45 else "#B64B4B"
        st.markdown(
            f"<div class='health-score' style='--score-color:{score_color}'>"
            f"<span>Daily health indicator</span><strong>{score}/100 · {score_label}</strong>"
            f"<small>Based on {', '.join(included)}. This is not a diagnosis.</small></div>",
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
            f"<span>BMI weight status</span><strong>BMI {item.bmi:.1f} · {status_label}</strong>"
            f"<small>{status_context}. This is not a diagnosis.</small></div>",
            unsafe_allow_html=True,
        )


def home():
    london_day = datetime.now(LONDON).date()
    research = daily_item(RESEARCH_INSIGHTS, london_day)
    st.markdown(
        f"""
        <div class="quote-card">
          <div class="quote-label">RESEARCH NOTE</div>
          <div class="quote-text">{research["insight"]}</div>
          <p><a href="{research["url"]}" target="_blank">{research["source"]}</a></p>
        </div>
        <div class="motivation-card">
          <div class="research-motivation-label">TODAY'S MOTIVATION</div>
          <div class="research-motivation">“{research["motivation"]}”</div>
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
    df = load_data()
    latest_weight = df.weight_kg.dropna().iloc[-1] if not df.empty and "weight_kg" in df else None
    goal_range = _profile.start_weight_kg - _profile.target_weight_kg
    progress = (
        (_profile.start_weight_kg - latest_weight)
        / goal_range
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
    latest_measurements = (
        df.dropna(subset=["bmi"]).sort_values("entry_date").iloc[-1]
        if "bmi" in df and df["bmi"].notna().any()
        else None
    )
    health_status_cards(latest_measurements)

    if df.empty:
        st.info("Add your first daily entry to begin the dashboard.")
        return
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    chart_height = 320
    accent = _theme_values[1]
    palette = derived_palette(*_theme_values[:2])
    series_colors = palette["series"]
    journey_start = pd.Timestamp(df.entry_date.min()).normalize()
    journey_end = max(pd.Timestamp(_profile.target_date), journey_start)
    date_scale = alt.Scale(domain=[journey_start, journey_end])
    date_axis = alt.Axis(
        title=None,
        format="%b",
        labelAngle=0,
        tickCount=8,
        labelOverlap="greedy",
    )

    st.subheader("Weight trend")
    milestones, weekly_pace = weight_milestones(journey_start.date(), _profile)
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
                    axis=alt.Axis(labels=True, ticks=True, domain=True),
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
            use_container_width=True,
            theme=None,
        )
        latest_weight_row = weight.iloc[-1]
        st.caption(
            f"Latest recorded weight: {latest_weight_row['weight_kg']:.1f} kg on "
            f"{latest_weight_row['entry_date']:%d %b %Y}."
        )
        weight_change = latest_weight_row["weight_kg"] - _profile.start_weight_kg
        st.caption(f"This is {weight_change:+.1f} kg from the beginning.")
    else:
        st.caption("No weight entries yet.")

    st.subheader("Additional KPI")
    kpis = [
        col
        for col in [
            "entry_date",
            "weight_kg",
            "bmi",
            "waist_cm",
            "steps",
            "sleep_hours",
            "calories",
            "calories_burned",
            "mood",
            "energy",
            "fasting_hours",
        ]
        if col in df
    ]
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
        label: field for field, label in labels.items() if field in df and df[field].notna().any()
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
                    axis=alt.Axis(labels=True, ticks=True, domain=True),
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
        st.altair_chart(style_chart(kpi_layers), use_container_width=True, theme=None)
        reference = f" [Reference]({goal['url']})" if goal["url"] else ""
        st.caption(f"Goal anchor: **{goal['label']}** — {goal['note']}{reference}")
    else:
        st.caption("Add another measurement to display a recent KPI trend.")

    recent_table = df[kpis].tail(14).sort_values("entry_date", ascending=False)
    st.download_button(
        "Download recent KPI table",
        recent_table.to_csv(index=False).encode(),
        "recent-health-kpis.csv",
        "text/csv",
        use_container_width=True,
    )
def daily_entry():
    st.title("Daily check-in")
    if saved_message := st.session_state.pop("daily_checkin_saved", None):
        st.success(saved_message)
    london_now = datetime.now(LONDON)
    today = london_now.date()
    if requested_date := st.session_state.pop("smartwatch_sync_requested", None):
        try:
            with st.spinner("Loading smartwatch data…"):
                smartwatch_data = sync_day(requested_date)
            st.session_state.garmin_sync = {"date": requested_date, "data": smartwatch_data}
            st.success(
                f"Smartwatch data loaded for {requested_date:%d %b %Y} · "
                f"{len(smartwatch_data['activities'])} activities."
            )
        except Exception as exc:
            st.error(f"Smartwatch sync failed: {exc}")
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
        st.caption(f"Updating the saved check-in for {selected:%A, %d %B %Y}.")
    else:
        selected = today
        st.caption(f"Recording today · {today:%A, %d %B %Y}")
    item = get_daily(selected)
    previous_item = get_latest_daily_before(selected) if item is None else None
    measurement_defaults = item or previous_item
    if item is not None:
        updated = item.updated_at
        if updated.tzinfo is not None:
            updated = updated.astimezone(LONDON)
        st.success(
            f"Entry saved for {selected:%d %b %Y} · Last updated {updated:%d %b %Y at %H:%M}"
        )
    sync_record = st.session_state.get("garmin_sync", {})
    synced = sync_record.get("data", {}) if sync_record.get("date") == selected else {}
    date_key = selected.isoformat()

    with st.expander("Morning check-in", expanded=True):
        st.caption("Record weight, waist and blood pressure.")
        with st.form(f"morning_form_{date_key}"):
            c1, c2 = st.columns(2)
            weight = c1.number_input(
                "Weight (kg)",
                30.0,
                250.0,
                float(value(measurement_defaults, "weight_kg", _profile.start_weight_kg)),
                0.1,
                key=f"weight_{date_key}",
            )
            waist = c2.number_input(
                "Waist (cm)",
                30.0,
                250.0,
                float(value(measurement_defaults, "waist_cm", 100.0)),
                0.1,
                key=f"waist_{date_key}",
            )
            bmi = weight / ((_profile.height_cm / 100) ** 2)
            c1, c2 = st.columns(2)
            systolic = c1.number_input(
                "Blood pressure · systolic",
                60,
                250,
                int(value(measurement_defaults, "systolic", 120)),
                key=f"systolic_{date_key}",
            )
            diastolic = c2.number_input(
                "Blood pressure · diastolic",
                30,
                160,
                int(value(measurement_defaults, "diastolic", 80)),
                key=f"diastolic_{date_key}",
            )
            morning_submitted = st.form_submit_button(
                "Save morning check-in", use_container_width=True, type="primary"
            )
        if morning_submitted:
            upsert_daily(
                {
                    "entry_date": selected,
                    "weight_kg": weight,
                    "waist_cm": waist,
                    "bmi": bmi,
                    "systolic": systolic,
                    "diastolic": diastolic,
                }
            )
            st.session_state["daily_checkin_saved"] = (
                f"Morning check-in saved for {selected:%d %b %Y}."
            )
            st.rerun()

    with st.expander("Evening check-in", expanded=False):
        st.subheader("Smartwatch data")
        st.caption(
            "Loads the selected date from Garmin. Sleep is the overnight sleep Garmin assigns "
            "to that date, normally the night ending that morning."
        )
        with st.container(key="smartwatch_load"):
            if st.button(
                "Load smartwatch data from Garmin",
                use_container_width=True,
                key=f"load_garmin_{date_key}",
            ):
                st.session_state.smartwatch_sync_requested = selected
                st.rerun()

        def smartwatch_value(field):
            imported = synced.get(field)
            return imported if imported is not None else value(item, field)

        with st.form(f"evening_form_{date_key}"):
            c1, c2, c3, c4 = st.columns(4)
            resting_value = smartwatch_value("resting_heart_rate")
            resting_hr = c1.number_input(
                "Resting heart rate",
                30,
                220,
                value=int(resting_value) if resting_value is not None else None,
                disabled=True,
                placeholder="No data",
                key=f"resting_hr_{date_key}",
            )
            sleep_value = smartwatch_value("sleep_hours")
            sleep = c2.number_input(
                "Sleep (hours)",
                0.0,
                24.0,
                value=float(sleep_value) if sleep_value is not None else None,
                step=0.01,
                disabled=True,
                placeholder="No data",
                key=f"sleep_{date_key}",
            )
            steps_value = smartwatch_value("steps")
            steps = c3.number_input(
                "Steps",
                0,
                100000,
                value=int(steps_value) if steps_value is not None else None,
                disabled=True,
                placeholder="No data",
                key=f"steps_{date_key}",
            )
            burned_value = smartwatch_value("calories_burned")
            burned = c4.number_input(
                "Calories burned",
                0,
                10000,
                value=int(burned_value) if burned_value is not None else None,
                disabled=True,
                placeholder="No data",
                key=f"burned_{date_key}",
            )

            st.subheader("Evening measurements")
            mood = rating_input(
                "Mood", f"mood_{date_key}", int(value(measurement_defaults, "mood", 5))
            )
            energy = rating_input(
                "Energy level",
                f"energy_{date_key}",
                int(value(measurement_defaults, "energy", 5)),
            )
            cravings = rating_input(
                "Cravings",
                f"cravings_{date_key}",
                int(value(measurement_defaults, "cravings", 5)),
            )
            satisfaction = rating_input(
                "Diet satisfaction",
                f"diet_satisfaction_{date_key}",
                int(value(measurement_defaults, "diet_satisfaction", 7)),
            )

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
                    label, value=bool(value(item, key, False)), key=f"{key}_{date_key}"
                )

            st.subheader("Extenuating circumstances")
            circumstance_cols = st.columns(4)
            circumstances = {}
            for idx, (key, label) in enumerate(
                [
                    ("illness", "Illness"),
                    ("injury", "Injury"),
                    ("travel", "Travel"),
                    ("unusual_day", "Unusual day"),
                ]
            ):
                circumstances[key] = circumstance_cols[idx].checkbox(
                    label, value=bool(value(item, key, False)), key=f"{key}_{date_key}"
                )

            evening_submitted = st.form_submit_button(
                "Save evening check-in", use_container_width=True, type="primary"
            )
        if evening_submitted:
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
                    **habits,
                    **circumstances,
                }
            )
            st.session_state.pop("garmin_sync", None)
            st.session_state["daily_checkin_saved"] = (
                f"Evening check-in saved for {selected:%d %b %Y}."
            )
            st.rerun()


def weekly_coaching():
    st.title("Weekly coaching")
    st.caption("Review the trend, choose one focus, and plan around real-life barriers")
    today = datetime.now(LONDON).date()
    week_start = today - timedelta(days=today.weekday())
    df = load_data()
    summary = weekly_coaching_summary(df, today, _profile)

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
            "logging completeness, portions, weekends and activity before lowering calories.</div>",
            unsafe_allow_html=True,
        )
    st.subheader("This week's evidence")
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

    saved = get_weekly_plan(week_start)
    with st.form("weekly_plan"):
        st.subheader("Plan this week")
        week_key = week_start.isoformat()
        c1, c2, c3 = st.columns(3)
        gym_sessions = c1.number_input(
            "Planned gym sessions", 0, 7, int(value(saved, "planned_gym_sessions", 3))
        )
        cardio_sessions = c2.number_input(
            "Planned cardio sessions", 0, 7, int(value(saved, "planned_cardio_sessions", 2))
        )
        minimum_steps = c3.number_input(
            "Daily step floor", 0, 50000, int(value(saved, "minimum_steps", 7000)), 500
        )
        focus_key = f"weekly_focus_{week_key}"
        focus = st.text_input(
            "One behaviour to focus on",
            value=value(saved, "focus", summary["recommendation"]),
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
            placeholder="If work runs late, then I will use the prepared dinner.",
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
            upsert_weekly_plan(
                {
                    "week_start": week_start,
                    "focus": focus,
                    "planned_gym_sessions": gym_sessions,
                    "planned_cardio_sessions": cardio_sessions,
                    "minimum_steps": minimum_steps,
                    "anticipated_barrier": barrier,
                    "if_then_plan": if_then,
                }
            )
            st.success("Weekly plan saved.")


def food_log():
    st.title("Food journal")
    if saved_message := st.session_state.pop("food_journal_saved", None):
        st.success(saved_message)
    st.caption("Paste your full day of notes. Meals and nutrition will be inferred automatically.")
    today = datetime.now(LONDON).date()
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
    else:
        selected = today
    existing = get_nutrition(selected)
    food_note_key = f"food_note_{selected.isoformat()}"
    note = st.text_area(
        "Full-day food journal",
        value=existing.raw_note if existing else "",
        height=220,
        placeholder="Breakfast was porridge with banana… Lunch… Later I had…",
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
        disabled=not note.strip(),
    ):
        if not setting("OPENAI_API_KEY"):
            st.error("OPENAI_API_KEY is not configured.")
        else:
            try:
                with st.spinner("Estimating meals and nutrition…"):
                    estimate, model = analyse_day(note)
                    save_estimate(selected, note, estimate, model)
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
        st.caption(f"Confidence: {existing.confidence.title()} · {existing.summary}")
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
    st.title("Nutrition insights")
    st.caption("Daily estimates compared with your adjustable targets")
    df = load_data()
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
    selected = st.date_input("Inspect a day", nutrition.entry_date.max().date())
    day = nutrition[nutrition.entry_date.dt.date == selected]
    st.subheader("Selected day")
    if day.empty:
        st.info("No food estimate exists for this day.")
    else:
        cols = st.columns(5)
        for col, (label, field) in zip(cols, fields.items(), strict=True):
            actual = float(day.iloc[-1][field])
            ratio = actual / targets[label] if targets[label] else 0
            status = "Low" if ratio < 0.8 else "High" if ratio > 1.2 else "On target"
            unit = "kcal" if label == "Calories" else "g"
            col.metric(label, f"{actual:.0f} {unit}", f"{ratio * 100:.0f}% · {status}")

    nutrition["week"] = nutrition.entry_date.dt.to_period("W").dt.start_time
    weekly = nutrition.groupby("week", as_index=False)[list(fields.values())].mean()
    weekly_rows = [
        {"Week": row.week, "Nutrient": label, "% of target": row[field] / targets[label] * 100}
        for _, row in weekly.iterrows()
        for label, field in fields.items()
    ]
    palette = derived_palette(*_theme_values[:2])
    st.subheader("Weekly average vs target")
    weekly_frame = pd.DataFrame(weekly_rows)
    if _smooth_charts:
        weekly_frame["% of target"] = weekly_frame.groupby("Nutrient")["% of target"].transform(
            lambda values: values.rolling(3, min_periods=1).mean()
        )
    weekly_chart = (
        alt.Chart(weekly_frame)
        .mark_line(point=not _smooth_charts, strokeWidth=3)
        .encode(
            x=alt.X(
                "Week:T",
                title=None,
                axis=alt.Axis(format="%b", labelAngle=0, labelOverlap="greedy"),
            ),
            y=alt.Y("% of target:Q", title="Target %"),
            strokeDash=alt.StrokeDash("Nutrient:N", legend=alt.Legend(orient="bottom")),
            color=alt.Color("Nutrient:N", legend=None, scale=alt.Scale(range=palette["series"])),
            tooltip=["Week:T", "Nutrient:N", alt.Tooltip("% of target:Q", format=".0f")],
        )
    )
    st.altair_chart(style_chart(weekly_chart), use_container_width=True, theme=None)

    overall = [
        {"Nutrient": label, "% of target": nutrition[field].mean() / targets[label] * 100}
        for label, field in fields.items()
    ]
    st.subheader("Overall average")
    overall_chart = (
        alt.Chart(pd.DataFrame(overall))
        .mark_bar(cornerRadiusEnd=8)
        .encode(
            x=alt.X("% of target:Q", title="Average target achievement (%)"),
            y=alt.Y("Nutrient:N", sort=None, title=None),
            opacity=alt.condition(
                "datum['% of target'] >= 80 && datum['% of target'] <= 120",
                alt.value(1.0),
                alt.value(0.45),
            ),
            color=alt.value(_theme_values[1]),
            tooltip=["Nutrient:N", alt.Tooltip("% of target:Q", format=".0f")],
        )
    )
    st.altair_chart(style_chart(overall_chart), use_container_width=True, theme=None)
    st.markdown(
        "<div class='neutral-note'>Indicators use AI food estimates and are informational, "
        "not medical advice.</div>",
        unsafe_allow_html=True,
    )


def appearance_page():
    st.title("Appearance")
    if st.session_state.pop("appearance_saved", False):
        st.success("Appearance settings saved.")
    st.caption("Make the tracker feel like your own")
    with Session(engine) as session:
        prefs = session.get(AppPreferences, 1)
        st.caption("Dark mode is used throughout the tracker.")
        picked_color = st.color_picker("Base palette colour", prefs.accent)
        typed_color = st.text_input(
            "RGB or HEX override (optional)",
            placeholder="rgb(123, 132, 81) or #7B8451",
            help="Leave blank to use the colour picker above.",
        )
        font = st.selectbox(
            "Font",
            list(FONTS),
            index=(list(FONTS).index(prefs.font_family) if prefs.font_family in FONTS else 0),
        )
        smooth_charts = st.toggle(
            "Smooth line graphs",
            value=bool(prefs.smooth_charts),
            help=(
                "Use seven-entry rolling averages. Turn off to plot every recorded value "
                "directly."
            ),
        )
        st.markdown(
            f'<div style="font-family:{FONTS[font]};font-size:1.15rem;padding:.5rem 0">'
            f"Selected: {font} — The quick brown fox — 0123456789</div>",
            unsafe_allow_html=True,
        )
        if st.button("Save appearance", type="primary", use_container_width=True):
            try:
                prefs.accent = normalize_color(typed_color or picked_color)
                prefs.color_mode = "dark"
                prefs.font_family = font
                prefs.smooth_charts = smooth_charts
                session.commit()
                st.session_state.appearance_saved = True
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


def settings_page():
    st.title("Targets, backup and privacy")
    with Session(engine) as session:
        goals = session.get(GoalSettings, 1)
        preferences = session.get(AppPreferences, 1)
        with st.form("profile_settings"):
            st.subheader("Profile and weight goal")
            profile_cols = st.columns(3)
            age = profile_cols[0].number_input(
                "Age", 18, 100, getattr(preferences, "age", DEFAULT_PROFILE.age)
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
            )
            height = profile_cols[2].number_input(
                "Height (cm)",
                120.0,
                230.0,
                getattr(preferences, "height_cm", DEFAULT_PROFILE.height_cm),
                0.5,
            )
            goal_cols = st.columns(3)
            starting_weight = goal_cols[0].number_input(
                "Starting weight (kg)",
                30.0,
                300.0,
                getattr(preferences, "start_weight_kg", DEFAULT_PROFILE.start_weight_kg),
                0.1,
            )
            goal_weight = goal_cols[1].number_input(
                "Final goal (kg)",
                30.0,
                300.0,
                getattr(preferences, "target_weight_kg", DEFAULT_PROFILE.target_weight_kg),
                0.1,
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
                    session.commit()
                    st.success("Profile and goal saved.")
                    st.rerun()
        with st.form("goals"):
            st.subheader("Daily targets")
            cols = st.columns(4)
            calories = cols[0].number_input("Calories", 1000, 5000, goals.calorie_target, 50)
            protein = cols[1].number_input("Protein (g)", 20, 400, goals.protein_target_g)
            carbs = cols[2].number_input("Carbs (g)", 20, 600, goals.carbs_target_g)
            fat = cols[3].number_input("Fat (g)", 20, 300, goals.fat_target_g)
            cols = st.columns(3)
            fibre = cols[0].number_input("Fibre (g)", 0, 100, goals.fibre_target_g)
            fasting = cols[1].number_input(
                "Fasting target (hours)", 0.0, 36.0, goals.fasting_target_hours, 0.5
            )
            sleep = cols[2].number_input(
                "Sleep target (hours)", 0.0, 16.0, goals.sleep_target_hours, 0.25
            )
            if st.form_submit_button("Save targets", type="primary", use_container_width=True):
                goals.calorie_target, goals.protein_target_g = calories, protein
                goals.carbs_target_g, goals.fat_target_g = carbs, fat
                goals.fibre_target_g, goals.fasting_target_hours = fibre, fasting
                goals.sleep_target_hours = sleep
                session.commit()
                st.success("Targets saved.")
    st.subheader("Export")
    data = load_data()
    export = data.copy()
    if "fasted" in export:
        export["fasting_status"] = export.pop("fasted").map({True: "Fasted", False: "Did not fast"})
    if "fast_end" in export:
        export = export.rename(columns={"fast_end": "fast_broken_at"})
    csv = export.to_csv(index=False).encode()
    st.download_button(
        "Download all data as CSV", csv, "health-journey.csv", "text/csv", use_container_width=True
    )
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
    st.info(
        "BMI, calorie targets, and AI nutrition estimates are informational only—"
        "not medical advice."
    )


page = st.navigation(
    [
        st.Page(home, title="Home", default=True),
        st.Page(dashboard, title="Dashboard"),
        st.Page(daily_entry, title="Daily check-in"),
        st.Page(food_log, title="Food journal"),
        st.Page(nutrition_insights, title="Nutrition insights"),
        st.Page(weekly_coaching, title="Weekly coaching"),
        st.Page(settings_page, title="Targets & export"),
        st.Page(appearance_page, title="Appearance"),
    ]
)
page.run()
