from __future__ import annotations

import io
import json
import secrets
from datetime import date, datetime, time

import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy.orm import Session

from health_tracker.analytics import current_streak, load_data, projected_target_date
from health_tracker.auth import require_login
from health_tracker.config import LONDON, PROFILE, setting
from health_tracker.db import engine, get_daily, get_nutrition, init_db, upsert_daily
from health_tracker.garmin import sync_day
from health_tracker.models import AppPreferences, GoalSettings
from health_tracker.nutrition import analyse_day, save_estimate
from health_tracker.quotes import QUOTES
from health_tracker.theme import ACCENTS, FONTS, apply_theme

st.set_page_config(page_title="Health Journey", layout="wide")
init_db()
require_login()

with Session(engine) as _theme_session:
    _preferences = _theme_session.get(AppPreferences, 1)
    _theme_values = (_preferences.color_mode, _preferences.accent, _preferences.font_family)
apply_theme(*_theme_values)


def value(item, name, default=None):
    result = getattr(item, name, None) if item else None
    return default if result is None else result


def home():
    if "opening_quote" not in st.session_state:
        st.session_state.opening_quote = secrets.choice(QUOTES)
    st.title("Welcome back")
    st.caption("Your private space for a stronger, healthier year")
    st.markdown(
        f"""
        <div class="quote-card">
          <div class="quote-label">TODAY'S THOUGHT</div>
          <div class="quote-text">“{st.session_state.opening_quote}”</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='neutral-note'>Use the menu to complete today's check-in, log food, "
        "and review your progress.</div>",
        unsafe_allow_html=True,
    )


def dashboard():
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

    if df.empty:
        st.info("Add your first daily entry to begin the dashboard.")
        return
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    left, right = st.columns(2)
    with left:
        st.subheader("Weight trend")
        weight = df.dropna(subset=["weight_kg"])
        if not weight.empty:
            chart = (
                alt.Chart(weight)
                .mark_line(point=True)
                .encode(
                    x=alt.X("entry_date:T", title=None),
                    y=alt.Y("weight_kg:Q", title="kg", scale=alt.Scale(zero=False)),
                )
            )
            st.altair_chart(chart, use_container_width=True)
        else:
            st.caption("No weight entries yet.")
    with right:
        st.subheader("Calories and activity")
        fields = [
            field
            for field in ["calories", "calories_burned"]
            if field in df and df[field].notna().any()
        ]
        if fields:
            melted = df.melt("entry_date", fields, var_name="measure", value_name="kcal").dropna()
            st.altair_chart(
                alt.Chart(melted)
                .mark_line(point=True)
                .encode(x=alt.X("entry_date:T", title=None), y="kcal:Q", color="measure:N"),
                use_container_width=True,
            )
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
    st.dataframe(
        df[kpis].tail(14).sort_values("entry_date", ascending=False),
        hide_index=True,
        use_container_width=True,
    )


def daily_entry():
    st.title("Daily check-in")
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
        c3.metric("BMI (calculated)", f"{bmi:.1f}")
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
                ("sufficient_water", "Sufficient water"),
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
        st.success("Daily check-in saved.")


def food_log():
    st.title("Food journal")
    st.caption("Paste your full day of notes. Meals and nutrition will be inferred automatically.")
    selected = st.date_input("Date", date.today(), key="food_date")
    existing = get_nutrition(selected)
    note = st.text_area(
        "What did you eat and drink?",
        value=existing.raw_note if existing else "",
        height=220,
        placeholder="Breakfast was porridge with banana… Lunch… Later I had…",
        label_visibility="collapsed",
    )
    if st.button(
        "Analyse and save day", type="primary", use_container_width=True, disabled=not note.strip()
    ):
        if not setting("OPENAI_API_KEY"):
            st.error("OPENAI_API_KEY is not configured.")
        else:
            try:
                with st.spinner("Estimating meals and nutrition…"):
                    estimate, model = analyse_day(note)
                    save_estimate(selected, note, estimate, model)
                st.success("Nutrition saved.")
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
        st.warning("AI nutrition values are estimates and are not medical advice.")


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
    st.altair_chart(
        alt.Chart(long)
        .mark_rect(cornerRadius=3)
        .encode(
            x=alt.X("Date:T", title=None),
            y=alt.Y("Nutrient:N", title=None),
            color=alt.Color(
                "% of target:Q",
                scale=alt.Scale(domain=[50, 100, 150], range=["#D8664F", "#2A9D8F", "#7057C7"]),
            ),
            tooltip=["Date:T", "Nutrient:N", alt.Tooltip("% of target:Q", format=".0f")],
        ),
        use_container_width=True,
    )

    nutrition["week"] = nutrition.entry_date.dt.to_period("W").dt.start_time
    weekly = nutrition.groupby("week", as_index=False)[list(fields.values())].mean()
    weekly_rows = [
        {"Week": row.week, "Nutrient": label, "% of target": row[field] / targets[label] * 100}
        for _, row in weekly.iterrows()
        for label, field in fields.items()
    ]
    st.subheader("Weekly average vs target")
    weekly_chart = (
        alt.Chart(pd.DataFrame(weekly_rows))
        .mark_line(point=True)
        .encode(
            x=alt.X("Week:T", title=None),
            y=alt.Y("% of target:Q", title="Target %"),
            color="Nutrient:N",
            tooltip=["Week:T", "Nutrient:N", alt.Tooltip("% of target:Q", format=".0f")],
        )
    )
    target_line = alt.Chart(pd.DataFrame({"y": [100]})).mark_rule(strokeDash=[5, 5]).encode(y="y:Q")
    st.altair_chart(weekly_chart + target_line, use_container_width=True)

    overall = [
        {"Nutrient": label, "% of target": nutrition[field].mean() / targets[label] * 100}
        for label, field in fields.items()
    ]
    st.subheader("Overall average")
    st.altair_chart(
        alt.Chart(pd.DataFrame(overall))
        .mark_bar(cornerRadiusEnd=8)
        .encode(
            x=alt.X("% of target:Q", title="Average target achievement (%)"),
            y=alt.Y("Nutrient:N", sort=None, title=None),
            color=alt.condition(
                "datum['% of target'] >= 80 && datum['% of target'] <= 120",
                alt.value("#2A9D8F"),
                alt.value("#D8664F"),
            ),
            tooltip=["Nutrient:N", alt.Tooltip("% of target:Q", format=".0f")],
        ),
        use_container_width=True,
    )
    st.warning("Indicators use AI food estimates and are informational, not medical advice.")


def appearance_page():
    st.title("Appearance")
    st.caption("Make the tracker feel like your own")
    with Session(engine) as session:
        prefs = session.get(AppPreferences, 1)
        with st.form("appearance"):
            mode = st.segmented_control(
                "Mode", ["light", "dark"], default=prefs.color_mode, format_func=str.title
            )
            accent_name = st.selectbox(
                "Main accent colour",
                list(ACCENTS),
                index=(
                    list(ACCENTS.values()).index(prefs.accent)
                    if prefs.accent in ACCENTS.values()
                    else 0
                ),
            )
            font = st.selectbox(
                "Font",
                list(FONTS),
                index=(list(FONTS).index(prefs.font_family) if prefs.font_family in FONTS else 0),
            )
            st.color_picker("Selected accent", ACCENTS[accent_name], disabled=True)
            if st.form_submit_button("Save appearance", type="primary", use_container_width=True):
                prefs.color_mode = mode or "light"
                prefs.accent = ACCENTS[accent_name]
                prefs.font_family = font
                session.commit()
                st.rerun()


def settings_page():
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
        data.to_excel(writer, index=False, sheet_name="Journey")
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
