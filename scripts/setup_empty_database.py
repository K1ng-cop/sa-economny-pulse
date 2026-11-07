"""Create the schemas and the (empty) raw tables, without calling any API.

Used by CI: GitHub Actions starts a brand-new Postgres for every run, so dbt needs the
raw tables to exist before it can build. The table definitions come straight from the
extractors, so CI always tests against the same structure the extractors create.

Run from the repo root:  python -m scripts.setup_empty_database
"""
from pathlib import Path

from dotenv import load_dotenv

from extract import cpi, fuel, fx, weather
from extract.db import get_connection

REPO_ROOT = Path(__file__).resolve().parent.parent


def main():
    load_dotenv()
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute((REPO_ROOT / "docker" / "init.sql").read_text())
        for ddl in (fx.CREATE_TABLE, weather.CREATE_TABLE, cpi.CREATE_TABLES, fuel.CREATE_TABLE):
            cur.execute(ddl)
    print("Schemas and raw tables are ready")


if __name__ == "__main__":
    main()
