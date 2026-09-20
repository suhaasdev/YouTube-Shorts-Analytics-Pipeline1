"""Analyze Shorts performance: engagement, reach, timing, duration, hashtags.

Usage:
    python -m src.analyze [--db shorts.db]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .store import load_frames

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
EXPORTS = ROOT / "exports"


def latest_stats(stats: pd.DataFrame) -> pd.DataFrame:
    """Latest snapshot per video."""
    return (stats.sort_values("snapshot_run")
            .groupby("video_id", as_index=False).last())


def build_video_summary(videos: pd.DataFrame, stats: pd.DataFrame) -> pd.DataFrame:
    latest = latest_stats(stats)[["video_id", "views", "likes", "comments"]]
    df = videos.merge(latest, on="video_id", how="inner")
    published = pd.to_datetime(df["published_at"], errors="coerce")
    df["published_at_days_ago"] = ((pd.Timestamp.now() - published)
                                   .dt.total_seconds() / 86400).clip(lower=0.5).round(1)
    df["engagement_rate"] = ((df["likes"] + df["comments"]) / df["views"].clip(lower=1)).round(4)
    df["like_ratio"] = (df["likes"] / df["views"].clip(lower=1)).round(4)
    df["comment_ratio"] = (df["comments"] / df["views"].clip(lower=1)).round(4)
    df["views_per_day"] = (df["views"] / df["published_at_days_ago"]).round(1)
    df["duration_bucket"] = pd.cut(df["duration_seconds"], bins=[0, 15, 25, 35, 50, 60],
                                   labels=["<15s", "15-25s", "25-35s", "35-50s", "50-60s"])
    return df


def velocity(stats: pd.DataFrame) -> pd.DataFrame:
    """View growth between the first and last snapshot (views/day)."""
    if stats["snapshot_run"].nunique() < 2:
        return pd.DataFrame()
    piv = stats.pivot_table(index="video_id", columns="snapshot_run", values="views")
    first, last = piv.columns.min(), piv.columns.max()
    if first == last:
        return pd.DataFrame()
    days_between = 1.0 * (last - first)  # snapshots are daily-ish
    growth = ((piv[last] - piv[first]) / days_between).dropna()
    return growth.sort_values(ascending=False).round(1).to_frame("views_per_day_gain")


def hashtag_performance(summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, video in summary.iterrows():
        for tag in str(video["hashtags"]).split():
            if tag.startswith("#"):
                rows.append({"hashtag": tag, "views": video["views"],
                             "engagement_rate": video["engagement_rate"]})
    if not rows:
        return pd.DataFrame()
    tags = pd.DataFrame(rows)
    return (tags.groupby("hashtag")
            .agg(videos=("hashtag", "size"), median_views=("views", "median"),
                 engagement_rate=("engagement_rate", "mean"))
            .query("videos >= 2")
            .sort_values("median_views", ascending=False)
            .round(3).reset_index())


def timing_analysis(summary: pd.DataFrame) -> pd.DataFrame:
    by_hour = (summary.groupby("upload_hour")
               .agg(videos=("video_id", "size"), median_views=("views", "median"))
               .round(0).reset_index())
    return by_hour


def duration_analysis(summary: pd.DataFrame) -> pd.DataFrame:
    return (summary.groupby("duration_bucket", observed=True)
            .agg(videos=("video_id", "size"), median_views=("views", "median"),
                 engagement_rate=("engagement_rate", "mean"))
            .round(3).reset_index())


def make_charts(summary: pd.DataFrame, by_hour: pd.DataFrame) -> None:
    REPORTS.mkdir(exist_ok=True)

    fig, ax = plt.subplots(figsize=(9, 5))
    sc = ax.scatter(summary["views"], summary["engagement_rate"] * 100,
                    c=summary["duration_seconds"], cmap="viridis", s=42, alpha=0.8)
    ax.set_xscale("log")
    ax.set(xlabel="Views (log)", ylabel="Engagement rate %",
           title="Views vs Engagement (color = duration)")
    fig.colorbar(sc, label="Duration (s)")
    fig.tight_layout()
    fig.savefig(REPORTS / "views_vs_engagement.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.bar(by_hour["upload_hour"], by_hour["median_views"], color="#ff5252")
    ax.set(xlabel="Upload hour (local)", ylabel="Median views", title="Median Views by Upload Hour")
    ax.set_xticks(range(24))
    fig.tight_layout()
    fig.savefig(REPORTS / "views_by_hour.png", dpi=150)
    plt.close(fig)


def write_insights(summary: pd.DataFrame, tags: pd.DataFrame,
                   by_hour: pd.DataFrame, by_duration: pd.DataFrame) -> Path:
    lines = ["# YouTube Shorts — Performance Insights\n"]

    top = summary.nlargest(5, "engagement_rate")
    lines.append("## Top performers (engagement rate)\n")
    for i, (_, v) in enumerate(top.iterrows(), 1):
        lines.append(f"{i}. **{v['title']}** — {v['engagement_rate']:.1%} engagement, "
                     f"{v['views']:,} views, {v['duration_seconds']:.0f}s")
    lines.append("")

    if len(by_duration):
        best_dur = by_duration.loc[by_duration["median_views"].idxmax()]
        lines.append(f"## Duration sweet spot\n\n"
                     f"Shorts of **{best_dur['duration_bucket']}** average "
                     f"{best_dur['median_views']:,.0f} median views "
                     f"({best_dur['engagement_rate']:.1%} engagement).\n")

    if len(by_hour) and by_hour["videos"].max() >= 2:
        best = by_hour.loc[by_hour["median_views"].idxmax()]
        worst = by_hour.loc[by_hour["median_views"].idxmin()]
        if worst["median_views"] and worst["median_views"] > 0:
            lines.append(f"## Posting time\n\nUploads around **{int(best['upload_hour'])}:00** "
                         f"earn {best['median_views'] / max(worst['median_views'], 1):.1f}x the "
                         f"median views of {int(worst['upload_hour'])}:00 uploads.\n")

    if len(tags):
        lines.append("## Hashtag performance (>= 2 videos)\n")
        lines.append("| Hashtag | Videos | Median views | Engagement |")
        lines.append("|---|---|---|---|")
        for _, t in tags.head(8).iterrows():
            lines.append(f"| {t['hashtag']} | {int(t['videos'])} | "
                         f"{t['median_views']:,.0f} | {t['engagement_rate']:.1%} |")
        lines.append("")

    lines.append(f"## Portfolio stats\n")
    lines.append(f"- Videos analyzed: {len(summary)}")
    lines.append(f"- Median views: {summary['views'].median():,.0f}")
    lines.append(f"- Median engagement rate: {summary['engagement_rate'].median():.1%}")
    lines.append(f"- Best upload window: {int(by_hour.loc[by_hour['median_views'].idxmax(), 'upload_hour']) if len(by_hour) else 'n/a'}:00")

    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / "shorts_insights.md"
    out.write_text("\n".join(lines))
    return out


def export_frames(summary: pd.DataFrame, tags: pd.DataFrame, by_hour: pd.DataFrame) -> None:
    EXPORTS.mkdir(exist_ok=True)
    summary.to_csv(EXPORTS / "video_summary.csv", index=False)
    by_hour.to_csv(EXPORTS / "daily_performance.csv", index=False)
    if len(tags):
        tags.to_csv(EXPORTS / "hashtag_performance.csv", index=False)


def run(db_path: Path = ROOT / "shorts.db") -> None:
    channels, videos, stats = load_frames(db_path)
    if videos.empty:
        print("No videos in the database — run `python -m src.ingest` first.")
        return

    summary = build_video_summary(videos, stats)
    tags = hashtag_performance(summary)
    by_hour = timing_analysis(summary)
    by_duration = duration_analysis(summary)

    make_charts(summary, by_hour)
    export_frames(summary, tags, by_hour)
    report = write_insights(summary, tags, by_hour, by_duration)

    print(f"Videos: {len(summary)} across {len(channels)} channel(s)")
    print(f"Median views: {summary['views'].median():,.0f} · "
          f"median engagement: {summary['engagement_rate'].median():.1%}")
    print(f"Insights -> {report}")
    print(f"Exports  -> {EXPORTS}/(video_summary|daily_performance|hashtag_performance).csv")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=ROOT / "shorts.db")
    args = parser.parse_args()
    run(args.db)
