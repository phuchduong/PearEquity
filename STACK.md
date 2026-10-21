# PearEquity — Stack & Technologies

This document describes what PearEquity is built with and why. The build order is in [ITERATIONS.md](ITERATIONS.md).

## Design principles

1. **MVP first, minimal scope.** The MVP does exactly two things: get a single equity's price history into a database, and backtest strategies against it. Nothing enters the MVP that those two goals do not require. Everything else is a future build-out idea (below), adopted only when its trigger is met.
2. **SQL for data, Python for code.** Transformations, indicators, and data-quality checks are SQL. Python handles ingestion, orchestration glue, and the backtesting engine. JavaScript/HTML/CSS only if a web layer is ever built.
3. **No tool the project did not ask for.** New tools are added by decision, against a written trigger — never because a checklist has an unnamed slot. PearEquity is a simple app; simplicity is a feature.
4. **Free and local first.** The MVP runs entirely on the developer's machine at zero cost. Cloud services appear only in the future build-out, each with its cost stated before adoption.
5. **Raw data is immutable, everything else is reproducible.** Raw pulls are never modified after landing. Every derived table and every backtest result can be rebuilt from raw, and every backtest records the data snapshot and parameters that produced it.

## MVP stack

| Technology | Role in PearEquity |
|---|---|
| SQL | All data work: loading, indicator computation, quality checks, and backtest analysis queries. Written in a Postgres-compatible dialect so it can move to Redshift later without a rewrite. |
| Python | The ingestion code (Yahoo Finance pulls, file handling, DuckDB loading) and the backtesting engine — the strategy logic that cannot be expressed in SQL. Dependencies are defined once, in `pyproject.toml`; there is no separate requirements file. |
| DuckDB | The database. A single local file: in-process, columnar, Postgres-dialect SQL, reads CSV/Parquet directly. It is the local stand-in for a production warehouse — the "SQLite for analytics" role — and it comfortably holds decades of daily price history. |
| Yahoo Finance (via `yfinance`) | The source of daily price history: OHLCV, dividends, and splits. Free, no API key. |
| Parquet / CSV | The raw file format. One file per symbol per pull, timestamped, never modified after landing. |
| GitHub | The public repository: version control and the project's home. |
| Sublime Text 4 | The code editor, used whenever possible. |
| DataGrip | SQL and database work: authoring queries, browsing the DuckDB schema, inspecting data. Free for non-commercial use. |
| Claude Code | The AI coding assistant for the project, flexible per job market. |

## MVP data model

DuckDB tables, in the order data flows through them:

- `raw_prices_daily` — append-only: one row per symbol per trading day **per pull**, keyed by (symbol, date, ingested_at), exactly as pulled, plus source. Rows are never updated or deleted; a corrected price arrives as a new row with a later `ingested_at`. In the MVP this holds two series: the one equity, and QQQ as the benchmark series (the strategy rules are benchmark-relative, so the backtest cannot run without it).
- `stg_prices` — one row per (symbol, date): the most recent pull's values, cleaned and typed.
- `int_daily_returns` — daily returns per symbol, and alpha versus QQQ.
- `int_indicators` — 50-day and 200-day moving averages, golden/death cross flags, RSI, Wilder ATR(22), and the Chandelier stop (highest high over 22 days minus 6 × ATR, ratcheted so it never moves down).
- `fct_prices_enriched` — the analysis-ready table: prices joined with returns, alpha, and indicators.
- `fct_backtest_runs` / `fct_backtest_trades` / `fct_backtest_equity_curve` — backtest results: run metadata (strategy parameters, data snapshot), individual trades, and the daily equity curve.

Prices are kept in one consistent, split-adjusted frame throughout; indicator levels and triggers are computed on that same frame.

## Cost

The MVP costs nothing: DuckDB, Python, SQL, and GitHub (public repository) are free, Yahoo Finance needs no key, and there is no cloud account involved at all. Any future build-out item that introduces a standing charge states that cost in its adoption decision before it is built.

## Future build-out technologies

None of these are in the MVP. Each is adopted only when its trigger is met, and the adoption — with its reason and, where relevant, its cost — is recorded when it happens.

| Technology | What it would add | Adoption trigger |
|---|---|---|
| Full symbol universe | `config/symbols.csv` grows from one equity (+ QQQ benchmark) to a watchlist, with a symbol-history table for renames (FB → META, SQ → XYZ), mergers, and delistings. | Backtests need to compare or coordinate multiple equities. |
| dbt | The SQL models become a managed dbt project: tests, documentation, lineage. | The handful of MVP SQL files grows into enough models that tests and lineage pay for the tooling. |
| Apache Airflow | Scheduled, unattended orchestration of the daily pipeline (pull → load → transform → quality gate), with retries and backfill support. Runs locally in Docker Compose. | The daily pipeline has enough steps, dependencies, and retry/backfill needs that running a script by hand is the bottleneck. |
| Amazon S3 | Cloud landing zone for raw files and a `curated/` Parquet prefix, replacing local disk as the durable store. | The data must live beyond one machine, or the AWS production build-out is adopted. |
| Amazon Redshift Serverless | The production warehouse: the DuckDB models promoted to a shared, always-available store with the same Postgres-compatible SQL. | Local DuckDB can no longer answer queries interactively, or a shared production store is needed. |
| AWS KMS + Secrets Manager + IAM | Encryption at rest, managed credentials, and role-based access (people via IAM Identity Center, workloads via roles, no long-lived keys) for the AWS resources. | The first AWS resource is created. Note: these carry small standing charges (about $1/month per KMS key, $0.40/month per secret), so the AWS build-out starts with AWS Budget alerts at $1 / $5 / $10. |
| Amazon DynamoDB | The API serving layer. Redshift is a warehouse built for analytical scans — per-request serving is an anti-pattern for it — so a publish step would copy API-shaped data (prices/indicators by symbol and date, backtest metadata) into DynamoDB for millisecond key lookups; large payloads (equity curves) would sit in S3 with DynamoDB pointers. Permanent free tier (25 GB, 25 read / 25 write units) covers this project's scale. | The API is adopted (below). |
| AWS Lambda + API Gateway | A public API — `GET /prices/{symbol}`, `GET /indicators/{symbol}`, `POST /backtests`, `GET /backtests/{id}`, `GET /backtests/{id}/equity-curve` — for downstream systems, reading only the serving layer. | A real downstream consumer needs programmatic access. |
| S3 Glacier lifecycle | Automatic archiving of raw files: Glacier Flexible after 90 days, Deep Archive after 365 days, under one S3 bucket with `raw/` and `curated/` prefixes. | S3 is adopted and raw data has accumulated. |
| AWS Glue | Serverless Spark ETL and a Data Catalog for the curated zone. | A workload outgrows single-machine DuckDB/dbt processing. |

**Explicitly not adopted, by decision:** infrastructure-as-code tooling (Terraform and similar) — PearEquity's AWS footprint would be a handful of resources created once; they are set up manually in the Console (or with AWS CLI commands) and written down as a setup guide under `infra/`, with the decision revisited only if resources reach the dozens or a second environment appears. Managed Airflow (MWAA), provisioned Redshift clusters, NAT Gateways, and cache clusters (ElastiCache, API Gateway caching) are likewise avoided: each bills continuously while idle, and a cache in front of the warehouse is cost spent protecting a database the API should not query at all.
