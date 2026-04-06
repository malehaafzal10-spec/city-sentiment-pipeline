"""
db.py — SQLite setup and connection helper.
Run once at startup via init_db().
"""

import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("PIPELINE_DB_PATH", "artifacts/pipeline.db")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS raw_documents (
            doc_id         TEXT PRIMARY KEY,
            source         TEXT NOT NULL,
            city           TEXT NOT NULL,
            title          TEXT,
            text           TEXT,
            published_at   TEXT,
            url            TEXT,
            ingestion_time TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cleaned_documents (
            doc_id       TEXT PRIMARY KEY,
            city         TEXT NOT NULL,
            source       TEXT NOT NULL,
            clean_text   TEXT NOT NULL,
            text_length  INTEGER,
            processed_at TEXT NOT NULL,
            run_id       TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS scored_documents (
            doc_id          TEXT PRIMARY KEY,
            city            TEXT NOT NULL,
            sentiment_label TEXT NOT NULL,
            sentiment_score REAL NOT NULL,
            scored_at       TEXT NOT NULL,
            run_id          TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS city_weekly_metrics (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            city           TEXT NOT NULL,
            week_start     TEXT NOT NULL,
            mention_count  INTEGER NOT NULL,
            avg_sentiment  REAL NOT NULL,
            positive_ratio REAL NOT NULL,
            negative_ratio REAL NOT NULL,
            neutral_ratio  REAL NOT NULL,
            crowding_score REAL,
            cost_score     REAL,
            safety_score   REAL,
            llm_verdict    TEXT,
            run_id         TEXT NOT NULL,
            computed_at    TEXT NOT NULL,
            UNIQUE(city, week_start)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS monitoring_alerts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            city          TEXT NOT NULL,
            week_start    TEXT NOT NULL,
            alert_type    TEXT NOT NULL,
            alert_message TEXT NOT NULL,
            severity      TEXT NOT NULL,
            triggered_at  TEXT NOT NULL,
            run_id        TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()
    print(f"[db] Initialised at {DB_PATH}")


if __name__ == "__main__":
    init_db()
