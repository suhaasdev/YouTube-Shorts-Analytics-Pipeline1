"""Tests: simulator realism, storage round-trip, analysis metrics."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ingest import collect_channels  # noqa: E402
from src.store import save_result  # noqa: E402


@pytest.fixture(scope="module")
def db(tmp_path_factory) -> Path:
    result = collect_channels(["@demo-channel"], snapshots=3)
    db_path = tmp_path_factory.mktemp("data") / "shorts.db"
    save_result(result, db_path)
    return db_path


def test_simulator_deterministic():
    a = collect_channels(["@same-handle"])
    b = collect_channels(["@same-handle"])
    assert a.channels[0].channel_id == b.channels[0].channel_id
    assert a.channels[0].videos[0]["views"] == b.channels[0].videos[0]["views"]


def test_simulator_realistic_ranges():
    ch = collect_channels(["@demo-channel"]).channels[0]
    assert len(ch.videos) >= 12
    for v in ch.videos:
        assert v["duration_seconds"] <= 60  # Shorts only
        assert v["likes"] < v["views"] < 10_000_000
        assert 0 < v["comments"] < v["likes"] * 1.5
        assert 0 <= v["upload_hour"] <= 23


def test_store_round_trip(db):
    from src.store import load_frames

    channels, videos, stats = load_frames(db)
    assert len(channels) == 1
    assert len(videos) >= 12
    assert set(stats["snapshot_run"]) == {0, 1, 2}


def test_analysis_metrics(db):
    from src.analyze import build_video_summary, duration_analysis, hashtag_performance, timing_analysis
    from src.store import load_frames

    _, videos, stats = load_frames(db)
    summary = build_video_summary(videos, stats)
    assert (summary["engagement_rate"] > 0).all()
    assert (summary["engagement_rate"] < 1).all()
    assert (summary["views"] > 0).all()

    tags = hashtag_performance(summary)
    assert len(tags) > 0
    assert (tags["videos"] >= 2).all()

    by_hour = timing_analysis(summary)
    assert set(by_hour["upload_hour"]).issubset(set(range(24)))

    by_dur = duration_analysis(summary)
    assert len(by_dur) >= 2


def test_growth_between_snapshots(db):
    from src.analyze import velocity
    from src.store import load_frames

    _, _, stats = load_frames(db)
    growth = velocity(stats)
    assert len(growth) > 0
    assert (growth["views_per_day_gain"] > 0).all()  # simulator only grows
