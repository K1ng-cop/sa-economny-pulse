"""Print the shape of an Excel file so we can design its loader."""
import sys

import pandas as pd

path = sys.argv[1]
sheets = pd.read_excel(path, sheet_name=None, header=0)

for name, df in sheets.items():
    print(f"\n=== sheet: {name!r}  rows={len(df)}  columns={len(df.columns)}")
    print("first 30 columns:", list(df.columns[:30]))
    print("last 5 columns: ", list(df.columns[-5:]))
    print(df.iloc[:3, :10].to_string())
    if "H03" in df.columns:
        print("unique H03 codes:", df["H03"].nunique(), "of", len(df), "rows")
