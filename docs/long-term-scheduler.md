# Long-Term Scheduler

This document explains how automatic long-term ticker ingestion works.

## Purpose

The long-term scheduler performs recurring background searches for a configured set of tickers and stores new articles in Datastore.

This enables:

- repeated collection over time
- long-term monitoring in the UI
- article growth charts based on saved records

## Configuration

The scheduler is configured in `config.yaml` under `long_term_trends`.

Relevant fields:

- `enabled`
  - turns the scheduler on or off
- `interval_minutes`
  - run interval in minutes
- `run_on_startup`
  - if enabled, the scheduler starts one collection cycle when the app process starts
- `period`
  - provider period passed to the news loader
- `max_results`
  - requested result count per ticker
- `extract_full_text`
  - enables article extraction before analysis
- `include_entities`
  - enables entity extraction
- `tickers`
  - list of tracked long-term search terms

## Current Default Behavior

Current project defaults:

- interval: every `360` minutes
- run on startup: `true`
- max results per ticker: `300`

Configured tickers:

- `Trump`
- `Iran`
- `Oil`
- `Gold`
- `NVDA`
- `Tesla`
- `MSFT`
- `Apple`
- `USA`

## Lifecycle

The scheduler is initialized in the Streamlit view layer and behaves as a process-wide singleton.

When enabled:

1. the app starts the scheduler thread
2. one cycle runs immediately if `run_on_startup` is enabled
3. the next cycle waits for the configured interval
4. every cycle requests news for each configured ticker
5. new records are analyzed and saved to Datastore
6. status information is exposed to the sidebar and the `Long-Term Trends` page

## Stored Data Used By The Dashboard

The `Long-Term Trends` page identifies matching records using these saved fields:

- `query`
- `topic`
- `company_keyword`
- `symbol`
- legacy values inside `raw_article_json`

For chart timestamps, the page prefers:

1. `ingested_at`
2. `analysis_timestamp`
3. `published_at`
4. `published_date`

This allows the dashboard to still show growth even when the original article timestamp is incomplete.

## Status Fields

The scheduler exposes status information including:

- `enabled`
- `running`
- `last_run_at`
- `last_result`
- `last_error`
- `interval_minutes`
- `tickers`

The latest run summary typically includes totals such as:

- `fetched`
- `existing`
- `new`
- `saved`
- `loaded`

## Provider Caveat For Large Result Sets

The application can request up to `300` results per ticker, but the underlying `gnews` provider has important caveats:

- searches above `100` results may not apply time-range handling as strictly as smaller searches
- provider behavior for large result sets can differ from standard `<=100` searches

The application suppresses noisy provider warnings in the UI/runtime output, but the provider limitation still exists conceptually.

If strict period handling becomes more important than volume, consider reducing `max_results` back toward `100`.
