import great_expectations as gx
import pandas as pd

SUITE_NAME = "market_snapshot_suite"
GE_ROOT = "/opt/airflow/great_expectations"

def validate_snapshot(records: list[dict]) -> bool:
    context = gx.get_context(mode="file", project_root_dir=GE_ROOT)
    suite = context.suites.get(SUITE_NAME)

    datasource = context.data_sources.add_or_update_pandas(name="runtime_source")
    asset = datasource.add_dataframe_asset(name="snapshot_asset")
    batch_definition = asset.add_batch_definition_whole_dataframe("whole_dataframe")

    df = pd.DataFrame(records)
    batch = batch_definition.get_batch(batch_parameters={"dataframe": df})

    results = batch.validate(suite)
    return bool(results.success)
