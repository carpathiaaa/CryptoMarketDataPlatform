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

## Phase 2 — Raw Ingestion DAG ⬜
**Goal:** Airflow DAG extracts from CoinGecko and loads into `raw.market_snapshots`. Idempotent.

*Chunks will be defined when Phase 1 Chunk 8 is complete.*

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
