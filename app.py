from __future__ import annotations

import calendar
import hashlib
import hmac
import os
from datetime import date, datetime, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from db import initialise_database, metrics, save_metrics, save_session, sessions

st.set_page_config(page_title="Lift Log", page_icon="🏋️", layout="wide", initial_sidebar_state="collapsed")

LIME = "#c8fa27"
ORANGE = "#ff9a6b"
BLUE = "#62c8f5"
BG = "#0d100e"
PANEL = "#171b18"
MUTED = "#909891"

st.markdown(f"""
<style>
  .stApp {{ background:{BG}; color:#f5f7f4; }}
  .block-container {{max-width:1100px; padding:1.5rem 1rem 6rem;}}
  h1,h2,h3 {{ color:#f7f8f6 !important; letter-spacing:-.04em; }}
  .eyebrow {{color:{MUTED};font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;}}
  .subtle {{color:{MUTED};font-size:.92rem;}}
  .lift-card {{background:{PANEL};border:1px solid #272d29;border-radius:16px;padding:1rem 1.1rem;margin:.4rem 0 .9rem;}}
  .stat-number {{font-size:2rem;font-weight:750;line-height:1.05;}}
  .lime {{color:{LIME};}} .orange {{color:{ORANGE};}} .blue {{color:{BLUE};}}
  [data-testid="stMetric"] {{background:{PANEL};border:1px solid #272d29;border-radius:14px;padding:14px;}}
  [data-testid="stMetricValue"] {{color:#f7f8f6;}}
  div.stButton > button {{background:{LIME};color:#10130f;border:0;border-radius:12px;font-weight:750;min-height:44px; width:100%;}}
  div.stButton > button:hover {{background:#d9ff52;color:#10130f;}}
  [data-baseweb="input"] > div, [data-baseweb="select"] > div, .stTextArea textarea {{background:#101310 !important;border-color:#303832 !important;color:#f5f7f4 !important;border-radius:10px !important;}}
  .stTabs [data-baseweb="tab-list"] {{gap:.35rem;}} .stTabs [data-baseweb="tab"] {{background:#171b18;border:1px solid #272d29;border-radius:10px;color:#d5d9d4;padding:.5rem 1rem;}}
  .stTabs [aria-selected="true"] {{background:{LIME};color:#10130f !important;}}
  @media(max-width:640px) {{ .block-container{{padding:.8rem .75rem 5.5rem;}} h1{{font-size:2rem !important;}} [data-testid="stHorizontalBlock"]{{gap:.45rem;}} }}
</style>
""", unsafe_allow_html=True)


def secret(key: str, fallback: str = "") -> str:
    try:
        return st.secrets.get(key, fallback)
    except FileNotFoundError:
        return os.getenv(key, fallback)


def signed_in() -> bool:
    if st.session_state.get("authenticated"):
        return True
    st.markdown("<div style='max-width:420px;margin:12vh auto 0'>", unsafe_allow_html=True)
    st.markdown("<div class='eyebrow'>Private training journal</div><h1>Lift Log</h1><p class='subtle'>Sign in to log today's session and see your progress.</p>", unsafe_allow_html=True)
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
    expected_user = secret("APP_USERNAME", "admin")
    expected_password = secret("APP_PASSWORD", "change-me")
    if submitted:
        if hmac.compare_digest(username, expected_user) and hmac.compare_digest(password, expected_password):
            st.session_state.authenticated = True
            st.rerun()
        st.error("That username or password isn't right.")
    st.caption("Set APP_USERNAME and APP_PASSWORD in Streamlit secrets before deployment.")
    st.markdown("</div>", unsafe_allow_html=True)
    return False


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def next_workout(data: pd.DataFrame) -> str:
    cycle = ["Push", "Pull", "Legs"]
    if data.empty:
        return "Push"
    last = data.sort_values("session_date").iloc[-1].workout_type
    return cycle[(cycle.index(last) + 1) % len(cycle)] if last in cycle else "Push"


def next_workout_for_date(data: pd.DataFrame, session_day: date) -> str:
    """Suggest the next split using sessions logged before the selected day."""
    if data.empty:
        return "Push"
    earlier = data[data.session_date.dt.date < session_day]
    return next_workout(earlier)


def card(title: str, value: str, caption: str = "", tint: str = "lime") -> None:
    st.markdown(f"<div class='lift-card'><div class='eyebrow'>{title}</div><div class='stat-number {tint}'>{value}</div><div class='subtle'>{caption}</div></div>", unsafe_allow_html=True)


def chart(frame: pd.DataFrame, x: str, y: str, color: str = LIME, height: int = 230):
    fig = px.line(frame, x=x, y=y, markers=True)
    fig.update_traces(line_color=color, marker_color=color, line_width=3)
    fig.update_layout(height=height, margin=dict(l=0,r=0,t=10,b=0), paper_bgcolor=PANEL, plot_bgcolor=PANEL,
        font_color="#dfe4df", xaxis_title=None, yaxis_title=None, showlegend=False,
        xaxis=dict(gridcolor="#242a26"), yaxis=dict(gridcolor="#242a26"))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def today_view(data: pd.DataFrame) -> None:
    suggested = next_workout(data)
    today = date.today()
    count = len(data[(data.session_date.dt.date >= week_start(today)) & (data.session_date.dt.date <= today)]) if not data.empty else 0
    st.markdown(f"<div class='eyebrow'>{today.strftime('%a · %d %b %Y')}</div><h1>{suggested} day</h1><p class='subtle'>Session {min(count + 1, 4)} of 4 this week · next in your rotating split</p>", unsafe_allow_html=True)
    progress = min(count / 4, 1)
    st.progress(progress, text=f"{count} of 4 sessions done")
    workout_entry_form(data, today, "today_workout_entry")


def workout_entry_form(data: pd.DataFrame, session_day: date, form_key: str) -> None:
    """Create or edit a completed workout for any calendar day."""
    existing = data[data.session_date.dt.date == session_day] if not data.empty else pd.DataFrame()
    default_type = existing.iloc[0].workout_type if not existing.empty else next_workout_for_date(data, session_day)
    action = "Update workout" if not existing.empty else "Mark workout complete"
    with st.form(form_key, clear_on_submit=False):
        left, right = st.columns([1, 1])
        workout_type = left.selectbox("Workout type", ["Push", "Pull", "Legs"], index=["Push", "Pull", "Legs"].index(default_type))
        volume = right.number_input("Total volume (kg, optional)", min_value=0.0, step=10.0, value=float(existing.iloc[0].volume_kg) if not existing.empty else 0.0)
        exercise_log = st.text_area("Exercises, sets, reps and weights", value=existing.iloc[0].exercise_log if not existing.empty else "", height=150, placeholder="Barbell Bench Press - 3 x 8 x 72.5 kg\nOverhead Press - 3 x 8 x 40 kg")
        notes = st.text_area("Workout notes", value=existing.iloc[0].notes if not existing.empty else "", height=100, placeholder="How it felt, form cues, what to change next time...")
        saved = st.form_submit_button(action)
    if saved:
        save_session(session_day, workout_type, notes, exercise_log, volume)
        st.success(f"{workout_type} saved for {session_day.strftime('%d %b %Y')}.")
        st.rerun()


def week_view(data: pd.DataFrame) -> None:
    start = week_start(date.today())
    end = start + timedelta(days=6)
    current = data[(data.session_date.dt.date >= start) & (data.session_date.dt.date <= end)] if not data.empty else pd.DataFrame()
    st.markdown(f"<div class='eyebrow'>{start.strftime('%d %b')} - {end.strftime('%d %b %Y')}</div><h1>This week</h1>", unsafe_allow_html=True)
    a,b,c = st.columns(3)
    a.metric("Sessions", f"{len(current)} / 4", "Goal: 4 workouts")
    b.metric("Volume", f"{current.volume_kg.sum()/1000:.1f} t" if not current.empty else "0 t")
    c.metric("Split balance", f"{current.workout_type.nunique() if not current.empty else 0}/3")
    st.progress(min(len(current)/4,1), text=f"{max(0, 4-len(current))} sessions left to reach your goal")
    if not current.empty:
        daily = current.assign(day=current.session_date.dt.strftime("%a")).groupby("day", as_index=False).volume_kg.sum()
        st.markdown("### Volume by day")
        fig = px.bar(daily, x="day", y="volume_kg", color_discrete_sequence=[LIME])
        fig.update_layout(height=250, paper_bgcolor=PANEL, plot_bgcolor=PANEL, font_color="#dfe4df", margin=dict(l=0,r=0,t=10,b=0), xaxis_title=None, yaxis_title="kg")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        st.markdown("### Completed sessions")
        for row in current.sort_values("session_date").itertuples():
            st.markdown(f"<div class='lift-card'><b class='orange'>{row.workout_type}</b> · {row.session_date.strftime('%a %d %b')}<br><span class='subtle'>{row.exercise_log or row.notes or 'No notes added'}</span></div>", unsafe_allow_html=True)
    else:
        st.info("No sessions logged this week yet. Start with today's workout.")


def month_view(data: pd.DataFrame) -> None:
    if "month_cursor" not in st.session_state:
        st.session_state.month_cursor = date.today().replace(day=1)
    cursor = st.session_state.month_cursor
    if "month_selected_date" not in st.session_state:
        st.session_state.month_selected_date = None
    previous, heading, following = st.columns([1, 4, 1])
    if previous.button("←", key="previous_month"):
        st.session_state.month_cursor = (cursor - timedelta(days=1)).replace(day=1)
        st.session_state.month_selected_date = None
        st.rerun()
    heading.markdown(f"<div class='eyebrow'>{cursor.strftime('%B %Y')}</div><h1>Month overview</h1>", unsafe_allow_html=True)
    if following.button("→", key="next_month"):
        st.session_state.month_cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        st.session_state.month_selected_date = None
        st.rerun()
    year, month = cursor.year, cursor.month
    current = data[(data.session_date.dt.year == year) & (data.session_date.dt.month == month)] if not data.empty else pd.DataFrame()
    a,b,c = st.columns(3); a.metric("Sessions", f"{len(current)} / 16"); b.metric("Volume", f"{current.volume_kg.sum()/1000:.1f} t" if not current.empty else "0 t"); c.metric("PRs", "Track in notes")
    events = {int(row.session_date.day): row.workout_type for row in current.itertuples()} if not current.empty else {}
    weeks = calendar.monthcalendar(year, month)
    headers = st.columns(7)
    for col, label in zip(headers, ["M", "T", "W", "T", "F", "S", "S"]): col.markdown(f"<div class='eyebrow' style='text-align:center'>{label}</div>", unsafe_allow_html=True)
    for wk in weeks:
        cols = st.columns(7)
        for col, day in zip(cols, wk):
            if day:
                mark = events.get(day, "")
                label = {"Push": "Pu", "Pull": "Pl", "Legs": "Lg"}.get(mark, "")
                tone = {"Push": "orange", "Pull": "blue", "Legs": "lime"}.get(mark, "")
                is_selected = st.session_state.month_selected_date == date(year, month, day)
                button_label = f"{day}" + (f" · {label}" if label else "")
                if col.button(button_label, key=f"calendar_{year}_{month}_{day}", use_container_width=True, type="primary" if is_selected else "secondary"):
                    st.session_state.month_selected_date = date(year, month, day)
                    st.rerun()
    selected_day = st.session_state.month_selected_date
    if selected_day and selected_day.year == year and selected_day.month == month:
        st.markdown(f"### Log workout · {selected_day.strftime('%a, %d %b')}")
        st.caption("Select a date above to add a past session or edit a completed one.")
        workout_entry_form(data, selected_day, f"calendar_workout_{selected_day.isoformat()}")
    else:
        st.caption("Tap a date to log or edit that day's workout.")
    if not data.empty:
        st.markdown("### Sessions by week")
        series = current.set_index("session_date").resample("W-MON").size().reset_index(name="sessions")
        chart(series, "session_date", "sessions", BLUE)


def body_view(metric_data: pd.DataFrame) -> None:
    start = week_start(date.today())
    latest = metric_data.iloc[0] if not metric_data.empty else None
    st.markdown(f"<div class='eyebrow'>Week of {start.strftime('%d %b')}</div><h1>Body stats</h1><p class='subtle'>One entry per week. Keep it simple and consistent.</p>", unsafe_allow_html=True)
    with st.form("body_stats"):
        a,b = st.columns(2); weight = a.number_input("Weight (kg)", min_value=0.0, step=0.1, value=float(latest.weight_kg) if latest is not None and pd.notna(latest.weight_kg) else 0.0); muscle = b.number_input("Muscle mass (kg)", min_value=0.0, step=0.1, value=float(latest.muscle_mass_kg) if latest is not None and pd.notna(latest.muscle_mass_kg) else 0.0)
        c,d = st.columns(2); fat_kg = c.number_input("Body fat (kg)", min_value=0.0, step=0.1, value=float(latest.body_fat_kg) if latest is not None and pd.notna(latest.body_fat_kg) else 0.0); fat_pct = d.number_input("Body fat (%)", min_value=0.0, max_value=100.0, step=0.1, value=float(latest.body_fat_percent) if latest is not None and pd.notna(latest.body_fat_percent) else 0.0)
        submitted = st.form_submit_button("Save this week")
    if submitted:
        save_metrics(start, weight or None, muscle or None, fat_kg or None, fat_pct or None); st.success("Body stats saved."); st.rerun()
    if not metric_data.empty:
        st.markdown("### Weight, last 12 weeks")
        chart(metric_data.sort_values("week_start").tail(12), "week_start", "weight_kg")
        st.markdown("### Recent history")
        show = metric_data[["week_start", "weight_kg", "muscle_mass_kg", "body_fat_kg", "body_fat_percent"]].head(8).copy(); show["week_start"] = show.week_start.dt.strftime("%d %b")
        st.dataframe(show, hide_index=True, use_container_width=True)


def year_view(data: pd.DataFrame, metric_data: pd.DataFrame) -> None:
    today = date.today(); current = data[data.session_date.dt.year == today.year] if not data.empty else pd.DataFrame()
    st.markdown(f"<div class='eyebrow'>{today.year}</div><h1>Year in review</h1>", unsafe_allow_html=True)
    a,b,c = st.columns(3); a.metric("Sessions", f"{len(current)} / {date(today.year,12,31).isocalendar().week * 4}"); b.metric("Volume", f"{current.volume_kg.sum()/1000:.1f} t" if not current.empty else "0 t"); c.metric("Consistency", f"{min(round(len(current)/(today.isocalendar().week*4)*100),100)}%" if today.isocalendar().week else "0%")
    if not current.empty:
        monthly = current.set_index("session_date").resample("ME").size().reset_index(name="sessions"); monthly["month"] = monthly.session_date.dt.strftime("%b")
        fig = px.bar(monthly, x="month", y="sessions", color_discrete_sequence=[LIME]); fig.update_layout(height=280,paper_bgcolor=PANEL,plot_bgcolor=PANEL,font_color="#dfe4df",margin=dict(l=0,r=0,t=10,b=0),xaxis_title=None,yaxis_title="Sessions")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False})
    if not metric_data.empty and metric_data.weight_kg.notna().any():
        st.markdown("### Body weight trend")
        chart(metric_data.sort_values("week_start"), "week_start", "weight_kg")


initialise_database()
if signed_in():
    data, metric_data = sessions(), metrics()
    st.markdown("<div style='display:flex;align-items:center;justify-content:space-between'><div><span class='eyebrow'>LIFT LOG</span></div></div>", unsafe_allow_html=True)
    pages = ["Today", "Week", "Month", "Year", "Body"]
    selected = st.radio("Navigation", pages, horizontal=True, label_visibility="collapsed")
    if selected == "Today": today_view(data)
    elif selected == "Week": week_view(data)
    elif selected == "Month": month_view(data)
    elif selected == "Year": year_view(data, metric_data)
    elif selected == "Body": body_view(metric_data)
