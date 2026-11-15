"""Small persistence layer for Lift Log.

Use SQLite locally. On Streamlit Cloud, set DATABASE_URL to a Postgres URL so
workout data survives app restarts and deployments.
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text


def _database_url() -> str:
    configured = os.getenv("DATABASE_URL")
    if configured:
        return configured.replace("postgres://", "postgresql://", 1)
    return f"sqlite:///{Path(__file__).parent / 'lift_log.db'}"


ENGINE = create_engine(_database_url(), future=True)


def initialise_database() -> None:
    statements = [
        """CREATE TABLE IF NOT EXISTS workout_sessions (
            session_date DATE PRIMARY KEY,
            workout_type VARCHAR(20) NOT NULL,
            notes TEXT,
            exercise_log TEXT,
            volume_kg REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS body_metrics (
            week_start DATE PRIMARY KEY,
            weight_kg REAL,
            muscle_mass_kg REAL,
            body_fat_kg REAL,
            body_fat_percent REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
    ]
    with ENGINE.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def sessions() -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM workout_sessions ORDER BY session_date DESC", ENGINE, parse_dates=["session_date"])


def metrics() -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM body_metrics ORDER BY week_start DESC", ENGINE, parse_dates=["week_start"])


def save_session(session_date: date, workout_type: str, notes: str, exercise_log: str, volume_kg: float) -> None:
    query = text("""INSERT INTO workout_sessions (session_date, workout_type, notes, exercise_log, volume_kg)
        VALUES (:session_date, :workout_type, :notes, :exercise_log, :volume_kg)
        ON CONFLICT(session_date) DO UPDATE SET workout_type = excluded.workout_type,
        notes = excluded.notes, exercise_log = excluded.exercise_log, volume_kg = excluded.volume_kg""")
    with ENGINE.begin() as conn:
        conn.execute(query, {"session_date": session_date, "workout_type": workout_type, "notes": notes,
                             "exercise_log": exercise_log, "volume_kg": volume_kg})


def save_metrics(week_start: date, weight: float | None, muscle: float | None, fat_kg: float | None, fat_pct: float | None) -> None:
    query = text("""INSERT INTO body_metrics (week_start, weight_kg, muscle_mass_kg, body_fat_kg, body_fat_percent)
        VALUES (:week_start, :weight, :muscle, :fat_kg, :fat_pct)
        ON CONFLICT(week_start) DO UPDATE SET weight_kg = excluded.weight_kg,
        muscle_mass_kg = excluded.muscle_mass_kg, body_fat_kg = excluded.body_fat_kg,
        body_fat_percent = excluded.body_fat_percent""")
    with ENGINE.begin() as conn:
        conn.execute(query, {"week_start": week_start, "weight": weight, "muscle": muscle,
                             "fat_kg": fat_kg, "fat_pct": fat_pct})
