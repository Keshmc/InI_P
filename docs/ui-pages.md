# UI Pages

This document describes the user-facing pages of the Streamlit application.

## Navigation

The sidebar contains navigation links to all four main pages. In production it also shows `Collector: daily (Cloud Scheduler)` to indicate that long-term ingestion is handled externally. When running locally with the in-process scheduler enabled it shows the schedule and last run time.

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

Pressing **Run analysis** triggers the full pipeline:
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

- up to `300` provider results are requested per search
- articles already in Firestore are not re-analyzed
- all timestamps shown in `Europe/Zurich`

---

## Article Library

**Purpose**: Inspect and query the saved article collection. Loads up to `30,000` records.

The page has three modes selectable via a radio button at the top.

### Overview Mode

Loads the most recent `30,000` saved articles automatically on first visit.

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

### Search Mode

Filtered Firestore queries against the saved collection.

#### Filters

| Filter | Description |
|--------|-------------|
| Company / keyword | One or more comma-separated search terms |
| Industry sector | Standard sector label; "Any" disables this filter |
| Sentiment range | Slider for min and max score (−1.0 to +1.0); full range = no filter |
| Filter by publication date | Checkbox reveals a date-range picker (from / to) |
| Result limit | 50 – 10,000 rows |

All filters are active immediately — no form submission needed. **Run search** executes the query, **Clear results** resets the view.

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

### Long-Term Analysis Mode

Per-ticker deep-dive using the same Firestore query mechanism.

| Control | Description |
|---------|-------------|
| Select Ticker | Dropdown of all configured long-term tickers |
| Refresh data | Reloads Firestore data for the selected ticker |

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

**Purpose**: Summarize how publishers write across the saved article collection. Scans up to `30,000` records.

| Section | Content |
|---------|---------|
| Top-level metrics | Stored articles, publisher count, positive / neutral / negative publisher counts |
| Average Publisher Score | Collection-wide sentiment score + meter |
| Most Active Publisher | Publisher with the most saved articles |
| Publisher breakdown | Full publisher table with article count, average score, sentiment label |
| Export | CSV (ZIP), JSON, Excel |

Use **Refresh summary** to reload from Firestore.

---

## Long-Term Trends

**Purpose**: Monitor long-term ticker coverage. The collector is triggered daily by Cloud Scheduler (not by the web app). Scans up to `30,000` records.

### Collector Status

Four metrics reflecting the current state of the long-term data:

| Metric | Description |
|--------|-------------|
| Last Data Collection | Most recent `ingested_at` timestamp across all stored long-term records |
| Search Window | The `period` setting used by each collection run (e.g. `1 day`) |
| Max Articles / Ticker | Upper limit of articles fetched per ticker per run |
| Configured Tickers | Number of tickers being monitored |

If the in-process scheduler is running locally, a second row shows per-cycle totals (fetched, existing, new, saved, loaded).

### Coverage Overview

| Metric | Description |
|--------|-------------|
| Configured Tickers | Total number of tickers in the config |
| Tickers with Data | Tickers that have at least one saved article |
| Tickers without Data | Tickers not yet covered (collector may not have run for them) |
| Total Long-Term Articles | Total matching saved articles across all tickers |

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
| Article Growth Over Time | Cumulative total of all saved long-term articles by ingestion date |
| Daily Article Count by Ticker | Stacked bar chart of daily saves grouped by ticker |

Both charts use `Europe/Zurich` dates on the x-axis and support hover tooltips.

### Recent Articles

Table of the 200 most recently ingested articles across all configured tickers, with ticker, title, source, date, time, sentiment, and processing status.

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
