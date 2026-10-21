# PearEquity — Iterations & Milestones

This document is the build plan for PearEquity, in two parts. For what the project is built with and why, see [STACK.md](STACK.md).

**Part 1 — the MVP** is the committed plan: only what is necessary to get a single equity's price history into a database and backtest strategies against it. Four iterations, each ending at a milestone with explicit exit criteria — an iteration is done when its criteria pass, not when its tasks feel finished.

**Part 2 — future build-out ideas** is not a schedule. It collects everything beyond the MVP, each item with the trigger that would justify adopting it. Nothing in Part 2 is built unless its trigger is met and the adoption is recorded.

The first backtest target is a pyramiding strategy: positions start small, add fixed-size blocks only when the most recent block is outperforming the QQQ benchmark by a set alpha threshold, observe a cool-off period between adds, and exit in tranches on trend signals (moving-average breaks, death cross, and a Chandelier/ATR stop).

---

# Part 1 — MVP

## MVP Iteration 1 — Repository foundation

**Goal:** A clean, public repository with the minimum conventions the MVP builds on — and nothing built ahead of its iteration.

- [ ] GitHub repository created: https://github.com/phuchduong/PearEquity
- [ ] Root files only at this stage: `README.md`, `docs/`, `.gitignore`, `.env.example`, `AGENTS.md`, `pyproject.toml`. Code directories are created with real code in their iterations, never as empty placeholders
- [ ] `.gitignore` excluding data files, the DuckDB database, `.env`, and secrets
- [ ] Python project setup: a single `pyproject.toml` holding project metadata and pinned dependencies (no separate requirements file)
- [ ] Editor setup documented: Sublime Text 4 as the code editor, DataGrip for SQL/database work
- [ ] `AGENTS.md` with project rules for AI coding assistants: SQL for data, Python for code, no secrets in code, one consistent split-adjusted price frame, no tools added without a recorded decision

**Milestone:** The repository is public, a fresh clone can be set up with one documented command sequence, and the three planning documents are committed.

## MVP Iteration 2 — One equity into a database (DuckDB)

**Goal:** One equity's real price history, stored locally in DuckDB, queryable in SQL, reproducible from scratch. The database also holds QQQ as a benchmark series — the strategy rules are benchmark-relative, so the backtest cannot run without it. No other symbols.

- [ ] `config/symbols.csv` with exactly the MVP series: the chosen equity, and QQQ flagged as benchmark
- [ ] Python ingester using `yfinance`: one raw file per symbol per pull on local disk, with pull timestamp, dividends, and splits preserved; raw files are never modified after landing
- [ ] DuckDB loader creating `raw_prices_daily` — append-only, one row per symbol per trading day per pull, keyed by (symbol, date, ingested_at), exactly as pulled; nothing is ever updated or deleted
- [ ] Backfill: daily history from 2018-01-01 (or IPO date, if later) for the MVP series
- [ ] Update path: one command pulls new data, appends it, and reports row counts and date ranges per symbol versus the source
- [ ] Data-quality checks in SQL: no duplicate (symbol, date) in the cleaned layer, no missing trading days against the NYSE calendar, OHLC sanity (low ≤ open/close ≤ high), adjusted-close continuity around splits
- [ ] DataGrip connected to DuckDB, with saved exploratory queries for moving averages, returns, and drawdowns

**Milestone:** One command backfills or updates the history. The quality report is clean, or every exception is documented per symbol. A known historical calculation (days the equity spent below its 200-day average over a multi-year window) reproduces exactly.

## MVP Iteration 3 — Indicators in SQL

**Goal:** Every number the strategies need, computed in tested SQL on top of the stored history — no framework, plain SQL files in the repository.

- [ ] `stg_prices`: one row per (symbol, date) — the most recent pull's values from `raw_prices_daily`, cleaned and typed
- [ ] `int_daily_returns`: daily returns per symbol, and alpha versus QQQ (daily and rolling 1-year / 5-year)
- [ ] `int_indicators`: 50-day and 200-day moving averages, golden/death cross flags, RSI, Wilder ATR(22), Chandelier stop (highest high over 22 days minus 6 × ATR, ratcheted so it never moves down)
- [ ] `fct_prices_enriched`: prices joined with returns, alpha, and indicators — the single table the backtesting engine reads
- [ ] SQL checks on the models: unique and not-null (symbol, date) keys, sane value ranges, row-count reconciliation between raw, staging, and enriched layers
- [ ] All SQL runs on the consistent split-adjusted price frame, so levels match what a chart shows

**Milestone:** All models rebuild from raw with one command, the checks pass, and indicator values spot-check against an independent chart source within a documented tolerance.

## MVP Iteration 4 — Backtesting engine

**Goal:** Strategies backtest against the accumulated history, with results persisted in the database and reproducible exactly.

- [ ] Backtest engine (Python) implementing the pyramiding strategy against the one equity:
  - A benchmark reservoir (QQQ) funds all buys; all sale proceeds return to it the same day
  - Positions open with a small starter; fixed-size blocks are added only when the most recent live block beats the benchmark by the alpha threshold (+5% default)
  - A 28-day cool-off per symbol between buys
  - Forced liquidation, weakest alpha first and only for blocks below a −15% alpha floor, only when needed to fund a pending qualifying buy
  - Fully sold positions may re-open only on a golden cross, with a single-share opening block
- [ ] Exit tranches implemented as data, not hard-coded branches:
  - 200-day average tranche: sells after 3 consecutive closes below the 200-day average, at the next open
  - Death-cross tranche: sells 34% of the position as it stands; the remainder stays invested and can add blocks again
  - Chandelier tranche: Wilder ATR(22) stop at highest high (22) minus 6 × ATR, ratcheted
- [ ] Result tables in DuckDB: `fct_backtest_runs` (strategy parameters + data snapshot recorded per run), `fct_backtest_trades`, `fct_backtest_equity_curve`
- [ ] Reference results reproduced: a set of previously calculated strategy runs (fixed symbol, fixed window) match the engine's output exactly, validating the implementation

**Milestone:** One command runs a full backtest end-to-end — pull, load, indicators, engine — and the reference results match. The MVP is complete: one equity's history in a database, and strategies backtested against it.

### Intended repository artifacts (MVP)

None of these exist yet beyond the planning documents. They are created in the iteration noted, and only described in the README once they are real.

| Path | Intended artifact | Created in |
|---|---|---|
| `docs/STACK.md` | The stack and technologies, and the reasons for each choice. | MVP Iteration 1 (planning) |
| `docs/ITERATIONS.md` | This document: the MVP plan and the future build-out ideas. | MVP Iteration 1 (planning) |
| `AGENTS.md` | Project rules to follow when code is written. | MVP Iteration 1 |
| `.gitignore` | Rules keeping data files, the database file, `.env`, and secrets out of the repository. | MVP Iteration 1 |
| `.env.example` | A template of environment variable names, with no values. | MVP Iteration 1 |
| `pyproject.toml` | The single Python project and dependency definition. There is no separate `requirements.txt`. | MVP Iteration 1 |
| `config/symbols.csv` | The MVP series: one equity, plus QQQ as benchmark. | MVP Iteration 2 |
| `ingestion/` | The Python ingester and DuckDB loader. | MVP Iteration 2 |
| `sql/` | The SQL models: staging, returns, indicators, enriched prices, and the quality checks. | MVP Iterations 2–3 |
| `backtest/` | The Python backtesting engine. | MVP Iteration 4 |
| `tests/` | Tests for the loader, the SQL checks, and the engine's reference results. | MVP Iterations 2–4, as applicable |

---

# Part 2 — Future build-out ideas

Not scheduled. Each idea states what it adds and the trigger that would justify it; adoption is a recorded decision, taken only when the trigger is met. The technologies and their roles are detailed in [STACK.md](STACK.md#future-build-out-technologies).

## Future 1 — Full symbol universe

Grow `config/symbols.csv` from one equity to a watchlist, with a symbol-history table recording renames (e.g. FB → META, SQ → XYZ), mergers, and delistings with effective dates and reasons, so long-horizon analysis stays correct. **Trigger:** backtests need to compare or coordinate multiple equities.

## Future 2 — Portfolio-scale backtesting & parameter sweeps

Extend the engine from one equity to the whole universe: the one-buy-per-trading-day portfolio rule (highest qualifying alpha wins), cross-position funding and liquidation order, and systematic parameter sweeps (alpha threshold, cool-off length, tranche sizes) comparable in a single SQL query. **Trigger:** the universe exists (Future 1) and single-equity results justify portfolio questions.

## Future 3 — dbt transformation layer

Promote the plain SQL models into a dbt project (DuckDB adapter first): the same models with dbt tests, generated documentation, and lineage. **Trigger:** the model count grows past a handful, or tests/lineage are needed by someone other than the author.

## Future 4 — Airflow orchestration

Airflow in Docker Compose: DAG `daily_price_pipeline` (pull → land → load → transform → quality gate → summary) with retries and failure alerting, a `weekly_full_refresh` DAG, and a documented backfill runbook. Success bar if adopted: seven consecutive unattended daily runs. **Trigger:** the daily pipeline's steps, dependencies, and backfill needs make hand-running the script the bottleneck.

## Future 5 — AWS production foundation

Move the platform to AWS, set up manually (Console or AWS CLI, written down as a setup guide in `infra/` — no infrastructure-as-code tool; see STACK.md): AWS Budget alerts at $1 / $5 / $10 first, then one S3 bucket (prefixes `raw/` and `curated/`, versioning on, public access blocked, SSE-KMS), one KMS customer-managed key, Secrets Manager holding credentials as a single grouped secret with non-secret configuration in SSM Parameter Store, IAM roles throughout (GitHub Actions via OIDC, no stored keys), and Redshift Serverless mirroring the DuckDB models so the same SQL builds against both targets. **Trigger:** the data must live beyond one machine, or local DuckDB stops answering queries interactively.

## Future 6 — API & serving layer (Lambda, DynamoDB)

A publish step after each production build copies API-shaped data into DynamoDB (prices/indicators keyed by symbol and date, backtest run metadata; full equity curves as JSON in the S3 `curated/` prefix, with DynamoDB pointers) — the API never queries Redshift, which is an analytical warehouse, not a per-request serving database. Lambda + API Gateway expose `GET /prices/{symbol}`, `GET /indicators/{symbol}`, `POST /backtests`, `GET /backtests/{id}`, `GET /backtests/{id}/equity-curve`, with the Lambda role limited to DynamoDB, S3, and Secrets Manager. **Trigger:** a real downstream consumer needs programmatic access.

## Future 7 — API consumers & archiving

An OpenAPI contract, sample payloads, and a minimal HTML/JavaScript example consumer under `examples/`; S3 lifecycle rules moving `raw/` data to Glacier Flexible after 90 days and Deep Archive after 365 days (each object ages on its own clock once the rule is live), with an archive restore drill documented; and a recorded Glue decision — adopt a Glue job and Data Catalog for the curated zone if a workload has outgrown DuckDB/dbt, or record the deferral and its reason. **Trigger:** the API exists (Future 6) and has consumers; archiving follows once S3 holds accumulated raw data.

## Future 8 — Hardening & documentation

A demo mode (a small committed sample dataset that runs the MVP end-to-end with no setup beyond the repository), runbooks (daily operations, backfills, responding to a bad source pull), a full documentation pass with actual costs, and a technology review re-checking every future idea above against its trigger. **Trigger:** someone other than the author needs to run or reproduce the platform.

---

## Standing guardrails

- **Simplicity:** The MVP is the ceiling until it is finished. No future idea is started early, no tool is added without its trigger and a recorded decision, and nothing is scaffolded as an empty placeholder.
- **Cost:** The MVP costs nothing. Any future adoption that introduces a standing charge states the cost first; AWS work begins with Budget alerts at $1 / $5 / $10, and no continuously billed infrastructure (provisioned clusters, managed orchestration, NAT Gateways, cache clusters) is introduced without a written decision.
- **Data integrity:** Raw data is never modified after landing. Every derived table can be rebuilt from raw. Every backtest result records the data snapshot and parameters that produced it.
- **Security:** No secrets, credentials, or access keys in the repository, ever. If AWS is adopted, all access is through IAM roles with temporary credentials.
