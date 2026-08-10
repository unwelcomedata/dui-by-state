"""
rename_columns_v3.py — Rename mislabeled 'alcohol' columns to 'impaired' in DuckDB.

FARS raw data uses drimpair code 9 which captures ANY impairment (alcohol + drugs + meds).
These columns were incorrectly named 'alcohol_*' and should be 'impaired_*'.
NHTSA imputed columns (BAC >= .08 only) correctly keep 'alcohol' in the name.

Run this AFTER disconnecting the DuckDB VS Code extension (it holds a write lock).

Run: /opt/anaconda3/envs/data_projects/bin/python scripts/rename_columns_v3.py
"""

import duckdb
from pathlib import Path

DB = Path(__file__).parent.parent / "data" / "project.duckdb"

print(f"Connecting to {DB}...")
con = duckdb.connect(str(DB))

# ── fars_2024 (raw ingest table) ──
print("\n[1] Renaming fars_2024 columns...")
con.execute("ALTER TABLE fars_2024 RENAME COLUMN alcohol_crashes TO impaired_crashes")
con.execute("ALTER TABLE fars_2024 RENAME COLUMN alcohol_fatalities TO impaired_fatalities")
con.execute("ALTER TABLE fars_2024 RENAME COLUMN pct_fatalities_alcohol TO pct_fatalities_impaired")
print("  ✓ fars_2024: alcohol_* → impaired_*")

# ── fars_trends (raw ingest table) ──
print("\n[2] Renaming fars_trends columns...")
con.execute("ALTER TABLE fars_trends RENAME COLUMN alcohol_crashes TO impaired_crashes")
con.execute("ALTER TABLE fars_trends RENAME COLUMN alcohol_fatalities TO impaired_fatalities")
con.execute("ALTER TABLE fars_trends RENAME COLUMN pct_fatalities_alcohol TO pct_fatalities_impaired")
print("  ✓ fars_trends: alcohol_* → impaired_*")

# ── states (master reference) ──
print("\n[3] Renaming states columns...")
con.execute("ALTER TABLE states RENAME COLUMN alcohol_fatalities_2024 TO impaired_fatalities_fars_2024")
con.execute("ALTER TABLE states RENAME COLUMN pct_alcohol_2024 TO pct_impaired_fars_2024")
print("  ✓ states: alcohol_fatalities_2024 → impaired_fatalities_fars_2024")
print("  ✓ states: pct_alcohol_2024 → pct_impaired_fars_2024")

# ── Verify ──
print("\n[4] Verification...")
for table in ['fars_2024', 'fars_trends', 'states']:
    cols = con.sql(f"DESCRIBE {table}").df()['column_name'].tolist()
    alcohol_cols = [c for c in cols if 'alcohol' in c.lower()]
    impaired_cols = [c for c in cols if 'impaired' in c.lower()]
    print(f"  {table}: {len(alcohol_cols)} 'alcohol' cols, {len(impaired_cols)} 'impaired' cols")
    if alcohol_cols:
        print(f"    ⚠ Remaining alcohol cols: {alcohol_cols}")

con.close()
print("\n✓ Done. DuckDB columns renamed.")
