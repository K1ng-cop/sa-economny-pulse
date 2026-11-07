"""Dagster definitions for SA Economy Pulse.

Start the UI from the repo root:
    dagster dev -f orchestration/definitions.py
then open http://localhost:3000
"""
import os
import subprocess
import sys
from pathlib import Path

import dagster as dg
import requests 
from dagster_dbt import DbtCliResource, DbtProject, dbt_assets

REPO_ROOT = Path(__file__).resolve().parent.parent
DBT_DIR = REPO_ROOT / "dbt"
CPI_LANDING = REPO_ROOT / "data" / "landing" / "cpi"
TIMEZONE = "Africa/Johannesburg"

dbt_project = DbtProject(project_dir=DBT_DIR, profiles_dir=DBT_DIR)
dbt_project.prepare_if_dev()  # in `dagster dev`, re-parses dbt so model changes show up

# Retry a failed step twice: after 1 minute, then 2 minutes
RETRY = dg.RetryPolicy(max_retries=2, delay=60, backoff=dg.Backoff.EXPONENTIAL)


# ---------------------------------------------------------------- extract (Python)

def run_extractor(context, module, *args):
    """Run one of our extractor scripts exactly as you would by hand, and stream its log
    into Dagster. A non-zero exit code (e.g. weather.py's sys.exit(1)) fails the step."""
    cmd = [sys.executable, "-m", module, *args]
    context.log.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    for line in (result.stdout + result.stderr).splitlines():
        context.log.info(line)
    if result.returncode != 0:
        raise dg.Failure(f"{module} exited with code {result.returncode}")


# The asset keys match the dbt sources (raw.fx_rates etc.), so Dagster links each
# extractor to the dbt models that read its table - that's the lineage graph.

@dg.asset(key=["raw", "fx_rates"], group_name="extract", retry_policy=RETRY,
          kinds={"python", "postgres"}, description="ZAR exchange rates from the Frankfurter API.")
def fx_rates(context: dg.AssetExecutionContext):
    run_extractor(context, "extract.fx")


@dg.asset(key=["raw", "weather_daily"], group_name="extract", retry_policy=RETRY,
          kinds={"python", "postgres"}, description="Cape Town weather from the Open-Meteo archive.")
def weather_daily(context: dg.AssetExecutionContext):
    run_extractor(context, "extract.weather")


@dg.asset(key=["raw", "fuel_prices"], group_name="extract", retry_policy=RETRY,
          kinds={"python", "postgres"}, description="Fuel prices scraped from the Fuels Industry Association page.")
def fuel_prices(context: dg.AssetExecutionContext):
    run_extractor(context, "extract.fuel", "--download")


@dg.multi_asset(
    specs=[
        dg.AssetSpec(["raw", "cpi_series"], group_name="extract", kinds={"python", "postgres"}),
        dg.AssetSpec(["raw", "cpi_values"], group_name="extract", kinds={"python", "postgres"}),
    ],
    description="Stats SA CPI from the newest Excel file in data/landing/cpi/ (one script, two tables).",
)
def cpi(context: dg.AssetExecutionContext):
    run_extractor(context, "extract.cpi")
    yield dg.MaterializeResult(asset_key=["raw", "cpi_series"])
    yield dg.MaterializeResult(asset_key=["raw", "cpi_values"])


# ---------------------------------------------------------------- transform (dbt)

@dbt_assets(manifest=dbt_project.manifest_path)
def dbt_models(context: dg.AssetExecutionContext, dbt: DbtCliResource):
    """Every dbt model, seed and test. `dbt build` runs the tests too, so a failing
    test stops the bad data reaching the marts - exactly as when you run it by hand."""
    yield from dbt.cli(["build"], context=context).stream()


# ---------------------------------------------------------------- jobs

# "Run this asset and everything downstream of it"
daily_refresh = dg.define_asset_job(
    "daily_refresh",
    selection=dg.AssetSelection.assets(fx_rates, weather_daily).downstream(),
    description="FX and weather, then every dbt model that depends on them.",
)

fuel_refresh = dg.define_asset_job(
    "fuel_refresh",
    selection=dg.AssetSelection.assets(fuel_prices).downstream(),
    description="Download the fuel price page, then rebuild what depends on it.",
)

cpi_refresh = dg.define_asset_job(
    "cpi_refresh",
    selection=dg.AssetSelection.assets(cpi).downstream(),
    description="Load the newest CPI file, then rebuild what depends on it.",
)


# ---------------------------------------------------------------- schedules & sensors

daily_schedule = dg.ScheduleDefinition(
    job=daily_refresh, cron_schedule="0 7 * * *", execution_timezone=TIMEZONE,
)

# Fuel prices change on the first Wednesday of the month and the page is updated a few
# days before. Checking every Wednesday is cheap (one request) and never misses a change.
fuel_schedule = dg.ScheduleDefinition(
    job=fuel_refresh, cron_schedule="0 12 * * 3", execution_timezone=TIMEZONE,
)


@dg.sensor(job=cpi_refresh, minimum_interval_seconds=3600)
def new_cpi_file(context: dg.SensorEvaluationContext):
    """Stats SA has no API, so CPI files are downloaded by hand. When a new file lands
    in data/landing/cpi/, this sensor starts the CPI load automatically."""
    files = sorted(CPI_LANDING.glob("*CPI (COICOP)*.xlsx"))
    if not files:
        return dg.SkipReason(f"No CPI file in {CPI_LANDING}")
    newest = files[-1].name
    if newest == context.cursor:
        return dg.SkipReason(f"Already loaded {newest}")
    context.update_cursor(newest)
    return dg.RunRequest(run_key=newest)


# ---------------------------------------------------------------- alerts

@dg.run_failure_sensor(default_status=dg.DefaultSensorStatus.RUNNING)
def alert_on_failure(context: dg.RunFailureSensorContext):
    """Send a message to Slack or Discord whenever any run fails - an API down, a dbt test
    catching bad data, anything. Set ALERT_WEBHOOK_URL in .env to switch it on."""
    run = context.dagster_run
    failed_steps = [event.step_key for event in context.get_step_failure_events()]
    message = (
        f"SA Economy Pulse: job '{run.job_name}' failed\n"
        f"Failed steps: {', '.join(failed_steps) or 'see run'}\n"
        f"Details: http://localhost:3000/runs/{run.run_id}"
    )

    url = os.getenv("ALERT_WEBHOOK_URL")
    if not url:
        context.log.warning(f"ALERT_WEBHOOK_URL not set, so no alert sent:\n{message}")
        return
    payload = {"content": message} if "discord" in url else {"text": message}  # Discord vs Slack
    requests.post(url, json=payload, timeout=10).raise_for_status()


defs = dg.Definitions(
    assets=[fx_rates, weather_daily, fuel_prices, cpi, dbt_models],
    jobs=[daily_refresh, fuel_refresh, cpi_refresh],
    schedules=[daily_schedule, fuel_schedule],
    sensors=[new_cpi_file, alert_on_failure],
    resources={"dbt": DbtCliResource(project_dir=dbt_project)},
)