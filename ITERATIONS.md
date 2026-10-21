# PearEquity — Iterations & Milestones

This document is the build plan for PearEquity, in order. For what the project is built with and why, see [STACK.md](STACK.md).

PearEquity grows in seven iterations: a local data foundation first, then transformations, orchestration, a production cloud deployment, the backtesting engine, a public API, and finally hardening and documentation. Each iteration ends at a milestone with explicit exit criteria — an iteration is done when its criteria pass, not when its tasks feel finished.

The first backtest target is a pyramiding strategy: positions start small, add fixed-size blocks only when the most recent block is outperforming the QQQ benchmark by a set alpha threshold, observe a cool-off period between adds, and exit in tranches on trend signals (moving-average breaks, death cross, and a Chandelier/ATR stop).

---

## Iteration 0 — Repository foundation

**Goal:** A clean, public repository with the conventions every later iteration builds on.

- [ ] GitHub repository created: https://github.com/phuchduong/PearEquity
- [ ] Repository skeleton: `ingestion/`, `dags/`, `dbt/`, `sql/`, `api/`, `infra/`, `config/`, `examples/`, `tests/`, `docs/`
- [ ] README, stack document, and this iteration plan committed
- [ ] `.gitignore` excluding data files, `.env`, and secrets; `.env.example` with local settings only
- [ ] Python project setup: `pyproject.toml`, pinned dependencies, lint and formatting configuration
- [ ] Editor setup documented: Sublime Text 4 project file, DataGrip connections for DuckDB
- [ ] `AGENTS.md` with project rules for AI coding assistants: SQL for data, Python for code, no secrets in code, consistent split-adjusted price frame
- [ ] GitHub Actions CI: Python lint and tests, SQL lint, on every pull request
- [ ] AWS account basics: root account MFA, IAM Identity Center sign-in, IAM roles instead of access keys, AWS Budget alerts at $1 / $5 / $10, region us-west-2

### Intended repository artifacts

None of these exist yet. They are created in the iteration noted, and only described in the README once they are real.

| Path | Intended artifact | Created in |
|---|---|---|
| `docs/STACK.md` | The planned stack and technologies, and the reasons for each choice. | Iteration 0 (planning) |
| `docs/ITERATIONS.md` | This document: the planned build order, iterations, tasks, milestones, and exit criteria. | Iteration 0 (planning) |
| `AGENTS.md` | Project rules to follow when code is written. | Iteration 0 |
| `config/symbols.csv` | The symbol universe. An example file (three rows: QQQ, VOO, SPY) may be drafted to show the format; it is not a loaded universe until Iteration 1. | Iteration 1 |
| `requirements.txt` | The Python packages the ingestion code uses (yfinance, duckdb, pandas, pyarrow). | Iteration 1, with the first code |
| `.env.example` | A template of environment variable names, with no values. | Iteration 1 |
| `.gitignore` | Rules keeping data files, `.env`, and secrets out of the repository. | Iteration 0 |
| `PearEquity.sublime-project` | A Sublime Text 4 project file for the repository. | Iteration 0 |
| `ingestion/`, `dags/`, `dbt/`, `sql/`, `api/`, `infra/`, `examples/`, `tests/` | Code directories for ingestion, Airflow DAGs, dbt models, SQL, the Lambda API, infrastructure, examples, and tests. Created with real code in their iterations — not as empty placeholders. | Iterations 1–6, as applicable |

**Milestone:** CI is green on an initial pull request, and a fresh clone can be set up with one documented command sequence.

---

## Iteration 1 — Local data foundation (DuckDB)

**Goal:** Real price history, stored locally, queryable in SQL, and reproducible from scratch.

- [ ] Symbol universe in `config/symbols.csv`, including benchmark symbols (QQQ, VOO, SPY)
- [ ] Symbol history table design: renames (e.g. FB → META, SQ → XYZ), mergers, and delistings recorded with effective dates and reasons
- [ ] Python ingester using `yfinance`: one raw file per symbol per pull, with pull timestamp, dividends, and splits preserved
- [ ] DuckDB loader creating `raw_prices_daily` (symbol, date, open, high, low, close, adjusted close, volume, dividends, splits, source, ingested_at), keyed by (symbol, date), with idempotent upserts
- [ ] Backfill: daily history from 2018-01-01 (or IPO date, if later) for the full symbol universe
- [ ] Reconciliation report: row counts and date ranges per symbol versus the source
- [ ] Data-quality checks in SQL: no duplicate keys, no missing trading days against the NYSE calendar, OHLC sanity (low ≤ open/close ≤ high), adjusted-close continuity around splits
- [ ] DataGrip connected to DuckDB, with saved exploratory queries for moving averages, returns, and drawdowns

**Milestone:** One command backfills or updates the full history. The quality report is clean, or every exception is documented per symbol. A known historical calculation (days a sample symbol spent below its 200-day average over a multi-year window) reproduces exactly.

---

## Iteration 2 — Transformations & indicators (dbt)

**Goal:** All data logic lives in tested, documented SQL models.

*dbt is added in this iteration — its trigger (more than a handful of SQL models, plus a need for tests and lineage) is met as soon as staging and indicator models exist.*

- [ ] dbt project with the DuckDB adapter
- [ ] Models: `staging/stg_prices`, `intermediate/int_daily_returns`, `intermediate/int_indicators`, `marts/fct_prices_enriched`
- [ ] Indicators: 50-day and 200-day moving averages, golden/death cross flags, RSI, Wilder ATR(22), Chandelier stop (highest high over 22 days minus 6 × ATR, ratcheted so it never moves down)
- [ ] Benchmark models: per-symbol daily and rolling 1-year / 5-year alpha versus QQQ
- [ ] dbt tests: unique and not-null keys, accepted value ranges, and reconciliation between staging and mart row counts
- [ ] dbt documentation generated, including model lineage

**Milestone:** `dbt build` passes from a clean DuckDB file, documentation is generated, and indicator values spot-check against an independent chart source within a documented tolerance for the split/dividend adjustment frame.

---

## Iteration 3 — Orchestration (Airflow)

**Goal:** The daily pipeline runs itself, with retries, alerting, and painless backfills.

*Airflow is added in this iteration — its trigger (a multi-step daily pipeline with dependencies, retries, and backfills) is met once ingestion, loading, transformation, and quality checks all need to run in order every day.*

- [ ] Airflow running locally in Docker Compose
- [ ] DAG `daily_price_pipeline`: pull prices → land raw files → load DuckDB → run dbt → run quality gate → publish a run summary
- [ ] Retries with backoff on the pull step, failure alerting, catchup disabled
- [ ] DAG `weekly_full_refresh`: full-universe refresh, reconciled against the daily path
- [ ] Backfill runbook: a documented 30-day backfill, executed and verified

**Milestone:** Seven consecutive unattended daily runs succeed. A deliberately broken pull fails visibly and retries. A backfill reproduces identical mart rows.

---

## Iteration 4 — Production cloud foundation (S3, KMS, Secrets, Redshift)

**Goal:** The same pipeline running on AWS, secured with roles and encryption, at free-tier-first cost.

*Redshift is added in this iteration — its trigger (a shared production store, and queries that have outgrown comfortable local iteration) is met once the backtest work of Iteration 5 is on the horizon.*

- [ ] Infrastructure as code in `infra/` for all AWS resources in this iteration
- [ ] S3 buckets: `raw/` landing and `curated/` Parquet zones, versioning enabled, public access blocked, encrypted with KMS (SSE-KMS)
- [ ] One KMS customer-managed key for S3, Redshift, and secrets, with a least-privilege key policy
- [ ] Secrets Manager holding database credentials as a single grouped secret; non-secret configuration in SSM Parameter Store; no sensitive values in the repository
- [ ] IAM roles for GitHub Actions (OIDC federation, no stored AWS keys), the ETL pipeline, and read-only access; human access through IAM Identity Center; IAM Access Analyzer review clean
- [ ] Redshift Serverless namespace and workgroup, using trial credits first; schemas mirroring the DuckDB marts; data loaded from S3 curated Parquet
- [ ] dbt Redshift profile: the same models build against Redshift with `--target redshift`
- [ ] Cost checkpoint: projected monthly cost at current usage documented in the README

**Milestone:** The same dbt models build green on both DuckDB and Redshift. A new symbol flows from pull to S3 to Redshift using IAM role authentication only — no access keys anywhere in the path.

---

## Iteration 5 — Backtesting engine & API (Lambda)

**Goal:** Strategies backtest against the accumulated history, and the results are available to other systems through the API.

*Lambda is added in this iteration — its trigger (a real API consumer) is met because downstream systems need price, indicator, and backtest endpoints.*

- [ ] Backtest engine implementing the pyramiding strategy:
  - A benchmark reservoir (QQQ) funds all buys; all sale proceeds return to it the same day
  - Positions open with a small starter; fixed-size blocks are added only when the most recent live block beats the benchmark by the alpha threshold (+5% default)
  - One buy per trading day across the whole portfolio — the highest qualifying alpha wins
  - A 28-day cool-off per symbol between buys
  - Forced liquidation, weakest alpha first and only for blocks below a −15% alpha floor, only when needed to fund a pending qualifying buy
  - Fully sold positions may re-open only on a golden cross, with a single-share opening block
- [ ] Exit tranches implemented as data, not hard-coded branches:
  - 200-day average tranche: sells after 3 consecutive closes below the 200-day average, at the next open
  - Death-cross tranche: sells 34% of the position as it stands; the remainder stays invested and can add blocks again
  - Chandelier tranche: Wilder ATR(22) stop at highest high (22) minus 6 × ATR, ratcheted
- [ ] Reference results reproduced: a set of previously calculated strategy runs (fixed symbols, fixed window) match the platform's output exactly, validating the port
- [ ] Result marts: `fct_backtest_runs`, `fct_backtest_trades`, `fct_backtest_equity_curve`
- [ ] Parameter sweeps: alpha threshold, cool-off length, and tranche sizes vary systematically, with results comparable in a single SQL query
- [ ] Lambda + API Gateway endpoints: `GET /prices/{symbol}`, `GET /indicators/{symbol}`, `POST /backtests`, `GET /backtests/{id}`, `GET /backtests/{id}/equity-curve`
- [ ] Lambda execution role limited to the Redshift, S3, and Secrets Manager access it needs

**Milestone:** A full backtest runs end-to-end through the API. Reference results match. A parameter sweep of at least nine combinations completes and can be compared in one query.

---

## Iteration 6 — API consumers & archiving (Glacier)

**Goal:** PearEquity's data is reliably consumable by downstream systems through a stable, documented API, and old raw data is archived cheaply and automatically.

*Glacier archiving is added in this iteration — its trigger (raw landing data older than 90 days) is met by the accumulated pulls from Iterations 1–5.*

- [ ] API contract published (OpenAPI specification): price history with 200-day average and Chandelier overlays, momentum data, and backtest equity curves versus the benchmark
- [ ] Sample API payloads and an example consumer committed under `examples/`, so downstream systems can develop against realistic data without a live API
- [ ] S3 lifecycle rules live: `raw/` data moves to Glacier Flexible after 90 days and Deep Archive after 365 days
- [ ] Archive restore drill: one archived object restored and verified, with the process and timing documented
- [ ] Glue decision recorded: if a workload has outgrown DuckDB/dbt (see the trigger in STACK.md), a Glue job and Data Catalog are added for the curated zone; otherwise the deferral and its reason are written in the decision log

**Milestone:** The example consumer displays a symbol chart and a backtest comparison served by the PearEquity API. The restore drill is complete. The Glue decision is documented either way.

---

## Iteration 7 — Hardening & documentation

**Goal:** The platform is reliable to run, and a new reader can reproduce a result without help.

- [ ] Demo mode: a small sample dataset, committed to the repository, that runs Iterations 1–2 end-to-end with no AWS account
- [ ] Runbooks: daily operations, backfills, secret rotation, Redshift pause/resume, and responding to a bad source data pull
- [ ] Full documentation pass: README with architecture diagram and actual running costs, DataGrip query library, API reference
- [ ] Reliability pass: pipeline idempotency re-verified, quality gates reviewed, budget alerts tested
- [ ] Technology review: each "when necessary" tool re-checked against its trigger — adopted, still deferred, or removed — with the outcome recorded in the decision log

**Milestone:** A fresh clone, in demo mode, reproduces one reference backtest result by following only the written documentation.

---

## Standing guardrails

- **Cost:** AWS Budget alerts at $1 / $5 / $10. Any alert is a stop-and-check event. No continuously billed infrastructure (provisioned clusters, managed orchestration services, NAT Gateways) is introduced without a written decision.
- **Data integrity:** Raw data is never modified after landing. Every mart can be rebuilt from raw. Every backtest result records the data snapshot and parameters that produced it.
- **Security:** No secrets, credentials, or access keys in the repository, ever. All AWS access is through IAM roles with temporary credentials.
