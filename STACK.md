# PearEquity — Stack & Technologies

This document describes what PearEquity is built with and why. For the build order and milestones, see [ITERATIONS.md](ITERATIONS.md).

## Principles

1. **SQL for data, Python for code.** Every transformation, indicator, and backtest rule that can be expressed in SQL is written in SQL. Python handles pulling, loading, orchestration glue, and API handlers.
2. **Accumulate, never overwrite.** Raw price pulls are immutable and timestamped. Corrections and restatements create new records, so any historical result can be reproduced.
3. **Local first, production by promotion.** The same SQL runs on DuckDB locally and Redshift in production. A model is promoted, not rewritten.
4. **Free and low-cost tiers first.** Prefer open-source software and AWS free / low-cost tiers. Pay for a service only when a defined trigger (see below) is met.
5. **Add tools when necessary.** Each optional tool has a written trigger. Nothing enters the stack because it might be useful someday.

## Languages

| Language | Used for |
|---|---|
| SQL | Data modelling, transformations, indicators, backtest logic, data-quality checks. Postgres-compatible dialect throughout. |
| Python | Ingestion from Yahoo Finance, loaders, Airflow DAGs, Lambda handlers, backtest code that cannot be expressed in SQL. |
| JavaScript / HTML / CSS | Only where the web layer requires it — API examples, documentation, and any PearEquity status pages. |

## Editors & Tooling

| Tool | Role |
|---|---|
| Sublime Text 4 | Primary code editor, used whenever possible. Paired with the terminal and Git CLI for running, testing, and version control. |
| DataGrip | SQL and database work: authoring queries, browsing schemas in DuckDB and Redshift, inspecting data, tuning queries. Free for non-commercial use. |
| Claude Code | AI coding assistant for the project. Kept flexible — the repository stores its rules in `AGENTS.md` so a different assistant can be adopted without restructuring the project. |
| GitHub | Central repository (public) and CI via GitHub Actions: lint, tests, and dbt compilation on every change. |

## Data Stores

| Store | Role |
|---|---|
| DuckDB | Local data store. A single embedded file, columnar, Postgres-dialect SQL. Used for development, prototyping, and fast backtest iteration with no server to run. |
| Amazon Redshift Serverless | Production data store. Columnar warehouse with Postgres-compatible SQL, billed per query capacity used, so it costs nothing while idle apart from storage. Schemas mirror the DuckDB models. |
| Amazon S3 | Landing zone and file store. `raw/` holds every API pull, immutable and timestamped. `curated/` holds cleaned Parquet files ready to load. Versioning on, public access blocked. |
| Parquet | File format for landed and curated data: compact, columnar, readable by DuckDB, Redshift, and Glue alike. |

## Data Pipeline

| Component | Role |
|---|---|
| Yahoo Finance (via `yfinance`) | Source of daily price history: open, high, low, close, adjusted close, volume, dividends, and splits. Pulled incrementally in Python. |
| dbt | SQL transformation layer. Builds staging, intermediate, and mart models; runs schema and data tests; generates model documentation and lineage. |
| Apache Airflow | Orchestrator. Schedules and runs the daily pipeline — pull, land, load, transform, quality-check — with dependencies, retries, and backfills. Runs locally in Docker. |
| AWS Glue | Batch processing on Apache Spark, added only when necessary (see triggers). Also provides the Data Catalog if S3 data needs a shared catalog of record. |

## Cloud Services (AWS)

| Service | Role |
|---|---|
| AWS Lambda + API Gateway | The PearEquity API: price lookups, indicator queries, backtest submission and results. Serverless, with a perpetual free tier of 1M requests and 400,000 GB-seconds per month that covers expected use. |
| AWS KMS | Encryption for S3, Redshift, and secrets. One customer-managed key for the project ($1/month per key), AWS-managed keys elsewhere. |
| AWS Secrets Manager | Database credentials and any API keys ($0.40 per secret per month — secret count is kept low by grouping fields into a single JSON secret). Non-secret configuration lives in SSM Parameter Store at no cost. |
| IAM | All authentication and authorization. People sign in through IAM Identity Center with multi-factor authentication and temporary credentials. Applications and services use IAM roles with temporary credentials — Lambda execution roles, and GitHub Actions connected by OIDC federation. No long-lived access keys in code, configuration, or the repository. Amazon Cognito would be added only if public end-user accounts are ever needed; IAM is not an end-user identity system. |
| S3 Glacier Flexible / Deep Archive | Long-term archiving, applied by S3 lifecycle rules rather than by hand: raw landing data moves to Glacier Flexible after 90 days and Deep Archive after 365 days. |
| AWS Budgets | Cost guardrails: alerts at $1, $5, and $10 of monthly spend. The production region is us-west-2. |

### Cost notes

- Always-free or effectively free at PearEquity's scale: Lambda, GitHub Actions (public repository), DuckDB, Airflow, and dbt Core.
- Small standing charges by design: KMS customer-managed key ($1/month), Secrets Manager ($0.40/secret/month), S3 storage, and Redshift Serverless capacity while queries run (a $300 / 90-day trial covers first use).
- Avoided by design: provisioned Redshift clusters, managed Airflow (MWAA), and NAT Gateways — each bills continuously while idle.

## "When necessary" triggers

| Tool | Add it when |
|---|---|
| dbt | SQL transforms grow beyond roughly five models, or model tests, documentation, and lineage are needed. Expected in Iteration 2. |
| Apache Airflow | The daily pipeline has three or more dependent steps needing retries and backfills. Expected in Iteration 3. Before that, a scheduled Python script is sufficient. |
| Amazon Redshift | Local DuckDB can no longer answer backtest queries interactively, or a shared production store is needed. Expected in Iteration 4. |
| AWS Lambda | A consumer needs an API — price, indicator, and backtest endpoints for downstream systems, or an event trigger on S3 arrival. Expected in Iteration 5. |
| AWS Glue | A transformation outgrows SQL and Python on a single machine — for example, reprocessing tens of millions of rows — or the Glue Data Catalog is needed as the catalog of record. No fixed iteration; added only if a workload demands it. |
| S3 Glacier | Raw landing data older than 90 days exists. Applied as an automatic lifecycle rule in Iteration 6. |

## Data model (summary)

- `raw_prices_daily` — one row per symbol per trading day, exactly as pulled, plus source and ingestion timestamp.
- `dim_symbol` / `dim_symbol_history` — symbols and their history: renames, mergers, delistings, with effective dates and reasons.
- `stg_prices` — cleaned, typed, deduplicated prices (split-adjusted frame used consistently for indicators).
- `int_indicators` — daily returns, 50/200-day moving averages, cross signals, RSI, ATR, Chandelier stop levels, alpha versus benchmark.
- `fct_backtest_*` — backtest runs, trades, and daily equity curves, one set per strategy variant and parameter set.
