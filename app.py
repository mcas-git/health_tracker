from __future__ import annotations

import io
import json
from datetime import date, datetime, time, timedelta

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
)
from health_tracker.auth import require_login
from health_tracker.config import LONDON, PROFILE, setting
from health_tracker.db import (
    engine,
    get_daily,
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
from health_tracker.visuals import optional_home_logo, page_watermark

st.set_page_config(
    page_title="Health Journey",
    page_icon="⚪",
    layout="wide",
)
init_db()
require_login()

with Session(engine) as _theme_session:
    _preferences = _theme_session.get(AppPreferences, 1)
    _theme_values = (_preferences.color_mode, _preferences.accent, _preferences.font_family)
    _smooth_charts = bool(_preferences.smooth_charts)
apply_theme(*_theme_values)


def value(item, name, default=None):
    result = getattr(item, name, None) if item is not None else None
    return default if result is None else result


def adjust_rating(key: str, change: int) -> None:
    st.session_state[key] = max(1, min(10, int(st.session_state.get(key, 5)) + change))


def mobile_rating(label: str, key: str, initial: int) -> int:
    if key not in st.session_state:
        st.session_state[key] = initial
    with st.container(key=f"rating_{key}"):
        minus, scale, plus = st.columns([1, 6, 1], vertical_alignment="bottom")
        minus.form_submit_button(
            "−",
            key=f"{key}_minus",
            help=f"Decrease {label.lower()}",
            on_click=adjust_rating,
            args=(key, -1),
            use_container_width=True,
        )
        rating = scale.slider(label, 1, 10, key=key)
        plus.form_submit_button(
            "+",
            key=f"{key}_plus",
            help=f"Increase {label.lower()}",
            on_click=adjust_rating,
            args=(key, 1),
            use_container_width=True,
        )
    return rating


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
    indicator = daily_health_score(item) if item is not None else None
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
            f"<span>BMI weight status</span><strong>{status_label}</strong>"
            f"<small>BMI {item.bmi:.1f} · {status_context}. This is not a diagnosis.</small></div>",
            unsafe_allow_html=True,
        )


def home():
    page_watermark("home", _theme_values[1])
    optional_home_logo()
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
    page_watermark("runner", _theme_values[1])
    st.title("Your health journey")
    st.caption(f"One calm day at a time · Goal: {PROFILE.target_weight_kg:g} kg by 1 Sep 2027")
    df = load_data()
    latest_weight = df.weight_kg.dropna().iloc[-1] if not df.empty and "weight_kg" in df else None
    progress = (
        (PROFILE.start_weight_kg - latest_weight)
        / (PROFILE.start_weight_kg - PROFILE.target_weight_kg)
        if latest_weight is not None
        else 0
    )
    projection = projected_target_date(df)
    recent_completion = weekly_coaching_summary(df)["completion"]
    a, b, c, d = st.columns(4)
    a.metric("Current weight", f"{latest_weight:.1f} kg" if latest_weight else "—")
    b.metric("Goal progress", f"{max(0, min(100, progress * 100)):.0f}%")
    c.metric("7-day completion", f"{recent_completion}%")
    d.metric("Projected goal", projection.strftime("%d %b %Y") if projection else "Need more data")
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
    hidden_axis = alt.Axis(labels=False, ticks=False, domain=False, title=None)

    st.subheader("Weight trend")
    weight = df[["entry_date", "weight_kg"]].dropna().copy()
    if not weight.empty:
        weight["display_value"] = (
            weight.weight_kg.rolling(7, min_periods=1).mean()
            if _smooth_charts
            else weight.weight_kg
        )
        weight_line = (
            alt.Chart(weight)
            .mark_line(
                point=(
                    alt.OverlayMarkDef(
                        filled=True, fill=accent, stroke=accent, strokeWidth=2, size=72
                    )
                    if not _smooth_charts
                    else False
                ),
                color=accent,
                strokeWidth=4,
            )
            .encode(
                x=alt.X("entry_date:T", axis=hidden_axis),
                y=alt.Y("display_value:Q", axis=hidden_axis, scale=alt.Scale(zero=False)),
                tooltip=[
                    alt.Tooltip("entry_date:T", title="Date"),
                    alt.Tooltip("display_value:Q", title="Weight (kg)", format=".1f"),
                ],
            )
        )
        goal_line = (
            alt.Chart(pd.DataFrame({"goal": [PROFILE.target_weight_kg]}))
            .mark_rule(color=series_colors[1], strokeWidth=3, strokeDash=[8, 5], opacity=0.8)
            .encode(
                y="goal:Q",
                tooltip=[alt.Tooltip("goal:Q", title="Goal weight (kg)", format=".1f")],
            )
        )
        st.altair_chart(
            style_chart((weight_line + goal_line).properties(height=chart_height)),
            use_container_width=True,
            theme=None,
        )
    else:
        st.caption("No weight entries yet.")

    st.subheader("Calories and activity")
    fields = [
        field
        for field in ["calories", "calories_burned"]
        if field in df and df[field].notna().any()
    ]
    if fields:
        calories = df[["entry_date", *fields]].copy()
        if _smooth_charts:
            calories[fields] = calories[fields].rolling(7, min_periods=1).mean()
        melted = calories.melt("entry_date", fields, var_name="measure", value_name="kcal").dropna()
        chart = (
            alt.Chart(melted)
            .mark_line(point=not _smooth_charts, strokeWidth=4)
            .encode(
                x=alt.X("entry_date:T", axis=hidden_axis),
                y=alt.Y("kcal:Q", axis=hidden_axis, scale=alt.Scale(zero=False)),
                strokeDash=alt.StrokeDash(
                    "measure:N", legend=alt.Legend(orient="bottom", title=None)
                ),
                color=alt.Color(
                    "measure:N",
                    legend=None,
                    scale=alt.Scale(range=series_colors[: len(fields)]),
                ),
                tooltip=[
                    alt.Tooltip("entry_date:T", title="Date"),
                    alt.Tooltip("measure:N", title="Measure"),
                    alt.Tooltip("kcal:Q", title="kcal", format=".0f"),
                ],
            )
            .properties(height=chart_height)
        )
        st.altair_chart(style_chart(chart), use_container_width=True, theme=None)
    else:
        st.caption("No nutrition or calorie-burn data yet.")

    st.subheader("Recent KPI view")
    kpis = [
        col
        for col in [
            "entry_date",
            "weight_kg",
            "bmi",
            "waist_cm",
            "steps",
            "sleep_hours",
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
        "mood": "Mood",
        "energy": "Energy",
        "fasting_hours": "Fasting hours",
        "resting_heart_rate": "Resting heart rate",
        "systolic": "Blood pressure (systolic)",
        "diastolic": "Blood pressure (diastolic)",
    }
    available = {
        label: field for field, label in labels.items() if field in df and df[field].notna().any()
    }
    if available:
        selected_label = st.selectbox("Additional KPI", available)
        selected_kpi = available[selected_label]
        recent = df[["entry_date", selected_kpi]].dropna().tail(30).copy()
        recent["display_value"] = (
            recent[selected_kpi].rolling(7, min_periods=1).mean()
            if _smooth_charts
            else recent[selected_kpi]
        )
        kpi_chart = (
            alt.Chart(recent)
            .mark_line(
                point=(
                    alt.OverlayMarkDef(
                        filled=True, fill=accent, stroke=accent, strokeWidth=2, size=72
                    )
                    if not _smooth_charts
                    else False
                ),
                color=accent,
                strokeWidth=4,
            )
            .encode(
                x=alt.X("entry_date:T", axis=hidden_axis),
                y=alt.Y("display_value:Q", axis=hidden_axis, scale=alt.Scale(zero=False)),
                tooltip=[
                    alt.Tooltip("entry_date:T", title="Date"),
                    alt.Tooltip("display_value:Q", title=selected_label, format=".1f"),
                ],
            )
            .properties(height=chart_height)
        )
        st.altair_chart(style_chart(kpi_chart), use_container_width=True, theme=None)
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
    page_watermark("barbell", _theme_values[1])
    st.title("Daily check-in")
    if saved_message := st.session_state.pop("daily_checkin_saved", None):
        st.success(saved_message)
    london_now = datetime.now(LONDON)
    yesterday = london_now.date() - timedelta(days=1)
    if "daily_entry_date" not in st.session_state:
        st.session_state.daily_entry_date = yesterday if london_now.hour < 12 else london_now.date()
    with st.container(key="garmin_yesterday"):
        if st.button("Load yesterday", use_container_width=True):
            try:
                with st.spinner("Loading yesterday from Garmin…"):
                    yesterday_data = sync_day(yesterday)
                st.session_state.daily_entry_date = yesterday
                st.session_state.garmin_sync = {"date": yesterday, "data": yesterday_data}
                st.success(f"Loaded yesterday · {len(yesterday_data['activities'])} activities.")
            except Exception as exc:
                st.error(f"Garmin sync failed: {exc}")
    selected = st.date_input("Date", key="daily_entry_date")
    item = get_daily(selected)
    if item is not None:
        updated = item.updated_at
        if updated.tzinfo is not None:
            updated = updated.astimezone(LONDON)
        st.success(
            f"Entry saved for {selected:%d %b %Y} · Last updated {updated:%d %b %Y at %H:%M}"
        )
    with st.expander("Garmin sync", expanded=False):
        st.caption("Imports steps, calories burned, sleep, resting heart rate, and activity data.")
        with st.container(key="garmin_selected"):
            if st.button("Sync selected date", use_container_width=True):
                try:
                    with st.spinner("Connecting to Garmin…"):
                        synced = sync_day(selected)
                    st.session_state.garmin_sync = {"date": selected, "data": synced}
                    st.success(f"Synced {len(synced['activities'])} activities.")
                except Exception as exc:
                    st.error(f"Garmin sync failed: {exc}")
    sync_record = st.session_state.get("garmin_sync", {})
    synced = sync_record.get("data", {}) if sync_record.get("date") == selected else {}

    with st.form("daily_form"):
        st.subheader("Measurements")
        c1, c2, c3 = st.columns(3)
        weight = c1.number_input(
            "Weight (kg)",
            30.0,
            250.0,
            float(value(item, "weight_kg", PROFILE.start_weight_kg)),
            0.1,
        )
        waist = c2.number_input(
            "Waist (cm)", 30.0, 250.0, float(value(item, "waist_cm", 100.0)), 0.1
        )
        bmi = weight / ((PROFILE.height_cm / 100) ** 2)
        c3.number_input("BMI (calculated)", value=round(bmi, 1), disabled=True)
        c1, c2, c3 = st.columns(3)
        resting_hr = c1.number_input(
            "Resting heart rate",
            30,
            220,
            int(synced.get("resting_heart_rate") or value(item, "resting_heart_rate", 70)),
        )
        systolic = c2.number_input(
            "Blood pressure · systolic", 60, 250, int(value(item, "systolic", 120))
        )
        diastolic = c3.number_input(
            "Blood pressure · diastolic", 30, 160, int(value(item, "diastolic", 80))
        )
        c1, c2, c3 = st.columns(3)
        sleep = c1.number_input(
            "Sleep (hours)",
            0.0,
            24.0,
            float(synced.get("sleep_hours") or value(item, "sleep_hours", 8.0)),
            0.25,
        )
        steps = c2.number_input(
            "Steps", 0, 100000, int(synced.get("steps") or value(item, "steps", 0)), 100
        )
        burned = c3.number_input(
            "Calories burned",
            0,
            10000,
            int(synced.get("calories_burned") or value(item, "calories_burned", 0)),
            10,
        )
        date_key = selected.isoformat()
        mood = mobile_rating("Mood", f"mood_{date_key}", int(value(item, "mood", 5)))
        energy = mobile_rating("Energy level", f"energy_{date_key}", int(value(item, "energy", 5)))
        hunger = mobile_rating("Hunger", f"hunger_{date_key}", int(value(item, "hunger", 5)))
        cravings = mobile_rating(
            "Cravings", f"cravings_{date_key}", int(value(item, "cravings", 5))
        )
        satisfaction = mobile_rating(
            "Diet satisfaction",
            f"diet_satisfaction_{date_key}",
            int(value(item, "diet_satisfaction", 7)),
        )

        st.subheader("Habits")
        cols = st.columns(4)
        habits = {}
        for idx, (key, label) in enumerate(
            [
                ("gym", "Gym"),
                ("cardio", "Cardio"),
                ("erg", "ERG"),
                ("supplements", "Supplements"),
                ("protein_powder", "Protein powder"),
                ("alcohol_free", "Alcohol-free"),
                ("physio", "Physio"),
                ("drugs", "Drugs"),
                ("sleep_target", "Sleep target"),
                ("illness", "Illness"),
                ("injury", "Injury"),
                ("unusual_day", "Unusual day"),
            ]
        ):
            habits[key] = cols[idx % 4].checkbox(label, value=bool(value(item, key, False)))

        st.subheader("Fasting")
        fasting_status = st.segmented_control(
            "Fasting status",
            ["Fasted", "Did not fast"],
            default="Fasted" if bool(value(item, "fasted", False)) else "Did not fast",
        )
        fasted = fasting_status == "Fasted"
        fast_start = fast_end = None
        fasting_hours = 0.0
        if fasted:
            fc1, fc2 = st.columns(2)
            default_start = value(
                item, "fast_start", datetime.combine(selected, time(20, 0), LONDON)
            )
            default_end = value(item, "fast_end", datetime.combine(selected, time(12, 0), LONDON))
            start_date = fc1.date_input("Fast started · date", default_start.date())
            start_time = fc1.time_input("Fast started · time", default_start.time())
            end_date = fc2.date_input("Fast broken · date", default_end.date())
            end_time = fc2.time_input("Fast broken at", default_end.time())
            fast_start = datetime.combine(start_date, start_time, LONDON)
            fast_end = datetime.combine(end_date, end_time, LONDON)
            fasting_hours = max(0, (fast_end - fast_start).total_seconds() / 3600)
            st.metric("Fasting duration", f"{fasting_hours:.1f} hours")
        notes = st.text_area("General notes", value=value(item, "notes", ""), height=100)
        submitted = st.form_submit_button(
            "Save daily check-in", use_container_width=True, type="primary"
        )
    if submitted:
        upsert_daily(
            {
                "entry_date": selected,
                "weight_kg": weight,
                "waist_cm": waist,
                "bmi": bmi,
                "resting_heart_rate": resting_hr,
                "systolic": systolic,
                "diastolic": diastolic,
                "sleep_hours": sleep,
                "steps": steps,
                "calories_burned": burned,
                "mood": mood,
                "energy": energy,
                "hunger": hunger,
                "cravings": cravings,
                "diet_satisfaction": satisfaction,
                "fasted": fasted,
                "fast_start": fast_start,
                "fast_end": fast_end,
                "fasting_hours": fasting_hours,
                "notes": notes,
                **habits,
            }
        )
        st.session_state.pop("garmin_sync", None)
        action = "updated" if item is not None else "saved"
        st.session_state["daily_checkin_saved"] = (
            f"Daily check-in {action} for {selected:%d %b %Y}."
        )
        st.rerun()


def weekly_coaching():
    page_watermark("kettlebell", _theme_values[1])
    st.title("Weekly coaching")
    st.caption("Review the trend, choose one focus, and plan around real-life barriers")
    today = datetime.now(LONDON).date()
    week_start = today - timedelta(days=today.weekday())
    df = load_data()
    summary = weekly_coaching_summary(df, today)

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
        focus = st.text_input(
            "One behaviour to focus on",
            value=value(saved, "focus", summary["recommendation"]),
        )
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
        barrier = st.text_input(
            "Anticipated barrier", value=value(saved, "anticipated_barrier", "")
        )
        if_then = st.text_input(
            "If–then response",
            value=value(saved, "if_then_plan", ""),
            placeholder="If work runs late, then I will use the prepared dinner.",
        )
        maintenance = st.toggle(
            "Maintenance mode", value=bool(value(saved, "maintenance_mode", False))
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
                    "maintenance_mode": maintenance,
                }
            )
            st.success("Weekly plan saved.")


def food_log():
    page_watermark("cycling", _theme_values[1])
    st.title("Food journal")
    if saved_message := st.session_state.pop("food_journal_saved", None):
        st.success(saved_message)
    st.caption("Paste your full day of notes. Meals and nutrition will be inferred automatically.")
    selected = st.date_input("Date", date.today(), key="food_date")
    existing = get_nutrition(selected)
    note = st.text_area(
        "Full-day food journal",
        value=existing.raw_note if existing else "",
        height=220,
        placeholder="Breakfast was porridge with banana… Lunch… Later I had…",
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
    page_watermark("swim", _theme_values[1])
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
            x=alt.X("Week:T", title=None),
            y=alt.Y("% of target:Q", title="Target %"),
            strokeDash=alt.StrokeDash("Nutrient:N", legend=alt.Legend(orient="bottom")),
            color=alt.Color("Nutrient:N", legend=None, scale=alt.Scale(range=palette["series"])),
            tooltip=["Week:T", "Nutrient:N", alt.Tooltip("% of target:Q", format=".0f")],
        )
    )
    target_line = (
        alt.Chart(pd.DataFrame({"y": [100]}))
        .mark_rule(strokeDash=[5, 5], color=_theme_values[1], opacity=0.65)
        .encode(y="y:Q")
    )
    st.altair_chart(style_chart(weekly_chart + target_line), use_container_width=True, theme=None)

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
    page_watermark("stretch", _theme_values[1])
    st.title("Appearance")
    if st.session_state.pop("appearance_saved", False):
        st.success("Appearance settings saved.")
    st.caption("Make the tracker feel like your own")
    with Session(engine) as session:
        prefs = session.get(AppPreferences, 1)
        mode = st.segmented_control(
            "Mode", ["light", "dark"], default=prefs.color_mode, format_func=str.title
        )
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
            help="Use rolling averages for clearer trends. Turn off to show every recorded value.",
        )
        st.markdown(
            f'<div style="font-family:{FONTS[font]};font-size:1.15rem;padding:.5rem 0">'
            f"Selected: {font} — The quick brown fox — 0123456789</div>",
            unsafe_allow_html=True,
        )
        if st.button("Save appearance", type="primary", use_container_width=True):
            try:
                prefs.accent = normalize_color(typed_color or picked_color)
                prefs.color_mode = mode or "light"
                prefs.font_family = font
                prefs.smooth_charts = smooth_charts
                session.commit()
                st.session_state.appearance_saved = True
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


def settings_page():
    page_watermark("target", _theme_values[1])
    st.title("Targets, backup and privacy")
    with Session(engine) as session:
        goals = session.get(GoalSettings, 1)
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
            if st.form_submit_button("Save targets", type="primary"):
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
        st.Page(appearance_page, title="Appearance"),
        st.Page(settings_page, title="Targets & export"),
    ]
)
page.run()
