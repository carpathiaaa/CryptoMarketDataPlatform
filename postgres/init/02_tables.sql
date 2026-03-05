-- =============================================================
-- raw.market_snapshots  (partitioned by month on snapshot_timestamp)
-- =============================================================

CREATE TABLE IF NOT EXISTS raw.market_snapshots (
    coin_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    price_usd NUMERIC(20, 8) NOT NULL,
    market_cap_usd NUMERIC(30, 2),
    volume_24h_usd NUMERIC(30, 2),
    price_change_pct_24h NUMERIC(10, 4),
    snapshot_timestamp TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_version TEXT,
    PRIMARY KEY (coin_id, snapshot_timestamp)
)
PARTITION BY
    RANGE (snapshot_timestamp);

-- Hand off partition management to pg_partman (monthly, pre-create 3 future months)
SELECT partman.create_parent (
        p_parent_table => 'raw.market_snapshots', 
        p_control => 'snapshot_timestamp', 
        p_interval => '1 month', 
        p_premake => 3
    );

-- =============================================================
-- raw.alerts
-- =============================================================
CREATE TABLE IF NOT EXISTS raw.alerts (
    alert_id SERIAL PRIMARY KEY,
    coin_id TEXT NOT NULL,
    snapshot_timestamp TIMESTAMPTZ NOT NULL,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    metric_value NUMERIC NOT NULL,
    threshold_value NUMERIC NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================
-- raw.pipeline_runs
-- =============================================================
CREATE TABLE IF NOT EXISTS raw.pipeline_runs (
    run_id SERIAL PRIMARY KEY,
    execution_date TIMESTAMPTZ NOT NULL,
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    status TEXT NOT NULL,
    rows_inserted INT,
    error_message TEXT,
    sla_status TEXT NOT NULL DEFAULT 'OK'
);

-- =============================================================
-- raw.sla_breaches
-- =============================================================
CREATE TABLE IF NOT EXISTS raw.sla_breaches (
    breach_id SERIAL PRIMARY KEY,
    expected_timestamp TIMESTAMPTZ NOT NULL,
    actual_latest_timestamp TIMESTAMPTZ NOT NULL,
    delay_minutes NUMERIC NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================
-- meta.alert_thresholds
-- =============================================================
CREATE TABLE IF NOT EXISTS meta.alert_thresholds (
    metric_name TEXT NOT NULL,
    severity TEXT NOT NULL,
    threshold_value NUMERIC NOT NULL,
    comparison_operator TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (metric_name, severity)
);