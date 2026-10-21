# PearEquity 🍐

This is a finance platform for testing equities and accumulating equity data.

## Overview

PearEquity is an end-to-end data platform for equity research. It ingests daily price history from Yahoo Finance, stores it in a persistent, queryable warehouse, computes technical indicators and benchmark-relative performance, and runs reproducible strategy backtests against that history. Results are served through an API so downstream systems can consume them.

The platform is SQL-first: data transformations, indicators, and backtest logic are implemented in SQL (via dbt), with Python used for ingestion, orchestration, and API code. It is designed to run locally on DuckDB during development and on Amazon Redshift in production, using Postgres-compatible SQL in both environments.

## What the platform does

* **Data accumulation** — Incremental daily ingestion of OHLCV, dividend, and split data. Raw pulls land in Amazon S3 as immutable, timestamped files; nothing is overwritten.
* **Data modelling** — dbt models clean and enrich the raw data, including symbol history (renames, mergers, delistings) so long-horizon analysis stays correct.
* **Indicators** — Moving averages (50/200-day), cross signals, RSI, ATR and Chandelier stops, and per-symbol alpha versus a benchmark (QQQ), all computed in SQL.
* **Backtesting** — Rule-based strategies executed against the accumulated history, with trades, daily equity curves, and parameter sweeps persisted as queryable results.
* **Data quality** — Automated checks on every load: duplicate keys, missing trading days, OHLC consistency, and split-adjustment continuity.
* **API access** — Prices, indicators, and backtest results exposed via AWS Lambda and API Gateway for downstream consumers.

## Architecture

```
Yahoo Finance ──► Python ingestion ──► S3 landing (raw, immutable)
                                              │
                    Airflow orchestration     ▼
              DuckDB (local)  ◄── dbt models ──►  Redshift Serverless (production)
                                              │
                                       Lambda API (API Gateway)
                                              │
                                   Downstream systems
```

Security and platform services: IAM roles for all AWS access (no long-lived keys), KMS encryption at rest, Secrets Manager for credentials, and S3 Glacier lifecycle policies for long-term archiving of raw data. AWS Glue is reserved for workloads that outgrow single-machine processing.

## Technology stack

| Area | Technologies |
|---|---|
| Languages | SQL, Python; JavaScript / HTML / CSS where a web layer requires it |
| Data stores | DuckDB, Amazon Redshift Serverless, Amazon S3, Parquet |
| Transformation & orchestration | dbt, Apache Airflow |
| API & cloud services | AWS Lambda, API Gateway, KMS, Secrets Manager, IAM, S3 Glacier |
| Source data | Yahoo Finance (via `yfinance`) |
| Tooling | GitHub, Sublime Text 4, DataGrip, Claude Code |

## Table of Contents

* [Stack & Technologies](docs/STACK.md) — the full technology stack, the role of each component, and the criteria for adding optional services.
* [Iterations & Milestones](docs/ITERATIONS.md) — the build plan: seven iterations from local data foundation to production deployment, backtesting, and API delivery, each with defined exit criteria.
