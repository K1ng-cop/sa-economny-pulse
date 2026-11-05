"""Extract daily weather from the Open-Meteo archive API into raw.weather_daily.

Run from the repo root:
    python -m extract.weather                     # incremental: only new dates
    python -m extract.weather --start 2023-01-01  # backfill from a given date
"""
import argparse
import logging
import sys
from datetime import date, timedelta

import requests
from dotenv import load_dotenv
from psycopg2.extras import execute_values
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from extract.db import get_connection

API_URL = "https://archive-api.open-meteo.com/v1/archive"
LOCATIONS = {
    "cape_town":     (-33.9249, 18.4241),  # southwest coast, winter rain
    "vredenburg":    (-32.9064, 17.9900),  # West Coast
    "worcester":     (-33.6461, 19.4485),  # Breede River valley, winelands
    "george":        (-33.9630, 22.4617),  # Garden Route, rain all year
    "oudtshoorn":    (-33.5900, 22.2014),  # Klein Karoo
    "beaufort_west": (-32.3567, 22.5830),  # Central Karoo, dry interior
    "stellenbosch":  (-33.9321, 18.8602),
    "bellville":     (-33.9000, 18.6300),
    "kuils_river":   (-33.9300, 18.6800),
}
DAILY_VARIABLES = [
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "precipitation_sum",
    "wind_speed_10m_max",
]
TIMEZONE = "Africa/Johannesburg"  # so each "day" is a South African day
ARCHIVE_DELAY_DAYS = 5  # the archive runs about 5 days behind today
DEFAULT_BACKFILL_DAYS = 3 * 365
LOOKBACK_DAYS = 3

log = logging.getLogger("weather")

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS raw.weather_daily (
    weather_date         DATE        NOT NULL,
    location             TEXT        NOT NULL,
    latitude             NUMERIC     NOT NULL,
    longitude            NUMERIC     NOT NULL,
    temperature_2m_max   NUMERIC,
    temperature_2m_min   NUMERIC,
    temperature_2m_mean  NUMERIC,
    precipitation_sum    NUMERIC,
    wind_speed_10m_max   NUMERIC,
    _loaded_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (weather_date, location)
);
"""

UPSERT = """
INSERT INTO raw.weather_daily (
    weather_date, location, latitude, longitude,
    temperature_2m_max, temperature_2m_min, temperature_2m_mean,
    precipitation_sum, wind_speed_10m_max
)
VALUES %s
ON CONFLICT (weather_date, location) DO UPDATE SET
    temperature_2m_max  = EXCLUDED.temperature_2m_max,
    temperature_2m_min  = EXCLUDED.temperature_2m_min,
    temperature_2m_mean = EXCLUDED.temperature_2m_mean,
    precipitation_sum   = EXCLUDED.precipitation_sum,
    wind_speed_10m_max  = EXCLUDED.wind_speed_10m_max,
    _loaded_at          = now();
"""


def start_date_for(cur, location):
    cur.execute(
        "SELECT max(weather_date) FROM raw.weather_daily WHERE location = %s",
        (location,),
    )
    latest = cur.fetchone()[0]
    if latest is None:
        return date.today() - timedelta(days=DEFAULT_BACKFILL_DAYS)
    return latest - timedelta(days=LOOKBACK_DAYS)



def make_session():
    """A requests session that retries timeouts and server errors, waiting longer each time."""
    retry = Retry(
        total=4,
        backoff_factor=2,  # waits 2s, 4s, 8s, 16s between attempts
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def fetch_weather(session, lat, lon, start, end):
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": TIMEZONE,
    }
    response = session.get(API_URL, params=params, timeout=60)
    response.raise_for_status()
    return response.json()["daily"]


def to_rows(daily, location, lat, lon):
    """Turn the API's column lists into one tuple per day.

    Open-Meteo returns columns, e.g. {"time": [d1, d2], "temperature_2m_max": [t1, t2]},
    but a table wants rows: (d1, t1), (d2, t2). zip() pairs them up.
    """
    columns = [daily[name] for name in DAILY_VARIABLES]
    rows = []
    for day, *values in zip(daily["time"], *columns):
        if all(v is None for v in values):
            continue  # day not in the archive yet; a later run will fill it
        rows.append((day, location, lat, lon, *values))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, help="backfill from this date (YYYY-MM-DD)")
    args = parser.parse_args()

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    end = date.today() - timedelta(days=ARCHIVE_DELAY_DAYS)
    session = make_session()
    failed = []

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(CREATE_TABLE)
        conn.commit()
        for location, (lat, lon) in LOCATIONS.items():
            try:
                start = args.start or start_date_for(cur, location)
                if start > end:
                    log.info("%s is up to date", location)
                    continue
                log.info("Fetching %s weather from %s to %s", location, start, end)
                daily = fetch_weather(session, lat, lon, start, end)
                rows = to_rows(daily, location, lat, lon)
                if rows:
                    execute_values(cur, UPSERT, rows)
                conn.commit()  # save this town before moving to the next
                log.info("Loaded %d rows for %s", len(rows), location)
            except Exception:
                conn.rollback()  # undo only this town's partial work
                log.exception("Failed to load %s, moving on", location)
                failed.append(location)

    if failed:
        log.error("Finished with failures: %s", ", ".join(failed))
        sys.exit(1)  # non-zero exit tells a scheduler the run needs attention

if __name__ == "__main__":
    main()