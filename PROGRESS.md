# Project Progress

## How This File Works
- Updated by Claude at the **start of each new chat session**
- A chunk's status only changes to ✅ after both user and Claude confirm all checklist items pass
- Current phase and next phase are fully detailed; all others are stubs until their turn

## Legend
| Symbol | Meaning |
|---|---|
| ✅ | Complete — all checklist items confirmed |
| 🔄 | In Progress — instructions given, not yet confirmed |
| ⬜ | Pending — not started |

---

## Phase 1 — Infrastructure Skeleton
**Goal:** Every container starts, stays healthy, and can talk to the containers it depends on. No pipeline logic yet.

---

### Chunk 1 — Directory Scaffold ✅
**Files:** `.gitignore`, full directory tree, `.gitkeep` placeholders

| # | Check | Pass? |
|---|---|---|
| 1 | `.gitignore` covers `.env`, `__pycache__`, `.venv/`, `dbt/target/`, `dbt/logs/`, `airflow/logs` | ✅ |
| 2 | All directories from §10 of architecture.md exist | ✅ |
| 3 | `.gitkeep` files present in empty dirs so git tracks them | ✅ |

---

### Chunk 2 — Environment Files ✅
**Files:** `.env.example`, `.env`

| # | Check | Pass? |
|---|---|---|
| 1 | `.env.example` has all required keys with empty values (safe to commit) | ✅ |
| 2 | `.env` has all keys filled: passwords, Fernet key, secret key, API keys, CoinGecko key | ✅ |
| 3 | `.env` is NOT tracked by git (`git status` does not show it) | ✅ |

---

### Chunk 3 — PostgreSQL ✅
**Files:** `postgres/Dockerfile`, `postgres/init/01_schemas.sql`, `02_tables.sql`, `03_partitions.sql`, `04_indexes.sql`

| # | Check | Pass? |
|---|---|---|
| 1 | `postgres/Dockerfile` extends `postgres:16` and installs `postgresql-16-partman` via apt | ✅ |
| 2 | `01_schemas.sql` creates `raw`, `staging`, `marts`, `meta` schemas and `pg_partman` extension in `partman` schema | ✅ |
| 3 | `02_tables.sql` creates all 5 tables with correct column types (`NUMERIC(20,8)`, `TIMESTAMPTZ`) | ✅ |
| 4 | `02_tables.sql` calls `partman.create_parent()` for `raw.market_snapshots` after table creation | ✅ |
| 5 | `03_partitions.sql` exists as a documentation-only file (no executable SQL) | ✅ |
| 6 | `04_indexes.sql` defines all 6 indexes across `raw.market_snapshots`, `raw.pipeline_runs`, `raw.alerts` | ✅ |

---

### Chunk 4 — Airflow Dockerfile 🔄
**Files:** `airflow/Dockerfile`, `airflow/requirements.txt`

| # | Check | Pass? |
|---|---|---|
| 1 | `airflow/Dockerfile` extends `apache/airflow:2.x` | ✅ |
| 2 | `airflow/requirements.txt` includes `great-expectations`, `psycopg2-binary`, `requests`, `statsd` | ✅ |
| 3 | Image builds without error: `docker compose build airflow-scheduler` | ⬜ |

---

### Chunk 5 — API Dockerfile 🔄
**Files:** `api/Dockerfile`, `api/requirements.txt`

| # | Check | Pass? |
|---|---|---|
| 1 | `api/Dockerfile` uses a Python slim base image | ✅ |
| 2 | `api/requirements.txt` includes `fastapi`, `uvicorn`, `asyncpg`, `sqlalchemy`, `pydantic` | ✅ |
| 3 | Image builds without error: `docker compose build api` | ⬜ |

---

### Chunk 6 — Monitoring Config ✅
**Files:** `prometheus/prometheus.yml`, `grafana/provisioning/datasources/prometheus.yml`, `grafana/provisioning/datasources/postgres.yml`, `grafana/provisioning/dashboards/dashboard.yml`

| # | Check | Pass? |
|---|---|---|
| 1 | `prometheus/prometheus.yml` has scrape target `statsd-exporter:9102` | ✅ |
| 2 | Grafana Prometheus datasource YAML is present and correctly formatted | ✅ |
| 3 | Grafana PostgreSQL datasource YAML points to `postgres-market:5432` with correct credentials | ✅ |
| 4 | Grafana dashboards provisioning YAML points to `/var/lib/grafana/dashboards` | ✅ |

---

### Chunk 7 — docker-compose.yml ✅
**Files:** `docker-compose.yml`

| # | Check | Pass? |
|---|---|---|
| 1 | All 9 services defined: `postgres-airflow`, `postgres-market`, `airflow-init`, `airflow-scheduler`, `airflow-webserver`, `api`, `statsd-exporter`, `prometheus`, `grafana` | ✅ |
| 2 | Every service uses `depends_on` with `condition: service_healthy` or `service_completed_successfully` as appropriate | ✅ |
| 3 | All named volumes declared at the bottom of the file | ✅ |
| 4 | `platform_net` bridge network declared and assigned to all services | ✅ |
| 5 | No hardcoded credentials — all sensitive values reference `.env` variables | ✅ |

---

### Chunk 8 — First Boot Verification ✅
**Goal:** Phase 1 exit criteria met

| # | Check | Pass? |
|---|---|---|
| 1 | `docker compose up -d` completes without error | ✅ |
| 2 | `docker compose ps` shows all 9 services as `healthy` | ✅ |
| 3 | Can connect to `postgres-market` on port 5433 and see all 4 schemas and 5 tables | ✅ |
| 4 | Airflow webserver reachable at `localhost:8080` and login works | ✅ |
| 5 | Grafana reachable at `localhost:3000` with both datasources (Prometheus + PostgreSQL) showing green | ✅ |

---

## Phase 2 — Raw Ingestion DAG
**Goal:** Airflow DAG extracts from CoinGecko and loads into `raw.market_snapshots`. Idempotent.

---

### Chunk 1 — extract.py ✅
**File:** `airflow/tasks/extract.py`

| # | Check | Pass? |
|---|---|---|
| 1 | `fetch_top20()` calls CoinGecko `/coins/markets` with correct params (vs_currency, per_page, page) | ✅ |
| 2 | Request includes `X-CG-Demo-Api-Key` header from env var | ✅ |
| 3 | Function raises an exception (not silently returns) on non-200 response | ✅ |
| 4 | Returns a list of dicts — only the fields needed for `raw.market_snapshots` | ✅ |
| 5 | `snapshot_timestamp` is set to the Airflow `logical_date` (not `datetime.now()`) | ✅ |

---

### Chunk 2 — Great Expectations Setup + validate.py ✅
**Files:** `airflow/great_expectations/` (GE init + suite), `airflow/tasks/validate.py`
**Note:** GE version is 1.13.0. Use `context.suites.get()`, `context.data_sources.add_or_update_pandas()`, `context.suites.update()`. No `init` CLI needed — use `gx.get_context(mode="file", project_root_dir=...)`.

| # | Check | Pass? |
|---|---|---|
| 1 | GE context initialised via `gx.get_context(mode="file")` on the host (GE 1.x — no `init` CLI needed) | ✅ |
| 2 | Expectation suite created with: not_null on coin_id + price_usd, value range on price_usd > 0 | ✅ |
| 3 | `validate_snapshot(records)` uses correct GE 1.x API and returns pass/fail bool | ✅ |
| 4 | Validation result written to GE's local store automatically by file-based context | ✅ |

---

### Chunk 3 — load.py ✅
**File:** `airflow/tasks/load.py`

| # | Check | Pass? |
|---|---|---|
| 1 | `load_records(records)` opens a connection using individual env vars (MARKET_DB_USER, MARKET_DB_PASSWORD, MARKET_DB_NAME) | ✅ |
| 2 | Uses `INSERT ... ON CONFLICT (coin_id, snapshot_timestamp) DO UPDATE` — idempotent | ✅ |
| 3 | Returns row count inserted/updated | ✅ |
| 4 | Re-running with same data does not increase row count | ⬜ |

---

### Chunk 4 — pipeline_log.py ✅
**File:** `airflow/tasks/pipeline_log.py`

| # | Check | Pass? |
|---|---|---|
| 1 | `log_pipeline_run(execution_date, status, rows_inserted, error_message)` writes one row to `raw.pipeline_runs` | ✅ |
| 2 | `status` is one of: `SUCCESS`, `QUALITY_FAIL`, `ERROR` | ✅ |
| 3 | Function handles `None` for `error_message` (nullable column) | ✅ |

---

### Chunk 5 — market_ingestion.py (DAG) ⬜
**File:** `airflow/dags/market_ingestion.py`

| # | Check | Pass? |
|---|---|---|
| 1 | DAG uses `schedule_interval='@hourly'` and `catchup=False` | ⬜ |
| 2 | `HttpSensor` gates the extract — DAG waits if API is unreachable | ⬜ |
| 3 | `BranchPythonOperator` routes to `load_market_data` or `skip_and_alert` based on validation result | ⬜ |
| 4 | `skip_and_alert` writes `QUALITY_FAIL` to `pipeline_runs` | ⬜ |
| 5 | `log_pipeline_run` task uses `TriggerRule.NONE_FAILED` — runs on both branches | ⬜ |
| 6 | All business logic is imported from `airflow/tasks/` — no inline logic in DAG file | ⬜ |

---

### Chunk 6 — End-to-End Verification ⬜
**Goal:** Phase 2 exit criteria met

| # | Check | Pass? |
|---|---|---|
| 1 | DAG triggered manually — completes successfully end-to-end | ⬜ |
| 2 | `raw.market_snapshots` has exactly 20 rows after one run | ⬜ |
| 3 | Re-triggering the same `execution_date` does not duplicate rows | ⬜ |
| 4 | Force a GE validation failure — `skip_and_alert` branch fires | ⬜ |
| 5 | `raw.pipeline_runs` has a record for every run with correct status | ⬜ |

---

## Phase 3 — dbt Transformation Layer ⬜ (stub)
*Chunks will be defined when Phase 2 is complete.*

## Phase 4 — Alerts + SLA ⬜ (stub)
*Chunks will be defined when Phase 3 is complete.*

## Phase 5 — Observability ⬜ (stub)
*Chunks will be defined when Phase 4 is complete.*

## Phase 6 — FastAPI ⬜ (stub)
*Chunks will be defined when Phase 5 is complete.*

## Phase 7 — Hardening + Review ⬜ (stub)
*Chunks will be defined when Phase 6 is complete.*

## Phase 8 — Cloud Migration ⬜ (stub, optional)
*Chunks will be defined when Phase 7 is complete.*
