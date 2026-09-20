"""SQLite storage: channels, videos, and per-snapshot video_stats rows."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
    channel_id   TEXT PRIMARY KEY,
    handle       TEXT NOT NULL,
    title        TEXT NOT NULL,
    subscribers  INTEGER NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
    video_id         TEXT PRIMARY KEY,
    channel_id       TEXT NOT NULL REFERENCES channels(channel_id),
    title            TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    hashtags         TEXT NOT NULL DEFAULT '',
    published_at     TEXT NOT NULL,
    upload_hour      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS video_stats (
    video_id    TEXT NOT NULL REFERENCES videos(video_id),
    snapshot_run INTEGER NOT NULL,
    collected_at TEXT NOT NULL,
    views       INTEGER NOT NULL,
    likes       INTEGER NOT NULL,
    comments    INTEGER NOT NULL,
    PRIMARY KEY (video_id, snapshot_run)
);

CREATE INDEX IF NOT EXISTS idx_stats_video ON video_stats (video_id);
CREATE INDEX IF NOT EXISTS idx_videos_channel ON videos (channel_id);
"""


def save_result(result, db_path: str | Path = "shorts.db") -> None:
    """Persist an IngestResult (from src.ingest) to SQLite."""
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        now = datetime.now().isoformat(timespec="seconds")
        for ch in result.channels:
            conn.execute(
                "INSERT OR REPLACE INTO channels VALUES (?, ?, ?, ?, ?)",
                (ch.channel_id, ch.handle, ch.title, ch.subscribers, now),
            )
            for v in ch.videos:
                published = (datetime.now()
                             - timedelta(days=float(v["published_at_days_ago"]))
                             ).replace(microsecond=0).isoformat()
                conn.execute(
                    "INSERT OR REPLACE INTO videos VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (v["video_id"], ch.channel_id, v["title"], v["duration_seconds"],
                     v.get("hashtags", ""), published, int(v.get("upload_hour", 0))),
                )
                for snap in v.get("snapshots", []):
                    conn.execute(
                        "INSERT OR REPLACE INTO video_stats VALUES (?, ?, ?, ?, ?, ?)",
                        (v["video_id"], int(snap["run"]), now,
                         snap["views"], snap["likes"], snap["comments"]),
                    )
        conn.commit()
    finally:
        conn.close()


def load_frames(db_path: str | Path = "shorts.db"):
    """Load joined frames for analysis."""
    import pandas as pd

    conn = sqlite3.connect(db_path)
    try:
        channels = pd.read_sql_query("SELECT * FROM channels", conn)
        videos = pd.read_sql_query(
            "SELECT v.*, c.handle, c.title AS channel_title, c.subscribers "
            "FROM videos v JOIN channels c USING (channel_id)", conn)
        stats = pd.read_sql_query("SELECT * FROM video_stats", conn)
    finally:
        conn.close()
    return channels, videos, stats
