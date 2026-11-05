"""Load the Stats SA CPI (COICOP) Excel file into raw.cpi_series and raw.cpi_values.

Stats SA publishes CPI as a file, not an API, so this loader reads from a landing folder.
Download the latest "CPI(COICOP) from Jan 2008" Excel file, unzip it into
data/landing/cpi/, then run from the repo root:
    python -m extract.cpi                 # loads the newest file in the landing folder
    python -m extract.cpi --file <path>   # loads a specific file
"""
import argparse
import logging
import re
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from psycopg2.extras import execute_values

from extract.db import get_connection

LANDING_DIR = Path("data/landing/cpi")
FILE_GLOB = "*CPI (COICOP)*.xlsx"
RELEASE_RE = re.compile(r"\((\d{6})\)")  # "(202609)" in the file name = data up to Sep 2026
MONTH_COL_RE = re.compile(r"^MO(\d{2})(\d{4})$")  # "MO092026" = Sep 2026
# Stats SA header fields. Kept under their source names in raw; dbt staging renames them.
# H03 series code, H04-H06 descriptions, H13 area, H17 unit, H18 base, H24 start, H25 frequency
HEADER_COLS = ["H01", "H02", "H03", "H04", "H05", "H06", "H13", "H17", "H18", "H24", "H25"]

log = logging.getLogger("cpi")

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS raw.cpi_series (
    h03 TEXT PRIMARY KEY,
    h01 TEXT, h02 TEXT, h04 TEXT, h05 TEXT, h06 TEXT,
    h13 TEXT, h17 TEXT, h18 TEXT, h24 TEXT, h25 TEXT,
    source_file    TEXT        NOT NULL,
    release_period TEXT,
    _loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS raw.cpi_values (
    h03         TEXT        NOT NULL,
    period      DATE        NOT NULL,
    value       NUMERIC     NOT NULL,
    source_file TEXT        NOT NULL,
    _loaded_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (h03, period)
);
"""

UPSERT_SERIES = """
INSERT INTO raw.cpi_series (h03, h01, h02, h04, h05, h06, h13, h17, h18, h24, h25, source_file, release_period)
VALUES %s
ON CONFLICT (h03) DO UPDATE SET
    h01 = EXCLUDED.h01, h02 = EXCLUDED.h02, h04 = EXCLUDED.h04, h05 = EXCLUDED.h05,
    h06 = EXCLUDED.h06, h13 = EXCLUDED.h13, h17 = EXCLUDED.h17, h18 = EXCLUDED.h18,
    h24 = EXCLUDED.h24, h25 = EXCLUDED.h25,
    source_file = EXCLUDED.source_file, release_period = EXCLUDED.release_period,
    _loaded_at = now();
"""

UPSERT_VALUES = """
INSERT INTO raw.cpi_values (h03, period, value, source_file)
VALUES %s
ON CONFLICT (h03, period) DO UPDATE SET
    value = EXCLUDED.value, source_file = EXCLUDED.source_file, _loaded_at = now();
"""


def release_of(path):
    match = RELEASE_RE.search(path.name)
    return match.group(1) if match else ""


def newest_file():
    files = sorted(LANDING_DIR.glob(FILE_GLOB), key=release_of)
    if not files:
        raise SystemExit(f"No file matching {FILE_GLOB!r} in {LANDING_DIR}/ - download and unzip it first")
    return files[-1]


def read_and_validate(path):
    """Read the sheet and stop early, with a clear message, if the layout isn't what we expect."""
    df = pd.read_excel(path, sheet_name=0, dtype={c: str for c in HEADER_COLS})

    missing = [c for c in HEADER_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Header columns missing from file: {missing}")

    month_cols = [c for c in df.columns if MONTH_COL_RE.match(str(c))]
    if not month_cols:
        raise ValueError("No MOmmyyyy month columns found - has the layout changed?")

        df = df.dropna(subset=["H03"])  # skip blank or footnote rows

    # Stats SA lists some series twice, under different headings (e.g. "CPI Headline" and
    # "All Items"). That's fine only if every monthly value matches; then keep the first listing.
    repeated = df[df["H03"].duplicated(keep=False)]
    if not repeated.empty:
        conflicting = [
            code for code, rows in repeated.groupby("H03")
            if len(rows[month_cols].drop_duplicates()) > 1
        ]
        if conflicting:
            raise ValueError(f"Series codes repeat with DIFFERENT values: {conflicting[:10]}")
        log.warning(
            "Dropped %d repeated listings of %s (values identical in every month; kept first listing)",
            df["H03"].duplicated().sum(), sorted(repeated["H03"].unique()),
        )
        df = df.drop_duplicates(subset="H03", keep="first")

    return df, month_cols


def to_long(df, month_cols):
    """Unpivot one-column-per-month into one row per series per month."""
    long = df.melt(id_vars="H03", value_vars=month_cols, var_name="month_col", value_name="value")
    month_year = long["month_col"].str.extract(MONTH_COL_RE)
    long["period"] = pd.to_datetime(month_year[1] + "-" + month_year[0] + "-01").dt.date
    long["value"] = pd.to_numeric(long["value"], errors="coerce")  # ".." or blanks become NaN
    return long.dropna(subset=["value"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, help="load this file instead of the newest one")
    args = parser.parse_args()

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    path = args.file or newest_file()
    release = release_of(path)
    log.info("Reading %s (release %s)", path.name, release or "unknown")

    df, month_cols = read_and_validate(path)
    long = to_long(df, month_cols)
    log.info("%d series, %d months, %d values", len(df), len(month_cols), len(long))

    meta = df[HEADER_COLS].astype(object).where(df[HEADER_COLS].notna(), None)
    series_rows = [
        (r.H03, r.H01, r.H02, r.H04, r.H05, r.H06, r.H13, r.H17, r.H18, r.H24, r.H25, path.name, release)
        for r in meta.itertuples(index=False)
    ]
    value_rows = list(zip(long["H03"], long["period"], long["value"].astype(float), [path.name] * len(long)))

    # A file is a full snapshot, so load it all-or-nothing: one transaction
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(CREATE_TABLES)
        execute_values(cur, UPSERT_SERIES, series_rows)
        execute_values(cur, UPSERT_VALUES, value_rows, page_size=5000)
    log.info("Loaded %d series and %d values", len(series_rows), len(value_rows))


if __name__ == "__main__":
    main()
