# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

Planning is complete. No code has been written yet. The canonical reference for all architecture decisions is [architecture.md](architecture.md). The current next step is **Phase 1 — Infrastructure Skeleton**.

**Tech stack is fixed:** Airflow + PostgreSQL + dbt + FastAPI + Prometheus + Grafana, all on Docker Desktop (WSL2). Do not suggest replacing any core component.

## Common Commands

```bash
# Start the full stack
docker compose up -d

# Tear down and wipe all volumes (full reset)
docker compose down -v

# Check service health
docker compose ps

# Generate an Airflow Fernet key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# dbt (run from inside airflow container or with dbt installed locally)
dbt run --select staging+
dbt test --select staging+
dbt seed                    # loads seeds/alert_thresholds.csv into meta.alert_thresholds
dbt docs generate

# Run API tests
cd api && pytest tests/

# Backfill (once scripts/ is written)
bash scripts/backfill.sh <start_date> <end_date>
```

## Service Ports

| Service | Port |
|---|---|
| Airflow webserver | localhost:8080 |
| FastAPI | localhost:8000 |
| Grafana | localhost:3000 |
| Prometheus | localhost:9090 |
| postgres-market (host access) | localhost:5433 |
| statsd-exporter (metrics) | localhost:9102 |

## Architecture

### Data Flow

```
CoinGecko API (hourly)
  → Airflow DAG: http_sensor → extract → validate (GE) → branch → load → dbt → alerts → sla_check → log
  → raw.market_snapshots (PostgreSQL)
  → dbt: staging → intermediate → marts
  → FastAPI (read-only from marts)
  → Grafana (business panels from PostgreSQL, ops panels from Prometheus)
  → Prometheus (pipeline metrics via StatsD exporter)
```

### Schema Layer Rules

| Schema | Written by | Read by |
|---|---|---|
| raw | Airflow only | dbt only |
| staging | dbt | dbt |
| marts | dbt | FastAPI, Grafana |
| meta | manual / dbt seed | Airflow alert task |

FastAPI **never** touches the raw or staging schemas. Consumers are insulated from raw schema changes.

### Two PostgreSQL Instances

- `postgres-airflow` — Airflow internal metadata only. Isolated to prevent Airflow's writes from polluting query plans on the business DB.
- `postgres-market` — All business data. Externally accessible on port 5433 (internal port remains 5432).

### Airflow DAG Structure

Business logic lives in `airflow/tasks/` as pure Python modules (extract, validate, load, alerts, sla, pipeline_log), not inline in the DAG file. This makes tasks unit-testable without Airflow.

Key patterns:
- **Idempotency:** UPSERT with `ON CONFLICT (coin_id, snapshot_timestamp) DO UPDATE`
- **Branching:** `BranchPythonOperator` post-validation routes to `load_market_data` or `skip_and_alert`
- **Final task:** `log_pipeline_run` uses `TriggerRule.NONE_FAILED` so it always runs regardless of branch
- **SLA:** Latest `snapshot_timestamp` must not be older than 90 minutes at time of `sla_check`

### dbt Model Structure

```
models/
  staging/    stg_market_snapshots.sql       -- 1:1 rename/cast of raw source
  intermediate/ int_coin_metrics.sql         -- rolling 7d avg, volatility, volume_spike_ratio
  marts/      mart_coin_summary.sql          -- denormalised, consumed by API + Grafana
              mart_alerts.sql               -- alert view with coin metadata
```

### FastAPI

- SQLAlchemy Core (not ORM) — SQL stays explicit
- Pydantic response models on every endpoint
- Async handlers with asyncpg connection pool
- `X-API-Key` header auth via `api/dependencies.py`
- Reads only from `marts` schema

### Key Data Model Decisions

- `price_usd` is `NUMERIC(20,8)`, not FLOAT — avoids rounding errors in financial aggregations
- `snapshot_timestamp` is always UTC (`TIMESTAMPTZ`), distinct from `ingested_at`
- `raw.market_snapshots` is range-partitioned by month on `snapshot_timestamp`
- Alert thresholds live in `meta.alert_thresholds` (DB), not in DAG code — threshold changes require no redeployment

### Docker Compose Patterns

- All services on a single user-defined bridge network (`platform_net`) for DNS-based service discovery
- `depends_on` with `condition: service_healthy` throughout — prevents race conditions on startup
- `airflow-init` uses `condition: service_completed_successfully` (one-shot migration runner, not a long-lived service)
- Named volumes for stateful data (DB files, Grafana state, logs); bind mounts for code and config

### Environment Configuration

All connection strings and credentials are injected via environment variables. Copy `.env.example` to `.env` before running. Required keys are documented in architecture.md §11 and in `.env.example`. Nothing is hardcoded.

## Implementation Phases

| Phase | Goal |
|---|---|
| 1 | All containers healthy (infrastructure skeleton) |
| 2 | Raw ingestion DAG working (extract → validate → load) |
| 3 | dbt models + tests passing |
| 4 | Alerts + SLA tracking |
| 5 | Grafana dashboards live |
| 6 | FastAPI endpoints live |
| 7 | Portfolio-ready (README, hardening, cold-start verification) |
| 8 | Cloud migration (optional, per §8.3) |

Never begin a phase until the previous phase's exit criteria are verified. See architecture.md §12 for detailed tasks and exit criteria per phase.

## Working Style

The user is actively learning data engineering. Default to this interaction pattern at all times:

- **No full file dumps — give focused snippets.** Provide only the relevant function, block, or section with enough surrounding context to place it correctly. The user types the full file themselves. This forces engagement with the code rather than copy-paste.
- **Never create, edit, or delete files in the codebase unless the user explicitly asks you to.** "Unless absolutely necessary" means a broken tool call or a critical correction the user cannot make themselves.
- **Chunk the work.** Break each phase into logical steps. Deliver one chunk at a time and wait for the user to confirm before moving to the next.
- **Explain the why — including the field context.** For every non-obvious decision: (1) state the reason for the specific choice, (2) name the data engineering pattern it represents, and (3) briefly note where this pattern appears in production or interviews. The goal is to build understanding of the field, not just this project.
- **Teach concepts before code.** Before giving any snippet, briefly explain what the component is, what problem it solves, and how it fits into the overall data flow. Then show the code.
