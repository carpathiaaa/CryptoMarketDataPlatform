-- =============================================================
-- raw.market_snapshots indexes
-- =============================================================

-- Point lookups for a single coin's recent history
CREATE INDEX ON raw.market_snapshots (coin_id, snapshot_timestamp DESC);

-- Recent-N queries across all coins (e.g. latest snapshot per coin)
CREATE INDEX ON raw.market_snapshots (snapshot_timestamp DESC);


-- =============================================================
-- raw.pipeline_runs indexes
-- =============================================================

-- Lookup runs by execution date (most common access pattern)
CREATE INDEX ON raw.pipeline_runs (execution_date DESC);

-- Filter runs by status (e.g. all QUALITY_FAIL runs)
CREATE INDEX ON raw.pipeline_runs (status);


-- =============================================================
-- raw.alerts indexes
-- =============================================================

-- Dashboard alert feed - only HIGH severity alerts queried frequently
CREATE INDEX ON raw.alerts (created_at DESC) WHERE severity = 'HIGH';

-- Alert lookups by coin
CREATE INDEX ON raw.alerts (coin_id, snapshot_timestamp DESC);
