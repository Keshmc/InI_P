# UI Pages

This document describes the user-facing pages of the Streamlit application.

## News Search

Purpose:

- collect recent news for a keyword or trending topic
- analyze sentiment and entities
- save new articles to Datastore automatically

Main sections:

- search form
- loading/progress indicator
- sentiment overview
- sentiment distribution
- sentiment over time
- top extracted entities
- results table
- export section

Important behavior:

- the page requests up to `300` provider results
- duplicate articles already stored in Datastore are not reprocessed
- the final analysis view reloads from saved Datastore-backed records

## Article Library

Purpose:

- inspect and query the saved article collection

Modes:

- `Overview`
  - high-level collection metrics
  - sentiment overview
  - top trends, entities, publishers
  - article table
  - export section
- `Search`
  - filtered Datastore search
  - supports company, sector, sentiment threshold, date range, and result limit
  - result summary and filtered table
  - export section

Important behavior:

- overview and search can scan up to the latest `10,000` saved records
- timestamps are shown in `Europe/Zurich`

## Publisher Sentiment

Purpose:

- summarize how publishers write across the saved article dataset

Main sections:

- collection-wide publisher metrics
- publisher sentiment mix
- most active publishers
- strongest positive and negative publishers
- full publisher table
- export section

Important behavior:

- the page is summary-only
- it currently summarizes up to `5,000` saved records

## Long-Term Trends

Purpose:

- monitor long-term scheduler coverage for configured tickers
- keep an eye on Datastore growth for tracked themes

Main sections:

- scheduler status
- coverage overview
- active tickers table
- cumulative article growth over time
- daily ticker breakdown over time
- recent long-term articles
- export section

Important behavior:

- only records matching configured long-term tickers are included
- ticker detection checks saved fields such as `query`, `topic`, `company_keyword`, `symbol`, and legacy raw payload values
- the page scans up to the latest `10,000` saved records
