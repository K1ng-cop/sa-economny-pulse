"""List every table in a saved HTML page, with the heading above it, so we can design a parser."""
import sys
from io import StringIO

import pandas as pd
from bs4 import BeautifulSoup

html = open(sys.argv[1], encoding="utf-8").read()
soup = BeautifulSoup(html, "lxml")
tables = soup.find_all("table")
print(f"{len(tables)} <table> elements found")

for i, table in enumerate(tables):
    heading = table.find_previous(["h1", "h2", "h3", "h4", "h5", "h6", "strong"])
    heading_text = heading.get_text(" ", strip=True)[:70] if heading else None
    try:
        df = pd.read_html(StringIO(str(table)), header=None)[0]
    except ValueError:
        print(f"\n=== table {i}  EMPTY (skipped)  heading above: {heading_text!r}")
        continue
    print(f"\n=== table {i}  shape={df.shape}  heading above: {heading_text!r}")
    print("first row:   ", df.iloc[0, :6].tolist())
    print("first column:", df.iloc[:, 0].astype(str).tolist()[:20])
