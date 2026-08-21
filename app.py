from __future__ import annotations

import io
import json
from datetime import date, datetime, time

import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy.orm import Session

from health_tracker.analytics import (
    bmi_status,
    current_streak,
    daily_health_score,
    excel_safe_data,
    load_data,
    projected_target_date,
)
from health_tracker.auth import require_login
from health_tracker.config import LONDON, PROFILE, setting
from health_tracker.db import engine, get_daily, get_nutrition, init_db, upsert_daily
from health_tracker.garmin import sync_day
from health_tracker.models import AppPreferences, GoalSettings
from health_tracker.nutrition import analyse_day, save_estimate
from health_tracker.quotes import QUOTES, daily_item
from health_tracker.research import RESEARCH_INSIGHTS
from health_tracker.theme import FONTS, apply_theme, derived_palette, normalize_color
from health_tracker.visuals import optional_home_logo, page_watermark

st.set_page_config(page_title="Health Journey", layout="wide")
init_db()
require_login()

with Session(engine) as _theme_session:
    _preferences = _theme_session.get(AppPreferences, 1)
    _theme_values = (_preferences.color_mode, _preferences.accent, _preferences.font_family)
apply_theme(*_theme_values)


def value(item, name, default=None):
    result = getattr(item, name, None) if item is not None else None
    return default if result is None else result


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
    if st.session_state.get("home_research", False):
        research = daily_item(RESEARCH_INSIGHTS, london_day)
        st.markdown(
            f"""
            <div class="quote-card">
              <div class="quote-label">RESEARCH NOTE</div>
              <div class="quote-text">{research["insight"]}</div>
              <p><a href="{research["url"]}" target="_blank">{research["source"]}</a></p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Show today's inspiration", use_container_width=True):
            st.session_state.home_research = False
            st.rerun()
    else:
        quote = daily_item(QUOTES, london_day)
        st.markdown(
            f"""
            <div class="quote-card">
              <div class="quote-label">TODAY'S THOUGHT</div>
              <div class="quote-text">“{quote}”</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Show today's research note", use_container_width=True):
            st.session_state.home_research = True
            st.rerun()


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
    a, b, c, d = st.columns(4)
    a.metric("Current weight", f"{latest_weight:.1f} kg" if latest_weight else "—")
    b.metric("Goal progress", f"{max(0, min(100, progress * 100)):.0f}%")
    c.metric("Logging streak", f"{current_streak(df)} days")
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
    smooth_weight = st.checkbox("Smooth weight (7-entry rolling average)", key="smooth_weight")
    weight = df[["entry_date", "weight_kg"]].dropna().copy()
    if not weight.empty:
        weight["display_value"] = (
            weight.weight_kg.rolling(7, min_periods=1).mean() if smooth_weight else weight.weight_kg
        )
        weight_line = (
            alt.Chart(weight)
            .mark_line(
                point=(
                    alt.OverlayMarkDef(
                        filled=True, fill=accent, stroke=accent, strokeWidth=2, size=72
                    )
                    if not smooth_weight
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
    smooth_calories = st.checkbox(
        "Smooth calories and activity (7-entry rolling average)", key="smooth_calories"
    )
    fields = [
        field
        for field in ["calories", "calories_burned"]
        if field in df and df[field].notna().any()
    ]
    if fields:
        calories = df[["entry_date", *fields]].copy()
        if smooth_calories:
            calories[fields] = calories[fields].rolling(7, min_periods=1).mean()
        melted = calories.melt("entry_date", fields, var_name="measure", value_name="kcal").dropna()
        chart = (
            alt.Chart(melted)
            .mark_line(point=not smooth_calories, strokeWidth=4)
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
    smooth_kpi = st.checkbox(
        "Smooth selected KPI (7-entry rolling average)", key="smooth_recent_kpi"
    )
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
            if smooth_kpi
            else recent[selected_kpi]
        )
        kpi_chart = (
            alt.Chart(recent)
            .mark_line(
                point=(
                    alt.OverlayMarkDef(
                        filled=True, fill=accent, stroke=accent, strokeWidth=2, size=72
                    )
                    if not smooth_kpi
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
    if st.session_state.pop("daily_checkin_saved", False):
        st.success("Daily check-in saved.")
    selected = st.date_input("Date", date.today())
    item = get_daily(selected)
    with st.expander("Garmin sync", expanded=False):
        st.caption("Imports steps, calories burned, sleep, resting heart rate, and activity data.")
        if st.button("Sync Garmin for this date", use_container_width=True):
            try:
                with st.spinner("Connecting to Garmin…"):
                    synced = sync_day(selected)
                st.session_state["garmin_sync"] = synced
                st.success(f"Synced {len(synced['activities'])} activities.")
            except Exception as exc:
                st.error(f"Garmin sync failed: {exc}")
    synced = st.session_state.get("garmin_sync", {})

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
        mood = st.slider("Mood", 1, 10, int(value(item, "mood", 5)))
        energy = st.slider("Energy level", 1, 10, int(value(item, "energy", 5)))

        st.subheader("Habits")
        cols = st.columns(4)
        habits = {}
        for idx, (key, label) in enumerate(
            [
                ("gym", "Gym"),
                ("cardio", "Cardio"),
                ("erg", "ERG"),
                ("supplements", "Supplements"),
                ("alcohol_free", "Alcohol-free"),
                ("physio", "Physio"),
                ("drugs", "Drugs"),
                ("sleep_target", "Sleep target"),
            ]
        ):
            habits[key] = cols[idx % 4].checkbox(label, value=bool(value(item, key, False)))

        st.subheader("Fasting")
        fasted = st.toggle("I fasted", value=bool(value(item, "fasted", False)))
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
            end_date = fc2.date_input("Fast ended · date", default_end.date())
            end_time = fc2.time_input("Fast ended · time", default_end.time())
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
                "fasted": fasted,
                "fast_start": fast_start,
                "fast_end": fast_end,
                "fasting_hours": fasting_hours,
                "notes": notes,
                **habits,
            }
        )
        st.session_state["daily_checkin_saved"] = True
        st.rerun()


def food_log():
    page_watermark("cycling", _theme_values[1])
    st.title("Food journal")
    st.caption("Paste your full day of notes. Meals and nutrition will be inferred automatically.")
    selected = st.date_input("Date", date.today(), key="food_date")
    existing = get_nutrition(selected)
    if existing:
        st.markdown(
            "<div class='neutral-note'>This day already has a saved food journal. Edit the text "
            "below and recalculate to replace its nutrition estimate.</div>",
            unsafe_allow_html=True,
        )
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
                st.success("Food journal and nutrition estimate updated.")
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

    rows = []
    for _, row in nutrition.iterrows():
        for label, field in fields.items():
            if pd.notna(row[field]):
                rows.append(
                    {
                        "Date": row.entry_date,
                        "Nutrient": label,
                        "% of target": float(row[field]) / targets[label] * 100,
                    }
                )
    long = pd.DataFrame(rows)
    st.subheader("Daily target balance")
    palette = derived_palette(*_theme_values[:2])
    daily_chart = (
        alt.Chart(long)
        .mark_rect(cornerRadius=3)
        .encode(
            x=alt.X("Date:T", title=None),
            y=alt.Y("Nutrient:N", title=None),
            color=alt.Color(
                "% of target:Q",
                scale=alt.Scale(domain=[50, 100, 150], range=palette["scale"]),
                legend=alt.Legend(orient="bottom"),
            ),
            tooltip=["Date:T", "Nutrient:N", alt.Tooltip("% of target:Q", format=".0f")],
        )
    )
    st.altair_chart(style_chart(daily_chart), use_container_width=True, theme=None)

    nutrition["week"] = nutrition.entry_date.dt.to_period("W").dt.start_time
    weekly = nutrition.groupby("week", as_index=False)[list(fields.values())].mean()
    weekly_rows = [
        {"Week": row.week, "Nutrient": label, "% of target": row[field] / targets[label] * 100}
        for _, row in weekly.iterrows()
        for label, field in fields.items()
    ]
    st.subheader("Weekly average vs target")
    smooth_weekly = st.checkbox(
        "Smooth weekly nutrition (3-week rolling average)", key="smooth_weekly_nutrition"
    )
    weekly_frame = pd.DataFrame(weekly_rows)
    if smooth_weekly:
        weekly_frame["% of target"] = weekly_frame.groupby("Nutrient")["% of target"].transform(
            lambda values: values.rolling(3, min_periods=1).mean()
        )
    weekly_chart = (
        alt.Chart(weekly_frame)
        .mark_line(point=not smooth_weekly, strokeWidth=3)
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
                session.commit()
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
    csv = data.to_csv(index=False).encode()
    st.download_button(
        "Download all data as CSV", csv, "health-journey.csv", "text/csv", use_container_width=True
    )
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        excel_safe_data(data).to_excel(writer, index=False, sheet_name="Journey")
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
        st.Page(appearance_page, title="Appearance"),
        st.Page(settings_page, title="Targets & export"),
    ]
)
page.run()
