"""Ingest YouTube Shorts metrics via the Data API (or a seeded simulator).

Usage:
    python -m src.ingest --channels @handle1 @handle2
    python -m src.ingest --channels @handle1 --snapshots 3   # collect 3 runs

Set YOUTUBE_API_KEY to hit the live API; without it a realistic simulator
generates the same schema so the whole pipeline is demoable offline.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import time
from dataclasses import dataclass, field

import numpy as np
import requests

API_BASE = "https://www.googleapis.com/youtube/v3"
SIM_SEED_BASIS = "yt-shorts-sim-v1"


@dataclass
class ChannelData:
    handle: str
    channel_id: str
    title: str
    subscribers: int
    videos: list[dict] = field(default_factory=list)


@dataclass
class IngestResult:
    source: str  # "api" | "simulator"
    channels: list[ChannelData]
    collected_at: float = field(default_factory=time.time)


# --------------------------------------------------------------------------
# Simulator: deterministic, realistic, offline
# --------------------------------------------------------------------------

_TOPIC_LIBRARY = [
    ("science experiment", ["#science", "#experiment"], 1.6),
    ("day in my life", ["#vlog", "#daily"], 0.9),
    ("coding tutorial", ["#coding", "#python"], 1.1),
    ("gaming highlights", ["#gaming", "#clips"], 1.3),
    ("cooking hack", ["#food", "#recipe"], 1.4),
    ("workout routine", ["#fitness", "#gym"], 1.2),
    ("money tip", ["#finance", "#money"], 1.7),
    ("travel moment", ["#travel", "#nature"], 1.0),
]

HOURS = list(range(24))


def _seed(*parts: str) -> np.random.Generator:
    digest = hashlib.sha256("|".join((SIM_SEED_BASIS, *parts)).encode()).hexdigest()
    return np.random.default_rng(int(digest[:16], 16))


def _simulated_channel(handle: str) -> ChannelData:
    rng = _seed(handle)
    subs = int(rng.gamma(2.0, 4e5) + 2_000)
    channel_id = "UC" + hashlib.sha1(handle.encode()).hexdigest()[:22]
    title = handle.lstrip("@").replace("-", " ").title()

    n_videos = int(rng.integers(12, 40))
    videos = []
    for i in range(n_videos):
        topic, tags, virality = _TOPIC_LIBRARY[int(rng.integers(0, len(_TOPIC_LIBRARY)))]
        age_days = float(rng.uniform(1, 180))
        duration = float(rng.integers(8, 58))
        hour = int(rng.choice(HOURS, p=_upload_hour_weights()))
        base_views = subs * rng.uniform(0.04, 0.35) * virality * _hour_factor(hour)
        views = int(max(500, base_views * (1 + rng.normal(0, 0.25))))
        like_rate = float(np.clip(rng.normal(0.075, 0.02), 0.01, 0.20))
        comment_rate = float(np.clip(rng.normal(0.008, 0.003), 0.0005, 0.03))
        videos.append({
            "video_id": hashlib.sha1(f"{handle}:{i}".encode()).hexdigest()[:11],
            "title": f"{topic.title()} #{i + 1}",
            "duration_seconds": duration,
            "hashtags": " ".join(tags),
            "published_at_days_ago": age_days,
            "upload_hour": hour,
            "views": views,
            "likes": int(views * like_rate),
            "comments": int(views * comment_rate),
        })
    return ChannelData(handle, channel_id, title, subs, videos)


def _upload_hour_weights() -> np.ndarray:
    weights = np.array([0.4, 0.3, 0.3, 0.4, 0.6, 0.9, 1.3, 1.8, 2.0, 1.9, 1.8, 1.9,
                        2.1, 2.0, 1.9, 2.0, 2.4, 2.6, 2.5, 2.2, 1.8, 1.2, 0.8, 0.5])
    return weights / weights.sum()


def _hour_factor(hour: int) -> float:
    return 0.55 + 0.9 * _upload_hour_weights()[hour] / _upload_hour_weights().max()


# --------------------------------------------------------------------------
# Live API client
# --------------------------------------------------------------------------

class ShortsClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("YOUTUBE_API_KEY")
        self.session = requests.Session()

    def _get(self, path: str, **params: str) -> dict:
        params["key"] = self.api_key
        resp = self.session.get(f"{API_BASE}/{path}", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def collect(self, handle: str, max_shorts: int = 40) -> ChannelData:
        """Collect a channel's Shorts metadata + statistics."""
        search = self._get("search", part="snippet", q=handle, type="channel", maxResults="1")
        items = search.get("items", [])
        if not items:
            raise ValueError(f"channel not found: {handle}")
        channel_id = items[0]["snippet"]["channelId"]

        channel = self._get("channels", part="snippet,statistics", id=channel_id)
        ch = channel["items"][0]
        data = ChannelData(handle, channel_id, ch["snippet"]["title"],
                           int(ch["statistics"].get("subscriberCount", 0)))

        uploads = self._get("search", part="snippet", channelId=channel_id,
                            type="video", order="date", maxResults=str(min(max_shorts, 50)))
        video_ids = [it["id"]["videoId"] for it in uploads.get("items", [])]
        if not video_ids:
            return data

        details = self._get("videos", part="contentDetails,statistics,snippet",
                            id=",".join(video_ids[:50]))
        for v in details.get("items", []):
            duration = _parse_duration(v["contentDetails"]["duration"])
            if duration > 60:  # only Shorts
                continue
            stats = v.get("statistics", {})
            data.videos.append({
                "video_id": v["id"],
                "title": v["snippet"]["title"],
                "duration_seconds": duration,
                "hashtags": " ".join(w for w in v["snippet"].get("description", "").split()
                                     if w.startswith("#") and len(w) < 30),
                "published_at_days_ago": _days_since(v["snippet"]["publishedAt"]),
                "upload_hour": int(v["snippet"]["publishedAt"][11:13]),
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
            })
        return data


def _parse_duration(iso: str) -> float:
    import re

    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0.0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def _days_since(rfc3339: str) -> float:
    from datetime import datetime, timezone

    dt = datetime.fromisoformat(rfc3339.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400


def collect_channels(handles: list[str], snapshots: int = 1) -> IngestResult:
    """Collect every handle; use the live API if a key exists, else simulate.

    Each video carries a `snapshots` list (one stats row per collection run)
    so velocity/growth analysis has time series to work with. The simulator
    applies organic growth per run; the live API yields a single snapshot.
    """
    client = ShortsClient()
    source = "api" if client.api_key else "simulator"
    channels: list[ChannelData] = []
    for handle in handles:
        base = (client.collect(handle) if source == "api" else _simulated_channel(handle))
        runs = snapshots if source == "simulator" else 1
        for v in base.videos:
            v["snapshots"] = []
            for run in range(runs):
                factor = (1 + 0.04 * run) if source == "simulator" else 1.0
                v["snapshots"].append({
                    "run": run,
                    "views": int(v["views"] * factor),
                    "likes": int(v["likes"] * factor),
                    "comments": int(v["comments"] * factor),
                })
        channels.append(base)
    return IngestResult(source=source, channels=channels)


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect YouTube Shorts metrics")
    parser.add_argument("--channels", nargs="+", required=True)
    parser.add_argument("--snapshots", type=int, default=1)
    parser.add_argument("--db", default="shorts.db")
    args = parser.parse_args()

    from .store import save_result

    result = collect_channels(args.channels, args.snapshots)
    save_result(result, args.db)
    print(f"Source   : {result.source}")
    for ch in result.channels:
        print(f"Channel  : {ch.title} ({ch.subscribers:,} subs, {len(ch.videos)} video snapshots)")
    print(f"Database : {args.db}")


if __name__ == "__main__":
    main()
