# News Analyzer

Streamlit-based news analysis application with Datastore persistence, sentiment analysis, publisher monitoring, and long-term ticker tracking.

## What The App Does

- searches recent news by keyword or trend
- analyzes sentiment and entities for saved articles
- stores processed articles in Google Cloud Datastore / Firestore Datastore mode
- explores the saved article library with filters
- summarizes sentiment by publisher
- tracks configured long-term tickers over time
- exports page results as `CSV (ZIP)`, `JSON`, or `Excel`

## Main Pages

- `News Search`
  - search by keyword or trending topic
  - analyze recent coverage
  - review sentiment, entities, trend chart, and result table
  - export the current analysis
- `Article Library`
  - `Overview` for the saved collection
  - `Search` for filtered Datastore queries
  - filters include companies, industry sector, sentiment threshold, and date range
  - export overview data or filtered result sets
- `Publisher Sentiment`
  - summarizes how publishers tend to write across saved records
  - includes publisher activity and sentiment rankings
  - export summary tables
- `Long-Term Trends`
  - shows active scheduler tickers
  - shows scheduler status and latest run details
  - visualizes saved long-term article growth over time
  - visualizes daily ticker breakdown
  - export long-term monitoring data

More page details are documented in `docs/ui-pages.md`.

## Project Structure

```text
config.yaml
src/news_analyzer/app.py
src/news_analyzer/model/
src/news_analyzer/presenter/
src/news_analyzer/view/
docs/
```

## Running The App

1. Create or activate a Python environment with the required project dependencies.
2. Ensure Google credentials are available.
3. Start Streamlit:

```bash
streamlit run src/news_analyzer/app.py
```

## Configuration

The application reads its runtime configuration from `config.yaml`.

Important sections:

- `rss`
  - controls language, country, default period, and default provider result size
- `extractor`
  - controls article extraction timeout and max text length
- `datastore`
  - contains project, database, collection kind, and credentials path
- `long_term_trends`
  - configures automatic long-term ingestion

Current long-term scheduler settings:

- `enabled: true`
- `interval_minutes: 360`
- `run_on_startup: true`
- `period: 1d`
- `max_results: 300`
- tickers:
  - `Trump`
  - `Iran`
  - `Oil`
  - `Gold`
  - `NVDA`
  - `Tesla`
  - `MSFT`
  - `Apple`
  - `USA`

Detailed scheduler behavior is documented in `docs/long-term-scheduler.md`.

## Deploy To Google Cloud

The application is best deployed as a public web app on `Cloud Run`.

Why `Cloud Run` fits this project:

- it exposes the Streamlit UI over HTTPS
- it works well with Python containers
- it can use a Google Cloud service account instead of a local JSON key file

Important deployment note:

- the built-in long-term background scheduler is process-local
- on `Cloud Run`, instances can scale down, restart, or scale out
- for reliable scheduled ingestion, prefer a separate `Cloud Run Job` plus `Cloud Scheduler`
- for the web app service itself, disable the in-process scheduler with:
  - `NEWS_ANALYZER_LONG_TERM_TRENDS_ENABLED=false`

### 1. Prepare Google Cloud

Make sure the target project exists and the required services are enabled:

```bash
gcloud config set project financial-news-analyzer-489418
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com datastore.googleapis.com language.googleapis.com
```

Create a dedicated runtime service account for the web app:

```bash
gcloud iam service-accounts create news-analyzer-run \
  --display-name="News Analyzer Cloud Run"
```

Grant the service account access to Datastore mode data:

```bash
gcloud projects add-iam-policy-binding financial-news-analyzer-489418 \
  --member="serviceAccount:news-analyzer-run@financial-news-analyzer-489418.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```

If you want the Cloud NLP analysis to run in Google Cloud instead of falling back locally, also make sure the Natural Language API is enabled for the same project.

### 2. Deploy The Web App

This repository already contains:

- `Dockerfile`
- `.dockerignore`
- `requirements.txt`

Deploy from the repository root:

```bash
gcloud run deploy news-analyzer \
  --source . \
  --region europe-west1 \
  --allow-unauthenticated \
  --service-account news-analyzer-run@financial-news-analyzer-489418.iam.gserviceaccount.com \
  --set-env-vars NEWS_ANALYZER_LONG_TERM_TRENDS_ENABLED=false
```

After a successful deployment, `gcloud` prints the public `https://...run.app` URL.

### 3. Credentials On Cloud Run

Do not ship the local JSON key from `secrets/` into production.

- local development can still use `config.yaml` or `GOOGLE_APPLICATION_CREDENTIALS`
- `Cloud Run` should use its attached service account via Application Default Credentials
- the container build excludes `secrets/`

### 4. Recommended Next Step For Long-Term Collection

If you want the long-term ticker collection to run reliably in Google Cloud:

1. keep the web UI on `Cloud Run`
2. move scheduled ingestion into a `Cloud Run Job` or separate worker service
3. trigger it with `Cloud Scheduler`

## Datastore Query Support

The application supports filtered Datastore queries from the `Article Library` search mode.

Supported filter categories include:

- one or more company names
- industry sector
- minimum sentiment score
- publication date range
- result limit

Current UI/data limits:

- `News Search`: up to `300` requested provider results
- `Article Library`: scans and displays up to the latest `10,000` saved records
- `Publisher Sentiment`: currently summarizes up to `5,000` saved records
- `Long-Term Trends`: scans up to the latest `10,000` saved records for configured tickers

## Export

Each main analysis page contains a compact export section.

Supported formats:

- `CSV (ZIP)`
  - each logical table is exported as its own CSV file inside one ZIP archive
- `JSON`
  - the current page payload is exported as structured JSON
- `Excel`
  - the current page payload is exported as a multi-sheet workbook

Excel export depends on `pandas` and `openpyxl`. If they are unavailable, the UI disables the Excel button and shows a short note.

## Scheduler Notes

The long-term scheduler:

- starts automatically when enabled
- runs once on startup if `run_on_startup` is enabled
- runs again every configured interval
- stores new articles in Datastore
- exposes last run status in the sidebar and on the `Long-Term Trends` page

Important provider note:

- the underlying `gnews` library can behave differently for searches above `100` results
- for very large result sets, provider-side time filtering may become less strict than for smaller searches

## Timestamps

The UI displays timestamps in `Europe/Zurich`.

Where possible, the application prefers:

1. `published_at`
2. `published_date`
3. `analysis_timestamp`
4. `ingested_at`

The `Long-Term Trends` page uses saved Datastore records and builds its charts from ingestion or fallback timestamps if a published timestamp is missing.

## Additional Documentation

- `docs/ui-pages.md`
- `docs/long-term-scheduler.md`
