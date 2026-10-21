# PearEquity 🍐

This is a finance platform for testing equities and accumulating equity data.

## Overview

PearEquity is an end-to-end data platform for equity research. It ingests daily price history from Yahoo Finance, stores it in a persistent, queryable database, computes technical indicators and benchmark-relative performance, and runs reproducible strategy backtests against that history.

The platform is built in two parts. The **MVP** (Part 1 of the build plan) contains only what is necessary to load a single equity's price history into a database and backtest strategies against it: a Python ingester, a local DuckDB database, indicators in plain SQL, and a Python backtesting engine. Everything beyond that — a full symbol universe, orchestration, a cloud deployment, a public API — is collected in **Future build-out ideas** (Part 2), each adopted only when a concrete need appears.

The platform is SQL-first: data transformations and indicators are implemented in SQL, with Python used for ingestion and the backtesting engine. The MVP runs entirely locally on DuckDB, using Postgres-compatible SQL so the same logic can move to Amazon Redshift later if the future build-out is adopted.

## What the MVP does

* **Data accumulation** — Daily ingestion of OHLCV, dividend, and split data for one equity, plus the QQQ benchmark series the strategies are measured against. Raw pulls are stored as immutable, timestamped files on local disk; nothing is overwritten.
* **Database** — The price history lives in DuckDB: one append-only table, queryable in SQL from DataGrip or Python.
* **Indicators** — Moving averages (50/200-day), cross signals, RSI, ATR and Chandelier stops, and per-symbol alpha versus QQQ, all computed in SQL.
* **Backtesting** — Rule-based strategies executed against the accumulated history, with trades, daily equity curves, and the exact parameters and data snapshot persisted as queryable results.
* **Data quality** — Automated checks on every load: duplicate keys, missing trading days, OHLC consistency, and split-adjustment continuity.

## Architecture (MVP)

```
Yahoo Finance ──► Python ingestion ──► raw files (local, immutable)
                                              │
                                              ▼
                                     DuckDB database
                                     (price history + indicators in SQL)
                                              │
                                              ▼
                              Python backtesting engine
                              (results written back to DuckDB)
```

Future build-out ideas — full symbol universe, Airflow orchestration, AWS production deployment (S3, Redshift, KMS, Secrets Manager, IAM), and a Lambda API reading a DynamoDB serving layer — are described in the build plan. None of them are built, and none are required for the MVP.

## Technology stack (MVP)

| Area | Technologies |
|---|---|
| Languages | SQL, Python |
| Data store | DuckDB (single local database file), Parquet/CSV raw files |
| Source data | Yahoo Finance (via `yfinance`) |
| Tooling | GitHub, Sublime Text 4, DataGrip, Claude Code |

Future build-out technologies (dbt, Airflow, AWS services, JavaScript/HTML/CSS for any web layer) are listed with their adoption triggers in the stack document.

## Table of Contents

* [Stack & Technologies](docs/STACK.md) — the MVP stack, the role of each component, and the future build-out technologies with the criteria for adopting each one.
* [Iterations & Milestones](docs/ITERATIONS.md) — the build plan in two parts: Part 1, the MVP (four iterations: repository, one equity into a database, indicators, backtesting engine); Part 2, future build-out ideas, each with its adoption trigger.
