"""Look closer at the fuel page: where the 2026 data comes from, and how old tables are laid out."""
import re
import sys

from bs4 import BeautifulSoup

html = open(sys.argv[1], encoding="utf-8").read()
soup = BeautifulSoup(html, "lxml")
tables = soup.find_all("table")

print("--- 1. Raw HTML of empty table 0 (first 600 characters):")
print(str(tables[0])[:600])

print("\n--- 2. Clues for JavaScript-loaded data:")
for pattern in ["iframe", "tablepress", "wpdatatable", "docs.google", "ninja_table", "admin-ajax", r"\.json", r"\.csv"]:
    hits = re.findall(rf".{{0,60}}{pattern}.{{0,80}}", html, flags=re.I)
    if hits:
        print(f"[{pattern}] {len(hits)} hit(s), e.g.: {hits[0].strip()}")

old = tables[2]
print("\n--- 3. Text just before table 2 (looking for its year):")
before = [s.strip() for s in old.find_all_previous(string=True, limit=20) if s.strip()]
print(before[:8])

print("\n--- 4. Table 2, first 3 rows, every cell:")
for tr in old.find_all("tr")[:3]:
    print([c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])])

print("\n--- 5. Table 2, every '95 ULP' row:")
for tr in old.find_all("tr"):
    cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
    if cells and cells[0].startswith("95 ULP"):
        print(cells)
