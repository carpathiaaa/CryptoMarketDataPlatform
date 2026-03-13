import os
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import execute_values

def load_records(records: list[dict]) -> int:
    conn_str = (
        f"host=postgres-market "
        f"dbname={os.environ['MARKET_DB_NAME']} "
        f"user={os.environ['MARKET_DB_USER']} "
        f"password={os.environ['MARKET_DB_PASSWORD']}"
    )
        
    rows = [
        (
            r["coin_id"],
            r["symbol"],
            r["name"],
            r["price_usd"],
            r["market_cap_usd"],
            r["volume_24h_usd"],
            r["price_change_pct_24h"],
            r["snapshot_timestamp"],
            datetime.now(timezone.utc)
        )
        for r in records
    ]

    sql = """
        INSERT INTO raw.market_snapshots (
            coin_id, 
            symbol,
            name,
            price_usd,
            market_cap_usd,
            volume_24h_usd,
            price_change_pct_24h,
            snapshot_timestamp,
            ingested_at   
        )

        VALUES %s
        ON CONFLICT (coin_id, snapshot_timestamp)
        DO UPDATE SET
            price_usd = EXCLUDED.price_usd,
            market_cap_usd = EXCLUDED.market_cap_usd,
            volume_24h_usd = EXCLUDED.volume_24h_usd,
            price_change_pct_24h = EXCLUDED.price_change_pct_24h,
            ingested_at = EXCLUDED.ingested_at
    """

    with psycopg2.connect(conn_str) as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, rows)
            row_count = cur.rowcount

    return row_count


