# UI Pages

This document describes the user-facing pages of the Streamlit application.

## Navigation

A sticky **top navigation bar** contains links to all four main pages plus a collector status pill (Live / Idle / Degraded / Stopped). The pill is data-driven: it reads the most recent `ingested_at` timestamp from Firestore (cached per session) and combines it with the in-process scheduler state. So it reflects what the daily Cloud Run Job last did in production, and the local thread state during development.

---

## News Search

**Purpose**: Fetch and analyze recent news for a keyword, save results to Firestore, and review the analysis.

### Form

| Field | Description |
|-------|-------------|
| Keyword | Free-text search term (e.g. NVIDIA, Apple) |
| Search Window | How far back to search: 1h, 6h, 12h, 1d, 3d, 7d |
| Extract full article text | Downloads and parses the full article body |
| Include entity extraction | Runs named entity recognition per article |

Pressing **Analyze coverage** triggers the full pipeline:
1. Fetch articles from Google News
2. Deduplicate against Firestore (skip already-stored articles)
3. Extract full text (optional)
4. Analyze sentiment and entities
5. Save new articles to Firestore
6. Reload from Firestore into the results view

A progress bar with phase labels tracks the pipeline as it runs.

### Analysis Sections

| Section | Content |
|---------|---------|
| Pipeline metrics | Fetched / Already Saved / New / Analyzed / Saved / Loaded |
| Sentiment Score | Average score and magnitude + visual sentiment meter |
| Sentiment Distribution | Donut chart (Positive / Neutral / Negative) + count table |
| Sentiment Over Time | Line chart of per-article sentiment by publication date |
| Top Extracted Entities | Horizontal bar chart of most frequent named entities |
| Results Table | Filterable by text, sentiment range, and processing status |
| Export | CSV (ZIP), JSON, Excel |

### Important Behavior

- up to `1,000` provider results are requested per search (Google News RSS practical max is ~100)
- articles already in Firestore are not re-analyzed
- all timestamps shown in `Europe/Zurich`

---

## Article Library

**Purpose**: Inspect and query the saved article collection. Loads up to `50,000` records.

The page has three tabs at the top: **Overview**, **Search**, and **Long-Term Ticker**.

### Overview Tab

Loads the most recent `50,000` saved articles automatically on first visit.

| Section | Content |
|---------|---------|
| Overview metrics | Stored articles, unique publishers, unique trends, unique entities |
| Date range | Oldest and newest article timestamps |
| Sentiment Overview | Average score, average magnitude, sentiment meter |
| Positive / Neutral / Negative Share | Donut chart |
| Sentiment Over Time | Line chart of per-article sentiment by publication date |
| Top Trends | Horizontal bar chart + ranked table |
| Top Entities | Horizontal bar chart + ranked table |
| Top Publishers | Horizontal bar chart + ranked table |
| Stored Articles | Full article table |
| Export | CSV (ZIP), JSON, Excel |

### Search Tab

Filtered Firestore queries against the saved collection. All filters live inside a form — the query runs when **Run search** is clicked.

#### Filters

| Filter | Description |
|--------|-------------|
| Company / keyword | One or more comma-separated search terms |
| Industry sector | Standard sector label; "Any" disables this filter |
| Sentiment range | Slider for min and max score (−1.0 to +1.0); full range = no filter |
| Publication range | Date range picker (defaults to the last 30 days) |
| Max results | 50 – 10,000 rows |

**Run search** submits the form and replaces the result area.

#### Result Sections

| Section | Content |
|---------|---------|
| Active Filters | Summary table of the filters applied to this query |
| Search Results | Matching article count, average score, unique publishers/trends, date range |
| Sentiment Overview | Average score, magnitude, sentiment meter |
| Sentiment Distribution | Donut chart |
| Sentiment Over Time | Line chart of per-article sentiment by publication date |
| Top Publishers | Horizontal bar chart + ranked table |
| Top Trends | Horizontal bar chart + ranked table |
| Matching Articles | Full article table |
| Export | CSV (ZIP), JSON, Excel |

### Long-Term Ticker Tab

Per-ticker deep-dive using the same Firestore query mechanism.

| Control | Description |
|---------|-------------|
| Tracked ticker | Dropdown of all configured long-term tickers |
| Run search | Submits the form and loads Firestore data for the selected ticker |

#### Result Sections

| Section | Content |
|---------|---------|
| Overview | Matching articles, unique publishers/trends/entities, average sentiment, date range |
| Sentiment Overview | Average score, magnitude, sentiment meter |
| Sentiment Distribution | Donut chart |
| Sentiment Over Time | Line chart of per-article sentiment by publication date |
| Top Trends | Horizontal bar chart + ranked table |
| Top Entities | Horizontal bar chart + ranked table |
| Top Publishers | Horizontal bar chart + ranked table |
| Articles | Full article table |
| Export | CSV (ZIP), JSON, Excel |

---

## Publisher Sentiment

**Purpose**: Summarize how publishers write across the saved article collection. Scans up to `50,000` records. The page auto-loads on first visit.

| Section | Content |
|---------|---------|
| At a glance | Stored articles, publisher count, positive / neutral / negative publisher counts |
| Average publisher score | Collection-wide sentiment score + meter, plus most active publisher |
| Sentiment Distribution | Donut chart + count table by sentiment label |
| Most Active Publishers | Top 15 ranked by saved articles |
| Most Positive / Negative Publishers | Top 10 each by average sentiment |
| All Publishers | Full publisher table with article count, average score, sentiment label, latest article |
| Export | CSV (ZIP), JSON, Excel |

---

## Long-Term Trends

**Purpose**: Monitor long-term ticker coverage. In production the collector is triggered daily by Cloud Scheduler (not by the web app). Scans up to `10,000` records.

### Header Bar

At the top of the page:

- **Collect now** button — runs one collection cycle synchronously inside the web app. In production this provides a manual override on top of the daily Cloud Run Job; locally it short-circuits the configured run interval.
- Caption summarizing how many tickers are tracked, the run interval, and the scan cap

### Scheduler Section

Inline status pill plus metrics:

| Metric | Description |
|--------|-------------|
| Interval | Run interval (e.g. 1440 min = 24 h) |
| Configured tickers | Number of tickers being monitored |
| Last run · Zurich | Last cycle timestamp in Europe/Zurich |
| Runs on startup | Whether the local scheduler runs one cycle on app startup |
| Lookback period | The `period` setting used by each collection run (e.g. `1d`) |
| Max results per ticker | Upper limit of articles fetched per ticker per run |

A second row shows the latest cycle totals (fetched, existing, new, saved, loaded) when available.

### Coverage Overview

| Metric | Description |
|--------|-------------|
| Configured tickers | Total number of tickers in the config |
| Tickers with data | Tickers that have at least one saved article |
| Saved long-term articles | Total matching saved articles across all tickers |
| Last run · Zurich | Last cycle timestamp |

### Configured Tickers Table

Per-ticker aggregated metrics:

| Column | Description |
|--------|-------------|
| ticker | Configured search term |
| saved_articles | Total articles stored for this ticker |
| avg_sentiment | Average sentiment score across all stored articles |
| latest_ingested_zurich | Most recent ingestion timestamp |
| latest_published_zurich | Most recent article publication timestamp |

### Charts

| Chart | Description |
|-------|-------------|
| Article Growth Over Time | Line chart of the cumulative total of saved long-term articles, day by day |
| Ticker Breakdown Over Time | Stacked bar chart of daily saved articles grouped by configured ticker |

Both charts use `Europe/Zurich` dates on the x-axis and support hover tooltips.

### Recent Articles

Table of the 100 most recently ingested articles across all configured tickers, with ticker, title, source, date, time, sentiment, and processing status.

### Export

CSV (ZIP), JSON, Excel — covers all sections (summary, ticker rows, growth charts, recent articles).

---

## Export Formats

All export sections offer the same three formats:

| Format | Notes |
|--------|-------|
| CSV (ZIP) | Each logical table is a separate CSV file inside one ZIP archive |
| JSON | Full page payload as structured JSON |
| Excel | Multi-sheet workbook; requires `pandas` and `openpyxl` (disabled with a note if unavailable) |
