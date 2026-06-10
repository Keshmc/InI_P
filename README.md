# News Analyzer

Streamlit-based financial news analysis application with Google Cloud Firestore persistence, sentiment analysis, publisher monitoring, and long-term ticker tracking.

**Live deployment:** https://news-analyzer-cc7trbhikq-ew.a.run.app/ (Cloud Run, `europe-west1`)

## What The App Does

- searches recent news by keyword
- analyzes sentiment and named entities for each article
- stores processed articles in Google Cloud Firestore (Datastore mode)
- explores the saved article library with detailed filters
- summarizes sentiment by publisher
- tracks configured long-term tickers over time via Cloud Scheduler
- exports page results as CSV (ZIP), JSON, or Excel

## Main Pages

### News Search
- search by keyword via the **Analyze coverage** button
- analyze recent coverage for a selected time window (1h–7d)
- review sentiment score, distribution chart, trend chart, top entities, and full results table
- new articles are saved automatically before the results view loads
- export the current analysis

### Article Library
The page uses three tabs at the top:
- **Overview** — high-level metrics, sentiment overview, top trends, entities, publishers, article table (auto-loads on first visit)
- **Search** — form with company/sector/sentiment/date filters; **Run search** executes the filtered Datastore query
- **Long-Term Ticker** — ticker dropdown + **Run search** button for per-ticker deep-dive with sentiment-over-time chart, trend and entity breakdown, and article table
- export any tab as CSV, JSON, or Excel

### Publisher Sentiment
- auto-loads on first visit and aggregates how publishers tend to write across the saved article collection
- publisher activity rankings, sentiment breakdown, most positive / most negative publishers
- export summary tables

### Long-Term Trends
- collector status pill (Live / Idle / Degraded / Stopped) derived from the most recent Firestore `ingested_at` plus in-process scheduler state
- **Collect now** button to trigger one collection cycle synchronously (works both locally and as a manual override in production)
- configured tickers table with per-ticker article counts and average sentiment
- cumulative article growth chart over time
- daily article count breakdown by ticker
- recent articles table
- export monitoring data

More detail in `docs/ui-pages.md`.

## Project Structure

```text
.gitignore                        # Excludes secrets/ from git
config.yaml                       # Runtime configuration
Dockerfile                        # Python 3.12 container for Cloud Run
requirements.txt                  # Python dependencies
deploy-to-gcp.ps1                 # Full GCP deployment script (PowerShell)

secrets/                          # Local credentials — never committed
  *.json                          # Service account key (local dev only)

src/news_analyzer/
  app.py                          # Main Streamlit entry point
  run_trends_job.py               # Cloud Run Job entry point (one-shot ingestion)
  model/                          # Business logic and data persistence
    model.py                      # NewsAnalysisPipeline orchestration
    analysis/                     # Sentiment and entity extraction
    rss_feed/                     # Google News sourcing and full-text extraction
    datastore/                    # Firestore persistence and query
    insights/                     # Data aggregation for UI
    publisher_sentiment/          # Publisher-level analysis
    trends/                       # Long-term ticker scheduler
  presenter/                      # View-to-model bridge (NewsPresenter)
  view/                           # Streamlit UI
    pages/search/                 # News Search page
    pages/datastore/              # Article Library page (Overview / Search / Long-Term Ticker tabs)
    pages/publishers/             # Publisher Sentiment page
    pages/long_term/              # Long-Term Trends page
    pages/general/                # Shared topbar navigation + global styles
    utils/                        # Datetime formatting, export tools, chart helpers

docs/
  ui-pages.md                     # Detailed UI page descriptions
  long-term-scheduler.md          # Scheduler and Cloud Run Job documentation
```

## Running The App Locally

1. Create or activate a Python environment and install dependencies:

```bash
pip install -r requirements.txt
```

2. Provide service account credentials (see [Credentials](#credentials)).

3. Start Streamlit:

```bash
streamlit run src/news_analyzer/app.py
```

## Credentials

### Local Development

Recommended: use Application Default Credentials so no key file needs to live on disk.

```bash
gcloud auth application-default login
```

Alternatively, drop a downloaded service account JSON into one of the auto-discovered locations:

- `./secrets/` (project-local, gitignored)
- `~/gcp-secrets/` (user-global, outside the repo)

The app resolves credentials in this order:

1. `GOOGLE_APPLICATION_CREDENTIALS` environment variable
2. `datastore.credentials_path` in `config.yaml` (omitted by default)
3. Auto-discovery: most recent `.json` file in `./secrets/`, then `~/gcp-secrets/`
4. `gcloud` ADC credentials

Both `secrets/` (via `.gitignore` and `.dockerignore`) and `~/gcp-secrets/` are outside the repo and the Docker build context, so downloaded keys never reach git or production images.

### Cloud Run (Production)

Cloud Run containers receive an attached service account identity automatically (Application Default Credentials). No JSON key file is needed or should be shipped to production.

## Configuration

The application reads runtime configuration from `config.yaml`.

| Section | Key fields |
|---------|-----------|
| `rss` | `language`, `country`, `period`, `max_results` |
| `extractor` | `request_timeout_seconds`, `max_chars` |
| `analyzer` | `max_chars`, `fallback_to_mock_on_error` |
| `datastore` | `project_id`, `database_id`, `kind` (credentials auto-discovered, see [Credentials](#credentials)) |
| `long_term_trends` | `enabled`, `interval_minutes`, `period`, `max_results`, `tickers` |

Current long-term trends settings:

```yaml
long_term_trends:
  enabled: true
  interval_minutes: 1440      # 24 hours (used locally only; Cloud = Cloud Scheduler)
  run_on_startup: true
  period: 1d                  # Search window per collection run
  max_results: 300            # Max articles fetched per ticker per run
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

Detailed scheduler behavior is documented in `docs/long-term-scheduler.md`.

## Deploy To Google Cloud

The PowerShell script `deploy-to-gcp.ps1` automates the full deployment in one step:

```powershell
.\deploy-to-gcp.ps1
```

It performs:
1. Enables required GCP APIs (Cloud Run, Cloud Build, Container Registry, Cloud Scheduler)
2. Builds and pushes the Docker image via Cloud Build
3. Deploys the Streamlit web app to Cloud Run (`NEWS_ANALYZER_LONG_TERM_TRENDS_ENABLED=false`)
4. Deploys a Cloud Run Job for one-shot trend ingestion (`run_trends_job.py`)
5. Creates or updates a Cloud Scheduler trigger (daily at 06:00 UTC)

### Architecture in Production

```
Browser
  └─► Cloud Run (web app, scheduler disabled)
        └─► Firestore

Cloud Scheduler (daily 06:00 UTC)
  └─► Cloud Run Job (run_trends_job.py, one-shot)
        └─► Firestore
```

The web app and the ingestion job use the same Docker image but different entry points.

### Manual Deployment Commands

Prepare the project:

```bash
gcloud config set project financial-news-analyzer-489418
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  cloudscheduler.googleapis.com language.googleapis.com datastore.googleapis.com
```

Deploy the web app:

```bash
gcloud run deploy news-analyzer \
  --source . \
  --region europe-west1 \
  --allow-unauthenticated \
  --set-env-vars NEWS_ANALYZER_LONG_TERM_TRENDS_ENABLED=false
```

Deploy the ingestion job:

```bash
gcloud run jobs deploy news-analyzer-trends-job \
  --image gcr.io/financial-news-analyzer-489418/news-analyzer \
  --region europe-west1 \
  --command python \
  --args src/news_analyzer/run_trends_job.py
```

Run the job manually:

```bash
gcloud run jobs execute news-analyzer-trends-job --region=europe-west1
```

View logs:

```bash
gcloud run logs read news-analyzer --region=europe-west1 --limit=50
gcloud run jobs logs read news-analyzer-trends-job --region=europe-west1 --limit=50
```

## Datastore Query Support

The Article Library search mode supports filtered Firestore queries:

| Filter | Description |
|--------|-------------|
| Company / keyword | One or more comma-separated names |
| Industry sector | Standard sector label (Technology, Energy, …) |
| Sentiment range | Min and max score (−1.0 to +1.0) |
| Publication date range | From/to date filter |
| Result limit | 50 – 10,000 rows |

## Data Limits

| Page / Mode | Scan limit |
|-------------|------------|
| News Search | up to 1,000 provider results per search (Google News RSS practical max is ~100) |
| Article Library (all tabs) | up to 50,000 saved records |
| Publisher Sentiment | up to 50,000 saved records |
| Long-Term Trends | up to 10,000 saved records |

## Export

Each main page contains an export section supporting:

| Format | Notes |
|--------|-------|
| CSV (ZIP) | Each table exported as a separate CSV file inside one ZIP archive |
| JSON | Full page payload as structured JSON |
| Excel | Multi-sheet workbook (requires `pandas` + `openpyxl`) |

## Timestamps

All timestamps in the UI are displayed in `Europe/Zurich`.

Timestamp field priority (most to least preferred):

1. `published_at`
2. `published_date`
3. `analysis_timestamp`
4. `ingested_at`

## Security Notes

- `secrets/` is excluded from git (`.gitignore`) and Docker builds (`.dockerignore`)
- Never commit service account JSON files
- Cloud Run uses Application Default Credentials — no key file needed in production
- Rotate service account keys immediately if accidentally exposed

## Additional Documentation

- `docs/ui-pages.md` — detailed page descriptions
- `docs/long-term-scheduler.md` — scheduler, Cloud Run Job, and Cloud Scheduler setup
