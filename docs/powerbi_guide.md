# Power BI Dashboard Guide

Build the Shorts analytics dashboard from the CSV exports in `exports/`.

## 1. Get data

Load `video_summary.csv` (fact), `daily_performance.csv`, `hashtag_performance.csv`.
Set `upload_hour` as Whole Number and `published_at_days_ago` as Decimal.

## 2. Page 1 — Performance overview

| Visual | Fields |
|---|---|
| Card ×4 | Sum of `views`, Average of `engagement_rate`, Count of `video_id`, Median of `views` |
| Scatter | X: `views` (log) · Y: `engagement_rate` · Size: `duration_seconds` · Tooltip: `title` |
| Slicer | `channel_title` |

Suggested measure:

```dax
Avg Engagement % = AVERAGE ( video_summary[engagement_rate] ) * 100

Views per Day =
AVERAGEX ( video_summary,
    DIVIDE ( video_summary[views], video_summary[published_at_days_ago] ) )
```

## 3. Page 2 — Timing & duration

| Visual | Fields |
|---|---|
| Column chart | X: `upload_hour` · Y: median `views` |
| Bar chart | Y: `duration_bucket` · X: median `views` |
| Matrix | Rows: `duration_bucket` · Values: `views`, `engagement_rate` |

## 4. Page 3 — Hashtags

| Visual | Fields |
|---|---|
| Treemap | Group: `hashtag` · Values: `median_views` |
| Table | `hashtag`, `videos`, `median_views`, `engagement_rate` |

## 5. Publishing

Publish to the Power BI Service and schedule a daily refresh pointing at the
regenerated CSVs (OneDrive/SharePoint path works well).
