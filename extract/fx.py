"""Extract ZAR exchange rates from the Frankfurter API into raw.fx_rates.

Run from the repo root:
    python -m extract.fx                     # incremental: only new dates
    python -m extract.fx --start 2023-01-01  # backfill from a given date
"""
import argparse
import logging
import os
from datetime import date, timedelta

import psycopg2
import requests
from dotenv import load_dotenv
from psycopg2.extras import execute_values

API_URL = "https://api.frankfurter.dev/v2/rates"
BASE_CURRENCIES = ["USD", "EUR", "GBP"]  # rates come back as "1 USD = x ZAR"
QUOTE_CURRENCY = "ZAR"
DEFAULT_BACKFILL_DAYS = 3 * 365  # first run loads about 3 years
LOOKBACK_DAYS = 3  # re-fetch recent days in case a rate was corrected

log = logging.getLogger("fx")

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS raw.fx_rates (
    rate_date       DATE        NOT NULL,
    base_currency   TEXT        NOT NULL,
    quote_currency  TEXT        NOT NULL,
    rate            NUMERIC     NOT NULL,
    _loaded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (rate_date, base_currency, quote_currency)
);
"""

UPSERT = """
INSERT INTO raw.fx_rates (rate_date, base_currency, quote_currency, rate)
VALUES %s
ON CONFLICT (rate_date, base_currency, quote_currency)
DO UPDATE SET rate = EXCLUDED.rate, _loaded_at = now();
"""


def get_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def start_date_for(cur, base):
    """Pick up where the last run stopped, minus a small lookback window."""
    cur.execute(
        "SELECT max(rate_date) FROM raw.fx_rates WHERE base_currency = %s",
        (base,),
    )
    latest = cur.fetchone()[0]
    if latest is None:
        return date.today() - timedelta(days=DEFAULT_BACKFILL_DAYS)
    return latest - timedelta(days=LOOKBACK_DAYS)


def fetch_rates(base, start, end):
    params = {
        "base": base,
        "quotes": QUOTE_CURRENCY,
        "from": start.isoformat(),
        "to": end.isoformat(),
    }
    response = requests.get(API_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()  # a list of {"date", "base", "quote", "rate"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, help="backfill from this date (YYYY-MM-DD)")
    args = parser.parse_args()

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    end = date.today()

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(CREATE_TABLE)
        for base in BASE_CURRENCIES:
            start = args.start or start_date_for(cur, base)
            log.info("Fetching %s/%s from %s to %s", base, QUOTE_CURRENCY, start, end)
            rows = fetch_rates(base, start, end)
            values = [(r["date"], r["base"], r["quote"], r["rate"]) for r in rows]
            if values:
                execute_values(cur, UPSERT, values)
            log.info("Loaded %d rows for %s", len(values), base)
    # leaving the "with" block commits everything, or rolls back on any error


if __name__ == "__main__":
    main()