# Crypto Market Data Platform — Architecture v2.0

## Session Context

> **For new sessions:** This is the canonical architecture document for a containerised crypto market data pipeline. The owner is a junior DE/AE targeting data engineering roles. Decisions prioritise learning depth over simplicity. Tech stack is fixed: Airflow + PostgreSQL + dbt + FastAPI + Prometheus + Grafana, all on Docker Desktop (WSL2). Do not suggest replacing core components. Current phase: planning complete — architecture, directory structure, docker-compose, and roadmap all defined. No code written yet. Next step: begin Phase 1 (infrastructure skeleton).
>
> **Development location:** The repo must live inside the WSL2 filesystem (e.g. `~/projects/`), not on the Windows filesystem (`C:\`). Docker Desktop bind mounts from WSL2 use a native socket and are significantly faster than the 9P bridge used for Windows paths. Airflow DAG scanning and dbt file access are both sensitive to this.
>
> **Document structure:** §1 Objective · §2 Architecture · §3 Data Model · §4 dbt · §5 Airflow DAG · §6 Observability · §7 FastAPI · §8 Cloud Path · §9 Non-Goals · §10 Directory Structure · §11 Docker Compose Layout

---

## 1. Objective

Build a containerised, orchestrated, and observable market data ingestion platform that demonstrates production-grade engineering patterns at a manageable solo scale.

**Target roles:** Data Engineer (ETL/pipelines), Analytics Engineer (dbt, metrics)  
**Target skills:** Airflow orchestration patterns, storage/query optimisation, cloud deployment readiness

### Capability Map

| Capability           | Implementation                                | Role Signal        |
| -------------------- | --------------------------------------------- | ------------------ |
| Orchestration        | Airflow DAG with sensor, branching, callbacks | Data Engineer      |
| Idempotent ETL       | UPSERT strategy, parameterised backfill       | Data Engineer      |
| Transformation layer | dbt staging → intermediate → marts            | Analytics Engineer |
| Storage design       | Partitioned tables, indexing strategy         | Data Engineer      |
| Data quality         | Great Expectations + dbt tests                | Both               |
| Observability        | Prometheus + StatsD + Grafana                 | Data Engineer      |
| Cloud-readiness      | Env-var config, phased migration plan         | Both               |
| API design           | FastAPI read-only over mart tables            | Data Engineer      |

---

## 2. Architecture

### 2.1 Components

| Component          | Technology                         | Role                                                               |
| ------------------ | ---------------------------------- | ------------------------------------------------------------------ |
| Orchestrator       | Apache Airflow 2.x (LocalExecutor) | Schedules and monitors all pipeline tasks                          |
| Raw store          | PostgreSQL 16                      | Partitioned market_snapshots; append-only raw layer                |
| Airflow metadata   | PostgreSQL 16 (separate instance)  | Isolated from business data                                        |
| Transform layer    | dbt Core                           | staging → intermediate → mart models + tests                       |
| API layer          | FastAPI                            | Read-only endpoints over mart tables only                          |
| Metrics collection | Prometheus + StatsD exporter       | Pipeline run durations, row counts, lag                            |
| Dashboards         | Grafana                            | Ops panels (Prometheus source) + business panels (Postgres source) |

**Why two PostgreSQL instances:** Mirrors production where orchestrators use managed metadata stores fully decoupled from the data warehouse. Prevents Airflow's internal writes from polluting query plans on the business DB.

**Why LocalExecutor:** Allows parallel task execution. More realistic than SequentialExecutor. Avoids Celery complexity while the focus is on pipeline patterns, not infrastructure.

### 2.2 Logical Data Flow

```
CoinGecko API
  → Airflow (extract → validate → branch → load)
  → raw.market_snapshots (PostgreSQL)
  → dbt (staging → intermediate → marts)
  → marts.mart_coin_summary
      → FastAPI (read-only)
      → Grafana (business panels)
  → Prometheus (pipeline metrics)
      → Grafana (ops panels)
```

### 2.3 Layer Access Rules

| Schema  | Tables                                                | Written By   | Read By            |
| ------- | ----------------------------------------------------- | ------------ | ------------------ |
| raw     | market_snapshots, pipeline_runs, sla_breaches, alerts | Airflow only | dbt only           |
| staging | stg_market_snapshots                                  | dbt          | dbt                |
| marts   | mart_coin_summary, mart_alerts                        | dbt          | FastAPI, Grafana   |
| meta    | alert_thresholds                                      | Manual / API | Airflow alert task |

**Why schema separation:** Mirrors Snowflake/BigQuery layer conventions. FastAPI never touches raw schema — consumers are insulated from raw schema changes. This is a pattern worth being able to explain in interviews.

---

## 3. Data Model

### 3.1 raw.market_snapshots

Partitioned by `RANGE` on `snapshot_timestamp`. One partition per month (e.g. `market_snapshots_2026_03`). UPSERT on load uses `ON CONFLICT (coin_id, snapshot_timestamp) DO UPDATE`.

| Column               | Type          | Notes                                                                                    |
| -------------------- | ------------- | ---------------------------------------------------------------------------------------- |
| coin_id              | TEXT          | CoinGecko slug. Part of unique key.                                                      |
| symbol               | TEXT          | e.g. btc, eth                                                                            |
| price_usd            | NUMERIC(20,8) | **Not FLOAT.** Avoids rounding errors in financial aggregations. Interviewable decision. |
| market_cap_usd       | NUMERIC(30,2) |                                                                                          |
| volume_24h_usd       | NUMERIC(30,2) |                                                                                          |
| price_change_pct_24h | NUMERIC(10,4) |                                                                                          |
| snapshot_timestamp   | TIMESTAMPTZ   | Partition key. Always UTC. Part of unique key.                                           |
| ingested_at          | TIMESTAMPTZ   | Wall-clock insert time. Distinct from snapshot_timestamp.                                |
| source_version       | TEXT          | API version string. Aids debugging schema drift.                                         |

**Estimated volume:** 20 coins × 24 runs/day = 480 rows/day → ~175k rows/year → <100 MB/year including indexes. Lightweight but sufficient to simulate partitioning behaviour.

### 3.2 raw.alerts

| Column             | Type        | Notes                                                  |
| ------------------ | ----------- | ------------------------------------------------------ |
| alert_id           | SERIAL PK   |                                                        |
| coin_id            | TEXT        |                                                        |
| snapshot_timestamp | TIMESTAMPTZ |                                                        |
| alert_type         | TEXT        | e.g. price_spike, volume_anomaly                       |
| severity           | TEXT        | LOW / MEDIUM / HIGH                                    |
| metric_value       | NUMERIC     | Actual value that triggered alert                      |
| threshold_value    | NUMERIC     | Value from meta.alert_thresholds at time of evaluation |
| created_at         | TIMESTAMPTZ |                                                        |

### 3.3 raw.pipeline_runs

| Column         | Type        | Notes                                     |
| -------------- | ----------- | ----------------------------------------- |
| run_id         | SERIAL PK   |                                           |
| execution_date | TIMESTAMPTZ | Airflow execution_date                    |
| start_time     | TIMESTAMPTZ |                                           |
| end_time       | TIMESTAMPTZ |                                           |
| status         | TEXT        | SUCCESS / QUALITY_FAIL / SLA_FAIL / ERROR |
| rows_inserted  | INT         |                                           |
| error_message  | TEXT        | Nullable                                  |
| sla_status     | TEXT        | OK / FAILED                               |

### 3.4 raw.sla_breaches

| Column                  | Type        | Notes |
| ----------------------- | ----------- | ----- |
| breach_id               | SERIAL PK   |       |
| expected_timestamp      | TIMESTAMPTZ |       |
| actual_latest_timestamp | TIMESTAMPTZ |       |
| delay_minutes           | NUMERIC     |       |
| detected_at             | TIMESTAMPTZ |       |

### 3.5 meta.alert_thresholds

Stored in DB, not in DAG code. Threshold changes require no redeployment.

| Column              | Type        | Notes                                             |
| ------------------- | ----------- | ------------------------------------------------- |
| metric_name         | TEXT        | e.g. price_change_pct_24h, volume_spike_ratio     |
| severity            | TEXT        | LOW / MEDIUM / HIGH                               |
| threshold_value     | NUMERIC     |                                                   |
| comparison_operator | TEXT        | `>` / `<` / `>=` — evaluated in Python alert task |
| updated_at          | TIMESTAMPTZ | Audit field                                       |

### 3.6 Indexing Strategy

- `(coin_id, snapshot_timestamp DESC)` — point lookups for a single coin's history
- `(snapshot_timestamp DESC)` — recent-N queries across all coins
- Partial index on `raw.alerts WHERE severity = 'HIGH'` — dashboard alert feed query

---

## 4. dbt Transformation Layer

### 4.1 Why dbt (not Python transforms)

The original design computed derived metrics in Python. dbt replaces this because: it is the dominant transformation tool in DE/AE stacks today; it enforces SQL-native lineage; and it adds a test layer that makes data quality a first-class concern. Being able to contrast "imperative Python transforms" vs "declarative dbt models" is a strong interview signal.

### 4.2 Model Structure

```
models/
  staging/
    stg_market_snapshots.sql   -- rename, cast, light clean. 1:1 with source table.
  intermediate/
    int_coin_metrics.sql       -- rolling 7d avg, volatility, volume_spike_ratio via window functions
  marts/
    mart_coin_summary.sql      -- denormalised, business-ready. consumed by API + Grafana.
    mart_alerts.sql            -- joined alert view with coin metadata
```

### 4.3 dbt Tests

| Layer        | Tests                                                                       |
| ------------ | --------------------------------------------------------------------------- |
| Staging      | not_null(coin_id, snapshot_timestamp), unique(coin_id + snapshot_timestamp) |
| Intermediate | accepted_values(severity), range checks on price and volume                 |
| Mart         | Custom: market_dominance_pct sums to ~100 across any snapshot               |

### 4.4 dbt in the DAG

dbt is triggered via `BashOperator` after each successful load:

```
load_market_data
  → run_dbt_models     (dbt run --select staging+)
  → run_dbt_tests      (dbt test --select staging+)
      on failure → on_failure_callback writes QUALITY_FAIL to pipeline_runs
                 → downstream tasks skipped
```

---

## 5. Airflow DAG Design

### 5.1 Schedule

Hourly. Backfill limited to last 30 days. `execution_date` is the idempotency key.

### 5.2 Full Task Graph

```
http_sensor
  → extract_top20
  → validate_snapshot        (Great Expectations checkpoint)
  → branch_on_validation     (BranchPythonOperator)
      ├─ [pass] load_market_data
      │    → run_dbt_models
      │    → emit_dbt_metrics    (reads dbt/target/run_results.json → StatsD)
      │    → run_dbt_tests
      │    → generate_alerts
      │    → sla_check
      └─ [fail] skip_and_alert
  → log_pipeline_run         (TriggerRule.NONE_FAILED — always runs)
```

### 5.3 Key Airflow Patterns

| Pattern                 | Where Used                 | Why It Matters                                              |
| ----------------------- | -------------------------- | ----------------------------------------------------------- |
| HttpSensor              | Pre-extract gate           | Prevents wasted retries on API downtime                     |
| XCom                    | extract → validate handoff | Understand size limits; small payloads only                 |
| BranchPythonOperator    | Post-validation routing    | Common interview topic; understand TriggerRule implications |
| on_failure_callback     | dbt test failure           | Alerting without external systems                           |
| SLA miss callback       | Hourly freshness check     | Airflow-native SLA enforcement                              |
| TriggerRule.NONE_FAILED | log_pipeline_run           | Final task always runs regardless of branch taken           |

### 5.4 Idempotency

- **Load:** UPSERT with `ON CONFLICT (coin_id, snapshot_timestamp) DO UPDATE`
- **dbt:** Models are `CREATE OR REPLACE`; tests are read-only
- Re-running any DAG execution for a given `execution_date` is always safe

### 5.5 SLA Definition

Rule: latest `snapshot_timestamp` must not be older than 90 minutes at time of `sla_check`.

On breach:

1. Insert into `raw.sla_breaches`
2. Set `pipeline_runs.sla_status = 'FAILED'`
3. Emit `data_freshness_lag_minutes` metric to Prometheus
4. Airflow native SLA miss callback fires

---

## 6. Observability

### 6.1 Metrics (Prometheus via StatsD exporter)

| Metric                         | Type                           | Source Task                                |
| ------------------------------ | ------------------------------ | ------------------------------------------ |
| pipeline_rows_inserted_total   | Counter                        | log_pipeline_run                           |
| pipeline_run_duration_seconds  | Histogram                      | log_pipeline_run                           |
| data_freshness_lag_minutes     | Gauge                          | sla_check                                  |
| dbt_model_run_duration_seconds | Histogram                      | run_dbt_models (parsed from dbt artifacts) |
| alerts_generated_total         | Counter (labelled by severity) | generate_alerts                            |
| validation_failures_total      | Counter                        | validate_snapshot                          |

### 6.2 Grafana Panels

| Panel                      | Data Source | Notes                                           |
| -------------------------- | ----------- | ----------------------------------------------- |
| Data freshness gauge       | Prometheus  | Red at 90 min, yellow at 75 min                 |
| Pipeline run status (24h)  | Prometheus  | Stacked: SUCCESS / QUALITY_FAIL / SLA_FAIL      |
| BTC price + 7d rolling avg | PostgreSQL  | From mart_coin_summary                          |
| Top 20 market cap table    | PostgreSQL  | Sorted by market cap                            |
| Volume spike heatmap       | PostgreSQL  | volume_spike_ratio across coins, hourly buckets |
| Alert feed                 | PostgreSQL  | Recent HIGH/MEDIUM alerts, filterable by coin   |
| dbt model run duration     | Prometheus  | Detect model regressions over time              |

---

## 7. FastAPI Service Layer

Reads exclusively from `marts` schema. Never touches `raw` or `staging`.

### 7.1 Endpoints

| Method | Path                     | Description                                          |
| ------ | ------------------------ | ---------------------------------------------------- |
| GET    | /health                  | DB connectivity, latest snapshot age, dbt run status |
| GET    | /coins/latest            | All 20 coins at most recent snapshot                 |
| GET    | /coins/{coin_id}/history | Paginated time series. Supports `?from=` and `?to=`  |
| GET    | /alerts                  | Recent alerts. Supports `?severity=` and `?coin_id=` |
| GET    | /pipeline/runs           | Last N pipeline runs with SLA status                 |
| GET    | /metrics/dominance       | Market dominance % from latest mart snapshot         |

### 7.2 Implementation Notes

- SQLAlchemy Core (not ORM) — keeps SQL explicit and auditable
- Pydantic response models on every endpoint — enforces contract, auto-generates OpenAPI docs
- Async handlers with asyncpg connection pool
- Simple `X-API-Key` header check — introduces auth concept without full OAuth complexity

---

## 8. Cloud Deployment Path

### 8.1 Local-to-Cloud Mapping

| Local (Docker)          | AWS                      | GCP                       |
| ----------------------- | ------------------------ | ------------------------- |
| PostgreSQL container    | RDS (PostgreSQL)         | Cloud SQL                 |
| Airflow (LocalExecutor) | MWAA                     | Cloud Composer            |
| FastAPI container       | ECS Fargate / App Runner | Cloud Run                 |
| Grafana container       | Managed Grafana          | Cloud Monitoring          |
| dbt Core (CLI)          | dbt Cloud / ECS task     | dbt Cloud / Cloud Run job |
| Prometheus              | CloudWatch Metrics       | Cloud Monitoring          |

### 8.2 Configuration Portability

All connection strings, credentials, and env-specific settings are injected via environment variables. No hostnames, passwords, or schema names are hardcoded. A `.env.example` documents all required variables.

### 8.3 Phased Migration

1. **Phase 1:** Move PostgreSQL to free-tier managed service (Neon, Supabase). Keep everything else local.
2. **Phase 2:** Deploy FastAPI to Render or Railway. Point at managed DB.
3. **Phase 3:** Move Airflow to a small cloud VM with CeleryExecutor + Redis. Avoid managed Airflow — it's expensive.
4. **Phase 4:** Add Terraform for the managed DB and networking. Introduces IaC without full complexity.

---

## 9. Non-Goals

| Out of Scope                          | Reasoning                                                                  |
| ------------------------------------- | -------------------------------------------------------------------------- |
| Real-time streaming                   | Kafka/Flink complexity would overwhelm the orchestration and storage goals |
| Historical backfill > 30 days         | Unbounded backfill adds risk without proportional learning value           |
| External notifications (email, Slack) | Better as a Phase 2 addition                                               |
| Frontend application                  | Grafana fulfils the visualisation need                                     |
| Write endpoints in API                | Mutations belong to the pipeline, not the API                              |
| ML / predictive features              | Out of scope for a DE/AE-targeted project                                  |

---

## 10. Directory Structure

Single monorepo. `dbt/` and `airflow/` are top-level siblings — separate concerns, shared repo. Every directory that starts empty has a comment explaining what belongs there so the structure is self-documenting from day one.

```
crypto-market-platform/
│
├── .env.example                  # All required env vars documented. Never commit .env
├── .gitignore
├── docker-compose.yml            # Defines all services; reads from .env
├── README.md                     # Project overview, setup steps, architecture diagram link
│
├── airflow/                      # Everything the Airflow container needs
│   ├── Dockerfile                # Extends apache/airflow base; installs requirements
│   ├── requirements.txt          # great-expectations, psycopg2, requests, statsd
│   │
│   ├── dags/
│   │   └── market_ingestion.py   # The single DAG — all tasks defined here
│   │
│   ├── plugins/                  # Custom Airflow operators/hooks if needed later
│   │
│   ├── tasks/                    # Pure Python modules imported by the DAG
│   │   ├── __init__.py
│   │   ├── extract.py            # CoinGecko API calls; includes X-CG-Demo-Api-Key header
│   │   ├── validate.py           # Great Expectations checkpoint logic
│   │   ├── load.py               # UPSERT into raw.market_snapshots
│   │   ├── dbt_metrics.py        # Reads dbt/target/run_results.json; emits model durations to StatsD
│   │   ├── alerts.py             # Reads meta.alert_thresholds, writes raw.alerts
│   │   ├── sla.py                # Freshness check, writes raw.sla_breaches
│   │   └── pipeline_log.py       # Writes final status to raw.pipeline_runs
│   │
│   ├── great_expectations/       # GE project root — init'd with `great_expectations init`
│   │   ├── great_expectations.yml
│   │   ├── expectations/         # Expectation suites (one per validated dataset)
│   │   └── checkpoints/          # Checkpoint configs called from validate.py
│   │
│   └── config/
│       └── airflow.cfg           # Airflow config overrides (executor, smtp off, etc.)
│
├── dbt/                          # Standalone dbt project
│   ├── dbt_project.yml           # Project name, model paths, target schema config
│   ├── profiles.yml              # Connection profiles — reads from env vars, not hardcoded
│   ├── packages.yml              # dbt-utils and any other packages
│   │
│   ├── models/
│   │   ├── staging/
│   │   │   ├── schema.yml        # Source definitions + staging model tests
│   │   │   └── stg_market_snapshots.sql
│   │   ├── intermediate/
│   │   │   ├── schema.yml        # Intermediate model tests
│   │   │   └── int_coin_metrics.sql
│   │   └── marts/
│   │       ├── schema.yml        # Mart model tests + column descriptions
│   │       ├── mart_coin_summary.sql
│   │       └── mart_alerts.sql
│   │
│   ├── tests/                    # Custom singular tests (e.g. dominance sums to 100)
│   │   └── assert_dominance_sums_to_100.sql
│   │
│   ├── macros/                   # Reusable Jinja macros (e.g. generate_schema_name)
│   │
│   ├── seeds/                    # Static reference data loaded via `dbt seed`
│   │   └── alert_thresholds.csv  # Initial threshold values — seeds meta.alert_thresholds
│   │
│   ├── snapshots/                # dbt snapshot models for SCD if needed later
│   │
│   └── docs/                     # dbt docs output — generated by `dbt docs generate`
│
├── api/                          # FastAPI service
│   ├── Dockerfile
│   ├── requirements.txt          # fastapi, uvicorn, asyncpg, sqlalchemy, pydantic
│   │
│   ├── main.py                   # App entry point; registers routers
│   ├── dependencies.py           # DB connection pool, API key auth dependency
│   │
│   ├── routers/                  # One file per endpoint group
│   │   ├── coins.py              # /coins/latest, /coins/{coin_id}/history
│   │   ├── alerts.py             # /alerts
│   │   ├── pipeline.py           # /pipeline/runs
│   │   ├── metrics.py            # /metrics/dominance
│   │   └── health.py             # /health
│   │
│   ├── schemas/                  # Pydantic response models
│   │   ├── coins.py
│   │   ├── alerts.py
│   │   └── pipeline.py
│   │
│   └── tests/                    # API unit + integration tests
│       ├── conftest.py           # Pytest fixtures (test DB, mock auth)
│       ├── test_coins.py
│       ├── test_alerts.py
│       └── test_health.py
│
├── postgres/                     # Market data DB initialisation
│   ├── Dockerfile                # Extends postgres:16; installs postgresql-16-partman
│   └── init/
│       ├── 01_schemas.sql        # CREATE SCHEMA raw, staging, marts, meta; CREATE EXTENSION pg_partman
│       ├── 02_tables.sql         # All raw.* and meta.* table definitions; calls partman.create_parent()
│       ├── 03_partitions.sql     # Partition lifecycle managed by pg_partman — document config here
│       └── 04_indexes.sql        # All indexes defined in §3.6
│
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/
│   │   │   ├── prometheus.yml    # Prometheus datasource — auto-provisioned on startup
│   │   │   └── postgres.yml      # PostgreSQL datasource — auto-provisioned on startup
│   │   └── dashboards/
│   │       └── dashboard.yml     # Tells Grafana where to find dashboard JSON files
│   └── dashboards/
│       └── market_platform.json  # Exported dashboard JSON — version-controlled
│
├── prometheus/
│   └── prometheus.yml            # Scrape config: targets statsd-exporter, cadvisor
│
├── scripts/                      # Operational one-off scripts, not part of the pipeline
│   ├── backfill.sh               # Triggers Airflow backfill for a date range
│   ├── create_partitions.sql     # Run manually when a new month approaches
│   └── seed_thresholds.sh        # Convenience wrapper around `dbt seed`
│
└── terraform/                    # Cloud IaC — empty until Phase 4 migration
    └── README.md                 # Explains what will live here and when
```

### Key Design Decisions in the Structure

**`airflow/tasks/` as pure Python modules, not inline DAG code.** The DAG file itself only defines the task graph. All business logic lives in `tasks/`. This makes individual task functions unit-testable without spinning up Airflow, and mirrors how production DAGs are structured.

**`dbt/seeds/alert_thresholds.csv` instead of a migration script.** Initial threshold values are managed as a dbt seed. Running `dbt seed` populates `meta.alert_thresholds`. This keeps configuration version-controlled and reproducible.

**`postgres/init/` split across four numbered files.** Docker's PostgreSQL image runs `init/` scripts in alphabetical order on first boot. Splitting by concern (schemas → tables → partitions → indexes) makes each file independently readable and easier to debug.

**`grafana/provisioning/` for datasources and dashboards.** Grafana supports fully automated provisioning via YAML files mounted at startup. This means the Grafana container comes up pre-configured with no manual UI clicks — a production pattern worth knowing.

**`terraform/` exists but is empty.** Planting it now signals architectural intent and avoids a future reorganisation. The README inside explains the phased migration plan from §8.3.

---

## 11. Docker Compose Layout

All services run on a single user-defined bridge network (`platform_net`). This is intentional — the default bridge network does not support DNS-based service discovery by name, which user-defined networks provide automatically. Every service reference (e.g. `postgres-market` as a hostname) works because they share this network.

Healthchecks are defined on every service. `depends_on` with `condition: service_healthy` is used throughout so containers only start when their dependencies are genuinely ready — not just running. This prevents the common race condition where Airflow starts before PostgreSQL has finished initialising.

```yaml
# docker-compose.yml
# All env vars are read from .env (see .env.example for required keys)
# Start stack: docker compose up -d
# Tear down + wipe volumes: docker compose down -v

version: "3.9"

x-airflow-common: &airflow-common
  # Shared config block reused by scheduler, webserver, and init service.
  # The & anchor + * alias pattern avoids repeating 30 lines per service.
  build:
    context: ./airflow
    dockerfile: Dockerfile
  environment:
    AIRFLOW__CORE__EXECUTOR: LocalExecutor
    AIRFLOW__CORE__SQL_ALCHEMY_CONN: postgresql+psycopg2://${AIRFLOW_DB_USER}:${AIRFLOW_DB_PASSWORD}@postgres-airflow:5432/${AIRFLOW_DB_NAME}
    AIRFLOW__CORE__FERNET_KEY: ${AIRFLOW_FERNET_KEY}
    AIRFLOW__CORE__LOAD_EXAMPLES: "false"
    AIRFLOW__WEBSERVER__SECRET_KEY: ${AIRFLOW_SECRET_KEY}
    # StatsD: emit pipeline metrics to the exporter, which Prometheus scrapes
    AIRFLOW__METRICS__STATSD_ON: "true"
    AIRFLOW__METRICS__STATSD_HOST: statsd-exporter
    AIRFLOW__METRICS__STATSD_PORT: "8125"
    # Market DB connection — used inside task code, not by Airflow core
    MARKET_DB_CONN: postgresql://${MARKET_DB_USER}:${MARKET_DB_PASSWORD}@postgres-market:5432/${MARKET_DB_NAME}
    # CoinGecko demo API key — used as X-CG-Demo-Api-Key header in extract.py
    COINGECKO_API_KEY: ${COINGECKO_API_KEY}
    # dbt profile target — tasks pass this when calling dbt CLI
    DBT_TARGET: prod
  volumes:
    - ./airflow/dags:/opt/airflow/dags
    - ./airflow/tasks:/opt/airflow/tasks
    - ./airflow/plugins:/opt/airflow/plugins
    - ./airflow/great_expectations:/opt/airflow/great_expectations
    - ./dbt:/opt/dbt # dbt project mounted into Airflow container
    - airflow_logs:/opt/airflow/logs # named volume — logs persist across restarts
  networks:
    - platform_net
  depends_on:
    postgres-airflow:
      condition: service_healthy
    postgres-market:
      condition: service_healthy

services:
  # ── PostgreSQL: Airflow metadata ─────────────────────────────────────────────
  postgres-airflow:
    image: postgres:16
    environment:
      POSTGRES_USER: ${AIRFLOW_DB_USER}
      POSTGRES_PASSWORD: ${AIRFLOW_DB_PASSWORD}
      POSTGRES_DB: ${AIRFLOW_DB_NAME}
    volumes:
      - postgres_airflow_data:/var/lib/postgresql/data # named volume — survives container rebuild
    networks:
      - platform_net
    healthcheck:
      # pg_isready confirms the DB is accepting connections, not just that the process is up
      test:
        [
          "CMD",
          "pg_isready",
          "-U",
          "${AIRFLOW_DB_USER}",
          "-d",
          "${AIRFLOW_DB_NAME}",
        ]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s # grace period before healthcheck starts counting retries

  # ── PostgreSQL: Market data ───────────────────────────────────────────────────
  postgres-market:
    build:
      context: ./postgres
      dockerfile: Dockerfile  # Extends postgres:16 with pg_partman; keeps image: removed
    environment:
      POSTGRES_USER: ${MARKET_DB_USER}
      POSTGRES_PASSWORD: ${MARKET_DB_PASSWORD}
      POSTGRES_DB: ${MARKET_DB_NAME}
    volumes:
      - postgres_market_data:/var/lib/postgresql/data
      # init/ scripts run once on first boot, in filename order (01_, 02_, ...)
      # They create schemas, tables, partitions, and indexes automatically
      - ./postgres/init:/docker-entrypoint-initdb.d
    ports:
      # Exposed to host only for local psql/DBeaver access during development
      # Remove this in any cloud deployment
      - "5433:5432"
    networks:
      - platform_net
    healthcheck:
      test:
        [
          "CMD",
          "pg_isready",
          "-U",
          "${MARKET_DB_USER}",
          "-d",
          "${MARKET_DB_NAME}",
        ]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s

  # ── Airflow: DB init + first-run setup ───────────────────────────────────────
  airflow-init:
    <<: *airflow-common
    # One-shot service: runs migrations and creates the admin user, then exits.
    # `restart: on-failure` so it retries if postgres-airflow isn't ready yet.
    # After success it stays in exited state — that is expected and correct.
    command: >
      bash -c "
        airflow db migrate &&
        airflow users create
          --username ${AIRFLOW_ADMIN_USER}
          --password ${AIRFLOW_ADMIN_PASSWORD}
          --firstname Admin
          --lastname User
          --role Admin
          --email ${AIRFLOW_ADMIN_EMAIL} || true
      "
    restart: on-failure

  # ── Airflow: Scheduler ───────────────────────────────────────────────────────
  airflow-scheduler:
    <<: *airflow-common
    command: scheduler
    restart: always
    depends_on:
      postgres-airflow:
        condition: service_healthy
      postgres-market:
        condition: service_healthy
      airflow-init:
        condition: service_completed_successfully # wait for migrations to finish

  # ── Airflow: Webserver ───────────────────────────────────────────────────────
  airflow-webserver:
    <<: *airflow-common
    command: webserver
    ports:
      - "8080:8080"
    restart: always
    depends_on:
      airflow-scheduler:
        condition: service_healthy
    healthcheck:
      # Hits the Airflow health endpoint — confirms the webserver is fully up
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s

  # ── FastAPI ───────────────────────────────────────────────────────────────────
  api:
    build:
      context: ./api
      dockerfile: Dockerfile
    environment:
      MARKET_DB_CONN: postgresql://${MARKET_DB_USER}:${MARKET_DB_PASSWORD}@postgres-market:5432/${MARKET_DB_NAME}
      API_KEY: ${API_KEY}
    ports:
      - "8000:8000"
    networks:
      - platform_net
    depends_on:
      postgres-market:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
    restart: always

  # ── StatsD exporter ───────────────────────────────────────────────────────────
  statsd-exporter:
    # Receives StatsD UDP metrics from Airflow and exposes them as Prometheus metrics.
    # This is the bridge between Airflow's built-in StatsD emission and Prometheus scraping.
    image: prom/statsd-exporter:latest
    ports:
      - "9102:9102" # Prometheus scrape port
      # Port 8125 (UDP) is not exposed to host — only reachable within platform_net
    networks:
      - platform_net
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:9102/metrics"]
      interval: 30s
      timeout: 5s
      retries: 3

  # ── Prometheus ────────────────────────────────────────────────────────────────
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro # ro = read-only mount
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    networks:
      - platform_net
    depends_on:
      statsd-exporter:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:9090/-/healthy"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: always

  # ── Grafana ───────────────────────────────────────────────────────────────────
  grafana:
    image: grafana/grafana:latest
    environment:
      GF_SECURITY_ADMIN_USER: ${GRAFANA_ADMIN_USER}
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD}
      GF_USERS_ALLOW_SIGN_UP: "false"
    volumes:
      - grafana_data:/var/lib/grafana
      # Provisioning dirs are read on startup — datasources and dashboards
      # are auto-configured with no manual UI clicks required
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
      - ./grafana/dashboards:/var/lib/grafana/dashboards:ro
    ports:
      - "3000:3000"
    networks:
      - platform_net
    depends_on:
      prometheus:
        condition: service_healthy
      postgres-market:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/api/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: always

# ── Named volumes ────────────────────────────────────────────────────────────────
volumes:
  # Named volumes persist data across `docker compose down` (but not `down -v`).
  # Bind mounts (./path:) are used for config/code that should be version-controlled.
  # Data that must not be lost (DB files, Grafana state) always uses named volumes.
  postgres_airflow_data:
  postgres_market_data:
  airflow_logs:
  prometheus_data:
  grafana_data:

# ── Network ───────────────────────────────────────────────────────────────────────
networks:
  platform_net:
    # User-defined bridge network enables DNS resolution by service name.
    # e.g. postgres-market is reachable as hostname "postgres-market" from any service.
    # The default bridge network does not support this.
    driver: bridge
```

### Service Startup Order

The `depends_on` chain resolves to this boot sequence:

```
postgres-airflow  ──┐
                    ├── airflow-init ── airflow-scheduler ── airflow-webserver
postgres-market   ──┘         │
                               └── api
statsd-exporter ── prometheus ── grafana
```

Both DB services start in parallel. Everything else waits on its health dependencies before starting.

### Key Patterns to Understand

**YAML anchors (`&airflow-common` / `<<: *airflow-common`).** The three Airflow services (init, scheduler, webserver) share 30+ lines of config. The anchor defines it once; the alias merges it in. Without this, any change to a shared env var requires editing three places. This is a standard compose pattern for multi-process services.

**`service_completed_successfully` vs `service_healthy`.** The `airflow-init` service is a one-shot migration runner — it exits with code 0 when done. Using `service_healthy` on it would never resolve because a stopped container cannot pass a healthcheck. `service_completed_successfully` is the correct condition for one-shot init containers.

**Named volumes vs bind mounts.** Code and config (`./airflow/dags`, `./prometheus/prometheus.yml`) use bind mounts so changes on the host are reflected immediately without rebuilding. Stateful data (DB files, Grafana state, logs) uses named volumes so it survives container rebuilds but is isolated from the host filesystem.

**Port 5433 on postgres-market.** The internal port is still 5432 — that is what other containers use. The `5433:5432` mapping only applies to host access (psql, DBeaver). This avoids conflict with any local PostgreSQL installation on the host.

### Required `.env` Keys

```bash
# Airflow metadata DB
AIRFLOW_DB_USER=
AIRFLOW_DB_PASSWORD=
AIRFLOW_DB_NAME=airflow

# Market data DB
MARKET_DB_USER=
MARKET_DB_PASSWORD=
MARKET_DB_NAME=market

# Airflow security
AIRFLOW_FERNET_KEY=          # generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
AIRFLOW_SECRET_KEY=          # any random string
AIRFLOW_ADMIN_USER=
AIRFLOW_ADMIN_PASSWORD=
AIRFLOW_ADMIN_EMAIL=

# FastAPI
API_KEY=                     # any random string for X-API-Key header auth

# CoinGecko
COINGECKO_API_KEY=           # free demo key from coingecko.com — sent as X-CG-Demo-Api-Key header

# Grafana
GRAFANA_ADMIN_USER=
GRAFANA_ADMIN_PASSWORD=
```

---

## 12. Implementation Roadmap

Each phase ends with a fully runnable, verifiable state. Never move to the next phase with a broken or unverified previous phase — debugging across two phases simultaneously is expensive.

The exit criteria listed under each phase are the minimum bar to consider it complete. They are also the things a reviewer or interviewer would check first.

---

### Phase 1 — Infrastructure Skeleton

**Goal:** Every container starts, stays healthy, and can talk to the containers it depends on. No pipeline logic yet.

**Tasks:**

- Ensure the repo is cloned inside the WSL2 filesystem (`~/projects/`) — Docker bind mounts from WSL2 are far faster than from the Windows filesystem (`C:\`)
- Write `.env` from `.env.example`
- Write `postgres/Dockerfile` — extend `postgres:16`, install `postgresql-16-partman` via apt; update `postgres-market` in `docker-compose.yml` to use `build: ./postgres` instead of `image: postgres:16`
- Write `postgres/init/01_schemas.sql` — create `raw`, `staging`, `marts`, `meta` schemas; `CREATE EXTENSION pg_partman SCHEMA partman;`
- Write `postgres/init/02_tables.sql` — all tables from §3; after creating `raw.market_snapshots`, call `SELECT partman.create_parent('raw.market_snapshots', 'snapshot_timestamp', 'native', 'monthly');`
- Write `postgres/init/03_partitions.sql` — no longer needed for bootstrapping (pg_partman handles this), but document here that pg_partman is now managing the partition lifecycle
- Write `postgres/init/04_indexes.sql` — all indexes from §3.6
- Write `airflow/Dockerfile` — extend `apache/airflow:2.x`, install `requirements.txt`
- Write `api/Dockerfile` — Python slim base, install `requirements.txt`
- Write `prometheus/prometheus.yml` — scrape targets: `statsd-exporter:9102`
- Write `grafana/provisioning/datasources/prometheus.yml` and `postgres.yml`
- Run `docker compose up -d` and confirm all healthchecks pass

**Exit criteria:**

- `docker compose ps` shows all services as healthy
- Can connect to `postgres-market` on port 5433 with a SQL client and see all schemas and tables
- Airflow webserver is reachable at `localhost:8080`
- Grafana is reachable at `localhost:3000` with both datasources showing green

---

### Phase 2 — Raw Ingestion DAG (no dbt, no alerts)

**Goal:** A working Airflow DAG that extracts from CoinGecko and loads into `raw.market_snapshots`. The DAG must be idempotent and handle the validation branch correctly.

**Tasks:**

- Write `airflow/tasks/extract.py` — call CoinGecko `/coins/markets`, return list of 20 dicts
- Write `airflow/tasks/validate.py` — Great Expectations checkpoint on raw payload; fail fast on schema drift or null prices
- Write `airflow/tasks/load.py` — UPSERT into `raw.market_snapshots` using `ON CONFLICT DO UPDATE`
- Write `airflow/tasks/pipeline_log.py` — write final run status to `raw.pipeline_runs`
- Write `airflow/dags/market_ingestion.py` — wire up: `http_sensor → extract → validate → branch → load → log`; `skip_and_alert` branch writes `QUALITY_FAIL` to `pipeline_runs`
- Configure Great Expectations: run `great_expectations init` **on the host machine** inside the `airflow/` directory (not inside Docker — the command is interactive and requires a terminal). The resulting `airflow/great_expectations/` directory is already bind-mounted into the container. After init, create the expectation suite and checkpoint via the GE CLI or Python API on the host.

**Exit criteria:**

- Trigger DAG manually; it completes successfully end-to-end
- `raw.market_snapshots` has 20 rows after one run
- Triggering the same DAG run again (same `execution_date`) does not duplicate rows
- Manually break the GE checkpoint (e.g. force a null value) and confirm the `skip_and_alert` branch fires and `pipeline_runs` records `QUALITY_FAIL`
- `raw.pipeline_runs` has a record for every run with correct status

---

### Phase 3 — dbt Transformation Layer

**Goal:** dbt models run successfully after each load. Mart tables are populated and queryable.

**Tasks:**

- Initialise dbt project: `dbt init` inside `dbt/`
- Configure `profiles.yml` to read connection from env vars
- Write `dbt/models/staging/stg_market_snapshots.sql` — rename columns, cast types, exclude nulls
- Write `dbt/models/staging/schema.yml` — source definition pointing to `raw.market_snapshots`; add `not_null` and `unique` tests
- Write `dbt/models/intermediate/int_coin_metrics.sql` — window functions: 7d rolling avg, 7d volatility, volume spike ratio
- Write `dbt/models/intermediate/schema.yml` — range check tests on price and volume
- Write `dbt/models/marts/mart_coin_summary.sql` — denormalised, business-ready join of snapshots + metrics
- Write `dbt/models/marts/mart_alerts.sql` — alert view joined with coin metadata
- Write `dbt/models/marts/schema.yml` — column descriptions + tests
- Write `dbt/tests/assert_dominance_sums_to_100.sql` — custom singular test
- Add `run_dbt_models`, `emit_dbt_metrics`, and `run_dbt_tests` tasks to DAG after `load_market_data` (in that order)
- Write `airflow/tasks/dbt_metrics.py` — reads `/opt/dbt/target/run_results.json` after a dbt run, parses `results[].timing` per model, emits `dbt_model_run_duration_seconds` histogram to StatsD via the Python `statsd` client; add `statsd` to `airflow/requirements.txt`
- Add `on_failure_callback` to `run_dbt_tests` — writes `QUALITY_FAIL` to `pipeline_runs`

**Exit criteria:**

- `dbt run --select staging+` completes with no errors
- `dbt test --select staging+` passes all tests
- `marts.mart_coin_summary` has 20 rows after a successful DAG run
- Intentionally break a dbt test; confirm `on_failure_callback` fires and DAG marks the run correctly

---

### Phase 4 — Alerts and SLA

**Goal:** Alert logic is driven by `meta.alert_thresholds`. SLA breaches are detected and recorded. Both appear correctly in `raw.alerts` and `raw.sla_breaches`.

**Tasks:**

- Seed `meta.alert_thresholds`: write `dbt/seeds/alert_thresholds.csv`, run `dbt seed`
- Write `airflow/tasks/alerts.py` — read thresholds from `meta.alert_thresholds`; evaluate each coin's metrics; write to `raw.alerts`
- Write `airflow/tasks/sla.py` — compare latest `snapshot_timestamp` to wall clock; write to `raw.sla_breaches` if lag > 90 min; emit `data_freshness_lag_minutes` to StatsD
- Add `generate_alerts` and `sla_check` tasks to DAG after `run_dbt_tests`
- Add Airflow-native SLA miss callback to DAG definition
- Add `TriggerRule.NONE_FAILED` to `log_pipeline_run` to ensure it always runs

**Exit criteria:**

- `raw.alerts` populates after a DAG run with correct `severity` values
- Manually lower a threshold in `meta.alert_thresholds` and confirm new alerts fire on next run — without any code change
- Simulate an SLA breach (pause the scheduler, wait, resume) and confirm `raw.sla_breaches` records it
- `log_pipeline_run` fires correctly on both the success branch and the `skip_and_alert` branch

---

### Phase 5 — Observability

**Goal:** Grafana dashboards are fully populated from both Prometheus (pipeline metrics) and PostgreSQL (business data). All panels from §6.2 are working.

**Tasks:**

- Verify StatsD metrics are reaching Prometheus: query `airflow_*` metrics in Prometheus UI at `localhost:9090`
- Build Grafana dashboard — add all panels from §6.2 one at a time
- Export dashboard JSON to `grafana/dashboards/market_platform.json`
- Configure `grafana/provisioning/dashboards/dashboard.yml` to auto-load the JSON on startup
- Verify dashboard auto-provisions on a fresh `docker compose down -v && docker compose up -d`

**Exit criteria:**

- All 7 panels from §6.2 are populated with real data
- Data freshness gauge correctly reflects lag between wall clock and latest `snapshot_timestamp`
- Dashboard survives a full stack teardown and restart without any manual UI reconfiguration
- At least one Prometheus-sourced panel and one PostgreSQL-sourced panel are confirmed working

---

### Phase 6 — FastAPI

**Goal:** All endpoints from §7.1 are working and documented. API reads exclusively from mart tables.

**Tasks:**

- Write `api/dependencies.py` — asyncpg connection pool; `X-API-Key` auth dependency
- Write `api/routers/health.py` — check DB connectivity and latest snapshot age
- Write `api/routers/coins.py` — `/coins/latest` and `/coins/{coin_id}/history` with pagination
- Write `api/routers/alerts.py` — `/alerts` with `severity` and `coin_id` filters
- Write `api/routers/pipeline.py` — `/pipeline/runs`
- Write `api/routers/metrics.py` — `/metrics/dominance`
- Write Pydantic schemas in `api/schemas/`
- Write `api/main.py` — register all routers
- Write `api/tests/` — at minimum: `test_health.py`, one happy-path test per router, one auth failure test

**Exit criteria:**

- All endpoints return correct data verified against direct DB queries
- `GET /health` returns unhealthy if `postgres-market` is stopped
- `GET /coins/{coin_id}/history` with `?from=` and `?to=` returns correct date-filtered results
- A request with a missing or wrong `X-API-Key` returns 401
- `GET /docs` (auto-generated OpenAPI) loads cleanly with all endpoints documented
- All tests in `api/tests/` pass

---

### Phase 7 — Hardening and Review

**Goal:** The system is solid enough to present as a portfolio project. Code is clean, documented, and the README tells the full story.

**Tasks:**

- Write `README.md` — project overview, architecture diagram (even ASCII is fine), prerequisites, setup steps, how to run backfill, how to run dbt manually
- Write `scripts/backfill.sh` — wraps `airflow dags backfill` with date range args
- Write `scripts/create_partitions.sql` — template for creating next month's partition; document that this should be run before month rollover
- Review all task code for bare `except` clauses — replace with specific exceptions and proper logging
- Confirm `.gitignore` covers `.env`, `__pycache__`, `dbt/target/`, `dbt/logs/`, `airflow/logs/`
- Run a full stack teardown (`docker compose down -v`) and cold start — confirm everything comes up cleanly from scratch with only `.env` and the repo

**Exit criteria:**

- Cold start from a clean clone works end-to-end following only the README
- No credentials or hostnames are hardcoded anywhere in the codebase
- A DAG run triggered manually completes successfully and all downstream systems (dbt, alerts, SLA, Grafana) reflect the result
- `api/tests/` and `dbt test` both pass cleanly

---

### Phase 8 — Cloud Migration (optional, follow §8.3)

**Goal:** Move stateful services off local Docker incrementally. Each step is independently deployable and reversible.

**Tasks:** Follow the phased plan in §8.3. Start with Phase 1 (managed PostgreSQL) only when Phase 7 is fully complete and stable locally.

**Exit criteria:** Defined per cloud phase in §8.3.

---

### Roadmap Summary

| Phase | Deliverable                | Key Learning                                        |
| ----- | -------------------------- | --------------------------------------------------- |
| 1     | All containers healthy     | Docker networking, healthchecks, Postgres init      |
| 2     | Raw ingestion DAG working  | Airflow operators, GE validation, idempotent loads  |
| 3     | dbt models + tests passing | dbt layers, SQL window functions, data contracts    |
| 4     | Alerts + SLA tracking      | Config-driven logic, Airflow callbacks, TriggerRule |
| 5     | Grafana dashboards live    | Prometheus metrics, Grafana provisioning            |
| 6     | FastAPI endpoints live     | Async Python, Pydantic, SQLAlchemy Core, auth       |
| 7     | Portfolio-ready            | Documentation, cold-start reliability, code hygiene |
| 8     | Cloud deployment           | Managed services, env portability, IaC basics       |
