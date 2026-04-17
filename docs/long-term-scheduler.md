# Long-Term Trend Collection

This document explains how automatic long-term ticker ingestion works, both locally and in Google Cloud.

## Purpose

The long-term collection pipeline performs recurring searches for a configured set of tickers and stores new articles in Firestore. This enables:

- repeated collection over time without manual intervention
- long-term monitoring across the UI (growth charts, per-ticker sentiment)
- historical article accumulation for trend analysis

## Architecture

### Production (Google Cloud)

In production the web app and the ingestion job are decoupled:

```
Cloud Scheduler (daily 06:00 UTC)
  └─► Cloud Run Job  (run_trends_job.py — one-shot, exits when done)
        └─► Firestore (stores new articles)

Browser
  └─► Cloud Run  (Streamlit web app, scheduler disabled)
        └─► Firestore (reads stored articles)
```

The web app runs with `NEWS_ANALYZER_LONG_TERM_TRENDS_ENABLED=false`. The Cloud Run Job uses the same Docker image but a different entry point (`run_trends_job.py`).

### Local Development

Locally the app can run the scheduler as a background thread within the Streamlit process. This is controlled by `long_term_trends.enabled` in `config.yaml` and is useful for development but unreliable on Cloud Run (scale-to-zero kills the thread).

## Configuration

All settings live in `config.yaml` under `long_term_trends`:

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | bool | Enables or disables the in-process background scheduler (local only) |
| `interval_minutes` | int | Run interval in minutes for the local scheduler (default: 1440 = 24h) |
| `run_on_startup` | bool | Run one cycle immediately when the local app process starts |
| `period` | string | News search window per collection run (e.g. `1d`, `7d`) |
| `max_results` | int | Max articles fetched per ticker per run (default: 300) |
| `extract_full_text` | bool | Download and parse full article text before analysis |
| `include_entities` | bool | Run named entity extraction per article |
| `tickers` | list | Search terms to track (keywords, company names, symbols) |

Current defaults:

```yaml
long_term_trends:
  enabled: true
  interval_minutes: 1440
  run_on_startup: true
  period: 1d
  max_results: 300
  extract_full_text: true
  include_entities: true
  tickers:
    - Trump
    - Iran
    - Oil
    - Gold
    - NVDA
    - Tesla
    - MSFT
    - Apple
    - USA
```

## Cloud Run Job

The entry point for scheduled collection is `src/news_analyzer/run_trends_job.py`.

What it does:

1. Loads `config.yaml` via the same `build_presenter()` used by the web app
2. Instantiates the long-term trend scheduler
3. Calls `scheduler.run_once()` — one full collection cycle, synchronous
4. Logs the outcome (articles fetched, saved, errors)
5. Exits with code `1` if an error occurred (Cloud Run Job marks the execution as failed)

The job is deployed separately from the web app:

```bash
gcloud run jobs deploy news-analyzer-trends-job \
  --image gcr.io/financial-news-analyzer-489418/news-analyzer \
  --region europe-west1 \
  --memory 2Gi \
  --cpu 2 \
  --task-timeout 3600 \
  --command python \
  --args src/news_analyzer/run_trends_job.py
```

Run manually at any time:

```bash
gcloud run jobs execute news-analyzer-trends-job --region=europe-west1
```

## Cloud Scheduler

Cloud Scheduler triggers the Cloud Run Job via an authenticated HTTP request.

The deploy script (`deploy-to-gcp.ps1`) creates the scheduler automatically. To create it manually:

```bash
PROJECT_NUMBER=$(gcloud projects describe financial-news-analyzer-489418 --format="value(projectNumber)")
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# Grant the scheduler permission to trigger the job
gcloud run jobs add-iam-policy-binding news-analyzer-trends-job \
  --region europe-west1 \
  --member "serviceAccount:${COMPUTE_SA}" \
  --role roles/run.invoker

# Create the daily trigger
gcloud scheduler jobs create http news-analyzer-trends-daily \
  --location europe-west1 \
  --schedule "0 6 * * *" \
  --uri "https://europe-west1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/financial-news-analyzer-489418/jobs/news-analyzer-trends-job:run" \
  --message-body "{}" \
  --oidc-service-account-email "${COMPUTE_SA}"
```

## One Collection Cycle

Each run (whether local or via Cloud Run Job) follows the same steps for every configured ticker:

1. Search Google News for the ticker using the configured `period` and `max_results`
2. Check which articles are already stored in Firestore (deduplication)
3. Extract full text for new articles (if `extract_full_text: true`)
4. Run sentiment and entity analysis on new articles
5. Save new articles to Firestore
6. Return totals: fetched / existing / new / saved / loaded

## How The Dashboard Identifies Articles

The Long-Term Trends page identifies records belonging to a ticker by checking these saved fields (in order):

- `query`
- `topic`
- `company_keyword`
- `symbol`
- legacy values inside `raw_article_json`

Matching is case-insensitive.

For chart timestamps, the page uses this fallback chain:

1. `ingested_at`
2. `analysis_timestamp`
3. `published_at`
4. `published_date`

## Sidebar Status

The sidebar shows different text depending on the environment:

| Situation | Sidebar text |
|-----------|-------------|
| In-process scheduler running (local) | `Collector: running (in-process)` + schedule + last run |
| In-process scheduler disabled (production) | `Collector: daily (Cloud Scheduler)` |

The "Last Data Collection" metric on the Long-Term Trends page is derived from the most recent `ingested_at` timestamp across all stored records — not from in-memory scheduler state. This means it correctly reflects the last Cloud Run Job execution even when the web app has no scheduler running.

## Provider Notes

The underlying `gnews` library has known behavior at high result counts:

- searches above `100` results may not apply the time-range filter as strictly as smaller searches
- for strict period handling, consider reducing `max_results` toward `100`

The application suppresses noisy provider warnings in output but the limitation still applies.
