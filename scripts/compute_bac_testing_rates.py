"""
compute_bac_testing_rates.py — Extract BAC testing rates by state from FARS 2024.

Uses person.csv from the FARS 2024 national zip. Computes:
- % of drivers in fatal crashes with known BAC test results
- Broken out by killed vs surviving drivers
- Test type breakdown (blood, breath, vitreous, PBT)

Output:
- data/interim/fars_bac_testing_2024.parquet
- DuckDB table: fars_bac_testing_2024

FARS ALC_STATUS codes:
  0 = Test Not Given
  2 = Test Given (BAC result known)
  8 = Not Reported
  9 = Unknown if Tested

Run: /opt/anaconda3/envs/data_projects/bin/python scripts/compute_bac_testing_rates.py
"""

import zipfile
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).parent.parent
ZPATH = ROOT / "data" / "raw" / "fars_2024.zip"
INTERIM = ROOT / "data" / "interim"
DB = ROOT / "data" / "project.duckdb"

print("[1] Loading person.csv from FARS 2024 zip...")
with zipfile.ZipFile(ZPATH) as zf:
    with zf.open("FARS2024NationalCSV/person.csv") as f:
        person = pd.read_csv(
            f, encoding="latin-1", low_memory=False,
            usecols=["STATE", "ST_CASE", "VEH_NO", "PER_NO", "PER_TYP",
                     "INJ_SEV", "ALC_STATUS", "ALC_RES", "ATST_TYP"]
        )

person.columns = [c.lower() for c in person.columns]
print(f"  Total person records: {len(person):,}")

# Filter to drivers only (per_typ=1)
drivers = person[person["per_typ"] == 1].copy()
print(f"  Drivers in fatal crashes: {len(drivers):,}")

# Classify
drivers["killed"] = (drivers["inj_sev"] == 4).astype(int)
drivers["bac_known"] = (drivers["alc_status"] == 2).astype(int)
drivers["test_not_given"] = (drivers["alc_status"] == 0).astype(int)

# ── All drivers by state ─────────────────────────────────────────────────────
print("\n[2] Aggregating by state...")
all_agg = drivers.groupby("state").agg(
    total_drivers=("per_no", "count"),
    drivers_bac_known=("bac_known", "sum"),
    drivers_test_not_given=("test_not_given", "sum"),
).reset_index()
all_agg["pct_bac_known_all"] = (
    all_agg["drivers_bac_known"] * 100.0 / all_agg["total_drivers"]
).round(1)

# ── Killed drivers ───────────────────────────────────────────────────────────
killed = drivers[drivers["killed"] == 1]
killed_agg = killed.groupby("state").agg(
    killed_drivers=("per_no", "count"),
    killed_bac_known=("bac_known", "sum"),
).reset_index()
killed_agg["pct_bac_known_killed"] = (
    killed_agg["killed_bac_known"] * 100.0 / killed_agg["killed_drivers"]
).round(1)

# ── Surviving drivers ────────────────────────────────────────────────────────
surviving = drivers[drivers["killed"] == 0]
surv_agg = surviving.groupby("state").agg(
    surviving_drivers=("per_no", "count"),
    surviving_bac_known=("bac_known", "sum"),
).reset_index()
surv_agg["pct_bac_known_surviving"] = (
    surv_agg["surviving_bac_known"] * 100.0 / surv_agg["surviving_drivers"]
).round(1)

# ── Test type breakdown (for tested drivers only) ────────────────────────────
tested = drivers[drivers["alc_status"] == 2].copy()
test_type_counts = tested.groupby("state")["atst_typ"].apply(
    lambda x: pd.Series({
        "n_blood": (x == 1).sum(),
        "n_breath": (x == 2).sum(),
        "n_urine": (x == 3).sum(),
        "n_vitreous": (x == 4).sum(),
        "n_pbt": (x == 10).sum(),
        "n_other_test": x[~x.isin([1, 2, 3, 4, 10])].count(),
    })
).unstack(fill_value=0).reset_index()

test_type_counts["n_total_tests"] = (
    test_type_counts["n_blood"] + test_type_counts["n_breath"] +
    test_type_counts["n_urine"] + test_type_counts["n_vitreous"] +
    test_type_counts["n_pbt"] + test_type_counts["n_other_test"]
)
test_type_counts["pct_blood_test"] = (
    test_type_counts["n_blood"] * 100.0 / test_type_counts["n_total_tests"]
).round(1)

# ── Merge ────────────────────────────────────────────────────────────────────
print("\n[3] Merging and saving...")
result = (
    all_agg
    .merge(killed_agg, on="state")
    .merge(surv_agg, on="state", how="left")
    .merge(test_type_counts[["state", "n_blood", "n_breath", "n_vitreous",
                             "n_pbt", "n_other_test", "pct_blood_test"]],
           on="state", how="left")
)
result["state_fips"] = result["state"].apply(lambda x: f"{int(x):02d}")
result = result.drop(columns=["state"])

# Reorder columns
col_order = [
    "state_fips", "total_drivers", "drivers_bac_known", "drivers_test_not_given",
    "pct_bac_known_all", "killed_drivers", "killed_bac_known", "pct_bac_known_killed",
    "surviving_drivers", "surviving_bac_known", "pct_bac_known_surviving",
    "n_blood", "n_breath", "n_vitreous", "n_pbt", "n_other_test", "pct_blood_test",
]
result = result[col_order]

# Save parquet
out_path = INTERIM / "fars_bac_testing_2024.parquet"
result.to_parquet(out_path, index=False, engine="pyarrow")
print(f"  → Parquet: {out_path.name} ({len(result)} rows × {len(result.columns)} cols)")

# Save to DuckDB
con = duckdb.connect(str(DB))
con.execute("DROP TABLE IF EXISTS fars_bac_testing_2024")
con.execute("CREATE TABLE fars_bac_testing_2024 AS SELECT * FROM result")
con.close()
print(f"  → DuckDB: fars_bac_testing_2024")

# ── Summary stats ────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("NATIONAL AVERAGES (mean across states):")
print(f"  All drivers BAC known:       {result['pct_bac_known_all'].mean():.1f}%")
print(f"  Killed drivers BAC known:    {result['pct_bac_known_killed'].mean():.1f}%")
print(f"  Surviving drivers BAC known: {result['pct_bac_known_surviving'].mean():.1f}%")
print(f"  Blood test share (of tested):{result['pct_blood_test'].mean():.1f}%")
print()
print("TOP 5 — highest BAC testing rate (killed drivers):")
top5 = result.nlargest(5, "pct_bac_known_killed")
print(top5[["state_fips", "killed_drivers", "pct_bac_known_killed", "pct_bac_known_all"]].to_string(index=False))
print()
print("BOTTOM 5 — lowest BAC testing rate (killed drivers):")
bot5 = result.nsmallest(5, "pct_bac_known_killed")
print(bot5[["state_fips", "killed_drivers", "pct_bac_known_killed", "pct_bac_known_all"]].to_string(index=False))
print()
print("SOUTH CAROLINA (FIPS 45):")
sc = result[result["state_fips"] == "45"]
if not sc.empty:
    print(sc.to_string(index=False))
