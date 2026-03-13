from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.sensors.http import HttpSensor
from airflow.utils.trigger_rule import TriggerRule

from tasks.extract import fetch_top20
from tasks.validate import validate_snapshot
from tasks.load import load_records
from tasks.pipeline_log import log_pipeline_run


DEFAULT_ARGS = {
    "owner": "airflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=5)
}

with DAG(
    dag_id = "market_ingestion",
    default_args = DEFAULT_ARGS,
    start_date = datetime(2024, 1, 1),
    schedule_interval = "@hourly",
    catchup = False
) as dag:
    
    wait_for_api = HttpSensor(
        task_id="wait_for_api",
        http_conn_id="coingecko_api",
        endpoint="api/v3/ping",
        poke_interval=60,
        timeout=300,
    )

    def _extract(**context):
        records = fetch_top20(context["logical_date"])
        context["ti"].xcom_push(key="records", value=records)

    def _validate(**context):
        records = context["ti"].xcom_pull(task_ids="extract_task", key="records")
        passed = validate_snapshot(records)
        return "load_task" if passed else "skip_and_alert"
    
    def _load(**context):
        records = context["ti"].xcom_pull(task_ids="extract_task", key="records")
        row_count = load_records(records)
        context["ti"].xcom_push(key="row_count", value=row_count)

    def _skip_and_alert(**context):
        log_pipeline_run(
            execution_date=context["logical_date"],
            status="QUALITY_FAIL",
            rows_inserted=0,
            error_message="Great Expectations validation failed"
        )

    extract_task = PythonOperator(task_id="extract_task", python_callable=_extract)
    validate_task = BranchPythonOperator(task_id="validate_task", python_callable=_validate)
    load_task  = PythonOperator(task_id="load_task", python_callable=_load)
    skip_and_alert = PythonOperator(task_id="skip_and_alert", python_callable=_skip_and_alert)
