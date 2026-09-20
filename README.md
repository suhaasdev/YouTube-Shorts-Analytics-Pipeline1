# 🎬 YouTube Shorts Analytics Pipeline

An end-to-end pipeline that collects YouTube Shorts performance metrics via the **YouTube Data API**, stores them in **SQLite**, analyzes engagement / reach / trends with **Pandas**, exports BI-ready aggregates, and renders a **Power BI** dashboard guide.

![YouTube Data API](https://img.shields.io/badge/YouTube-Data%20API-red)
![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![Pandas](https://img.shields.io/badge/Pandas-Analysis-150458)
![Power BI](https://img.shields.io/badge/Power%20BI-Dashboard-yellow)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

## ✨ Pipeline stages

```
ingest ──▶ store ──▶ analyze ──▶ export ──▶ visualize (Power BI)
```

| Stage | Module | What it does |
|---|---|---|
| Ingest | `src/ingest.py` | `shorts_client.collect(channel_handle)` → video metadata + statistics via `search.list`, `videos.list`, `channels.list`. **Falls back to a realistic seeded simulator when no API key is set** |
| Store | `src/store.py` | Normalizes into SQLite: `channels`, `videos`, `video_stats` (snapshot rows → track growth over time) |
| Analyze | `src/analyze.py` | Engagement rate, view velocity, like/comment ratios, trending-hashtag and duration-bucket performance, upload-pattern insights |
| Export | `src/analyze.py` | `reports/shorts_insights.md` + `exports/*.csv` for Power BI |
| Visualize | `docs/powerbi_guide.md` | Page-by-page dashboard build guide |

## 🚀 Quickstart

```bash
pip install -r requirements.txt
export YOUTUBE_API_KEY=...   # optional — omit to use the built-in simulator

python -m src.ingest --channels @MrBeast @Veritasium --snapshots 3
python -m src.analyze
```

Outputs:

```
reports/shorts_insights.md     # written insights
exports/daily_performance.csv  # Power BI fact table
exports/video_summary.csv      # per-video aggregates
exports/hashtag_performance.csv
```

### Example insights produced

```
TOP PERFORMERS (by engagement rate)
  1. How Deep Is the Ocean, Really? — 11.2% engagement, 4.2M views
POSTING TIME
  Uploads at 16-19h local get 2.3x the median views of 0-6h uploads.
DURATION SWEET SPOT
  Shorts of 35-50s average 2.1x the views of <15s shorts.
```

## 🗃️ Data model

| Table | Grain |
|---|---|
| `channels` | One row per channel (handle, subscriber count, video count) |
| `videos` | One row per Short (title, duration, hashtags, published_at) |
| `video_stats` | One snapshot row per (video, collection run): views, likes, comments → velocity & growth analysis |

## 🧪 Tests

```bash
pytest -q
```

## 📄 License

MIT — see [LICENSE](LICENSE).
