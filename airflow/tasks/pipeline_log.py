import os
import psycopg2


def log_pipeline_run(execution_date, status, rows_inserted, error_message):
    conn_str = (
        f"host=postgres-market "
        f"dbname={os.environ['MARKET_DB_NAME']} "
        f"user={os.environ['MARKET_DB_USER']} "
        f"password={os.environ['MARKET_DB_PASSWORD']}"
    )
    
      
    sql = """
        INSERT INTO raw.pipeline_runs (
            execution_date,
            start_time,
            end_time,
            status,
            rows_inserted,
            error_message
        )

        VALUES (%s, %s, %s,%s,%s,%s)


    """

    with psycopg2.connect(conn_str) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (execution_date, None, None, status, rows_inserted, error_message))