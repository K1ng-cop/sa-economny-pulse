"""Load South African fuel prices from the Fuels Industry Association page into raw.fuel_prices.

There's no API, so this saves a dated copy of the web page into data/landing/fuel/ and parses
the tables in it. Run from the repo root:
    python -m extract.fuel --download   # save today's page, then load it
    python -m extract.fuel              # load the newest page already saved
"""
import argparse
import logging
import re
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from psycopg2.extras import execute_values

from extract.db import get_connection

PAGE_URL = "https://fuelsindustry.org.za/consumer-information/fuel-prices-current-past/"
USER_AGENT = "sa-economy-pulse/0.1 (personal portfolio project)"
LANDING_DIR = Path("data/landing/fuel")
MIN_YEAR = 2023  # the project uses 3 years of history
REGIONS = {"COASTAL": "coastal", "GAUTENG": "gauteng"}
PRODUCT_RE = re.compile(r"\((c/l|c/kg)\)")  # product rows carry their unit, e.g. "95 ULP (c/l) *"

log = logging.getLogger("fuel")

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS raw.fuel_prices (
    effective_date DATE        NOT NULL,
    region         TEXT        NOT NULL,
    product        TEXT        NOT NULL,
    unit           TEXT        NOT NULL,
    price_cents    NUMERIC     NOT NULL,
    source_file    TEXT        NOT NULL,
    _loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (effective_date, region, product)
);
"""

UPSERT = """
INSERT INTO raw.fuel_prices (effective_date, region, product, unit, price_cents, source_file)
VALUES %s
ON CONFLICT (effective_date, region, product) DO UPDATE SET
    unit = EXCLUDED.unit, price_cents = EXCLUDED.price_cents,
    source_file = EXCLUDED.source_file, _loaded_at = now();
"""


def download_page():
    LANDING_DIR.mkdir(parents=True, exist_ok=True)
    response = requests.get(PAGE_URL, headers={"User-Agent": USER_AGENT}, timeout=60)
    response.raise_for_status()
    path = LANDING_DIR / f"fuel_prices_{date.today():%Y%m%d}.html"
    path.write_text(response.text, encoding="utf-8")
    log.info("Saved %s", path)
    return path


def newest_file():
    files = sorted(LANDING_DIR.glob("fuel_prices_*.html"))
    if not files:
        raise SystemExit(f"No saved page in {LANDING_DIR}/ - run with --download first")
    return files[-1]


def cells(tr):
    return [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]


def to_cents(text):
    text = text.strip().replace(" ", "")
    return float(text.replace(",", ".")) if text else None  # "2028,00" -> 2028.0


def clean_product(label):
    """'95 ULP (c/l) *' -> ('95 ULP', 'c/l')"""
    unit = PRODUCT_RE.search(label).group(1)
    name = PRODUCT_RE.split(label)[0].strip()
    return name, unit


def parse_current_year(rows):
    """The current year's tables: header 'Products | 1-Jan-26 | 4-Feb-26 ...', one table per region."""
    dates = [datetime.strptime(h, "%d-%b-%y").date() if h else None for h in rows[0][1:]]
    products = [r for r in rows[1:] if r and PRODUCT_RE.search(r[0])]
    # 93 octane is only sold inland, so the table with 93 rows is Gauteng
    region = "gauteng" if any(r[0].startswith("93") for r in products) else "coastal"
    return [(region, r, dates) for r in products]


def parse_archive_year(rows):
    """Archive tables: header '2025 | 01 Jan | 05 Feb ...', COASTAL and GAUTENG rows split the table."""
    year = int(rows[0][0])
    dates = [datetime.strptime(f"{h} {year}", "%d %b %Y").date() if h else None for h in rows[0][1:]]
    out, region = [], None
    for r in rows[1:]:
        if not r or not r[0]:
            continue
        label = r[0].upper()
        if label.startswith("NOTES"):
            break
        if label in REGIONS:
            region = REGIONS[label]
        elif PRODUCT_RE.search(r[0]):
            if region is None:
                raise ValueError(f"{year}: product row {r[0]!r} before any COASTAL/GAUTENG row")
            out.append((region, r, dates))
    return out


def parse_page(html):
    soup = BeautifulSoup(html, "lxml")
    records = []
    for table in soup.find_all("table"):
        rows = [cells(tr) for tr in table.find_all("tr")]
        if not rows or not rows[0]:
            continue
        first = rows[0][0]
        if first == "Products":
            parsed = parse_current_year(rows)
        elif re.fullmatch(r"\d{4}", first) and int(first) >= MIN_YEAR:
            parsed = parse_archive_year(rows)
        else:
            continue  # older years or layout tables
        for region, row, dates in parsed:
            product, unit = clean_product(row[0])
            for effective_date, value in zip(dates, row[1:]):
                price = to_cents(value)
                if effective_date and price is not None:
                    records.append((effective_date, region, product, unit, price))
    return records

MAX_REJECTED = 5  # a few typos in the source are fine; more probably means the layout changed

def validate(records):
    """Fail on structural problems; set aside individual out-of-range prices."""
    if not records:
        raise ValueError("No prices parsed - has the page layout changed?")
    keys = [(d, r, p) for d, r, p, _, _ in records]
    if len(keys) != len(set(keys)):
        raise ValueError("The same date/region/product was parsed twice")
    regions = {r for _, r, _, _, _ in records}
    if regions != {"coastal", "gauteng"}:
        raise ValueError(f"Expected both regions, got {sorted(regions)}")

    good = [rec for rec in records if 500 <= rec[4] <= 10000]  # R5 to R100 a litre or kg
    rejected = [rec for rec in records if rec not in good]
    for rec in rejected:
        log.warning("Rejected out-of-range price (likely a typo on the source page): %s", rec)
    if len(rejected) > MAX_REJECTED:
        raise ValueError(f"{len(rejected)} out-of-range prices - check the page layout before loading")
    return good


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="save today's page before loading")
    args = parser.parse_args()

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    path = download_page() if args.download else newest_file()
    records = parse_page(path.read_text(encoding="utf-8"))
    records = validate(records)
    dates = sorted({rec[0] for rec in records})
    log.info("Parsed %d prices from %s to %s", len(records), dates[0], dates[-1])

    rows = [(*rec, path.name) for rec in records]
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(CREATE_TABLE)
        execute_values(cur, UPSERT, rows)
    log.info("Loaded %d rows from %s", len(rows), path.name)


if __name__ == "__main__":
    main()