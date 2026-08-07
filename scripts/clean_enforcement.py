"""
clean_enforcement.py — Clean and standardize new enforcement/procedure tables.

Input tables (DuckDB):
  - nasid_enforcement (raw text from NASID state pages)
  - bac_testing_laws (already clean CSV)
  - fars_bac_testing_2024 (already clean computed data)

Output:
  - DuckDB table: nasid_enforcement_clean (standardized boolean/categorical)
  - data/interim/nasid_enforcement_clean.parquet

Run: /opt/anaconda3/envs/data_projects/bin/python scripts/clean_enforcement.py
"""

from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).parent.parent
DB = ROOT / "data" / "project.duckdb"
INTERIM = ROOT / "data" / "interim"

con = duckdb.connect(str(DB))

# ═══════════════════════════════════════════════════════════════════════════════
# 1. CLEAN NASID ENFORCEMENT — standardize free-text to categorical/boolean
# ═══════════════════════════════════════════════════════════════════════════════
print("[1] Cleaning NASID enforcement data...")

nasid = con.sql("SELECT * FROM nasid_enforcement").fetchdf()
print(f"  Input: {len(nasid)} rows × {len(nasid.columns)} cols")

clean = nasid[["state_fips", "state_abbr", "state_name"]].copy()

# ── Sobriety Checkpoints ─────────────────────────────────────────────────────
def classify_checkpoints(val):
    if pd.isna(val):
        return None
    v = val.lower().strip()
    if "permitted" in v:
        return "permitted"
    elif "prohibited" in v:
        return "prohibited"
    elif "no statutory" in v:
        return "no_authority"
    elif "alternative" in v:
        return "alternative"
    return "unknown"

clean["checkpoints"] = nasid["sobriety_checkpoints"].apply(classify_checkpoints)
clean["checkpoints_permitted"] = (clean["checkpoints"] == "permitted").astype(int)

# ── No-Refusal Programs ──────────────────────────────────────────────────────
def classify_no_refusal(val):
    if pd.isna(val):
        return None
    v = val.lower().strip()
    if "utilizes" in v:
        return "active"
    elif "has legal authority" in v:
        return "authorized"
    elif "lacks" in v:
        return "not_authorized"
    return "unknown"

clean["no_refusal_status"] = nasid["no_refusal_programs"].apply(classify_no_refusal)
clean["no_refusal_active"] = (clean["no_refusal_status"] == "active").astype(int)

# ── PBT Laws ─────────────────────────────────────────────────────────────────
def classify_pbt(val):
    if pd.isna(val):
        return None
    v = val.lower().strip()
    if "statute permits" in v:
        return "authorized"
    elif "doesn't explicitly" in v or "not explicitly" in v:
        return "not_explicit"
    return "unknown"

clean["pbt_law"] = nasid["roadside_preliminary_breath_test_pbt_laws"].apply(classify_pbt)
clean["pbt_authorized"] = (clean["pbt_law"] == "authorized").astype(int)

# ── Ignition Interlocks ──────────────────────────────────────────────────────
def classify_iid(val):
    if pd.isna(val):
        return None
    v = val.lower().strip()
    if "mandatory all offender" in v:
        return "mandatory_all"
    elif "mandatory high-bac and repeat" in v:
        return "mandatory_high_bac_repeat"
    elif "mandatory repeat" in v:
        return "mandatory_repeat"
    elif "incentivized" in v:
        return "incentivized_first_mandatory_repeat"
    elif "discretionary" in v:
        return "discretionary"
    return "unknown"

clean["iid_mandate"] = nasid["ignition_interlocks"].apply(classify_iid)
clean["iid_all_offender"] = (clean["iid_mandate"] == "mandatory_all").astype(int)

# ── Felony DUI threshold ─────────────────────────────────────────────────────
def classify_felony(val):
    if pd.isna(val):
        return None
    v = val.lower().strip()
    if "no felony" in v:
        return None  # No felony DUI law
    elif "second" in v:
        return 2
    elif "third" in v:
        return 3
    elif "fourth" in v:
        return 4
    return None

clean["felony_dui_threshold"] = nasid["felony_dui"].apply(classify_felony)
clean["has_felony_dui"] = clean["felony_dui_threshold"].notna().astype(int)

# ── DUI Look-back Period ─────────────────────────────────────────────────────
def parse_lookback(val):
    if pd.isna(val):
        return None
    v = val.lower().strip()
    mapping = {
        "five years": 5, "seven years": 7, "ten years": 10,
        "twelve years": 12, "fifteen years": 15,
        "fifty five years": 55, "seventy five years": 75,
        "lifetime": 99,
    }
    for text, years in mapping.items():
        if text in v:
            return years
    return None

clean["lookback_years"] = nasid["dui_look_back_periods"].apply(parse_lookback)

# ── Enhanced BAC threshold ───────────────────────────────────────────────────
def parse_high_bac(val):
    if pd.isna(val):
        return None
    v = val.lower().strip()
    if "no enhanced" in v:
        return None
    try:
        return float(v)
    except ValueError:
        return None

clean["high_bac_threshold"] = nasid["enhanced_penalties_for_high_bac"].apply(parse_high_bac)
clean["has_high_bac_penalty"] = clean["high_bac_threshold"].notna().astype(int)

# ── Open Container ───────────────────────────────────────────────────────────
def classify_open_container(val):
    if pd.isna(val):
        return None
    v = val.lower().strip()
    if "in compliance" in v:
        return "federal_compliant"
    elif "does not meet" in v:
        return "non_compliant"
    return "unknown"

clean["open_container"] = nasid["open_container_alcohol"].apply(classify_open_container)
clean["open_container_compliant"] = (clean["open_container"] == "federal_compliant").astype(int)

# ── Testing Methods ──────────────────────────────────────────────────────────
clean["testing_methods"] = nasid["duid_implied_consent_testing_methods"]
clean["allows_oral_fluid"] = nasid["duid_implied_consent_testing_methods"].str.lower().str.contains("oral", na=False).astype(int)

# ── ALS/ALR enacted ─────────────────────────────────────────────────────────
clean["als_alr_enacted"] = nasid["administrative_license_suspension_revocation"].str.lower().str.contains("enacted", na=False).astype(int)

print(f"  Output: {len(clean)} rows × {len(clean.columns)} cols")
print(f"  Columns: {list(clean.columns)}")

# ── Quality checks ───────────────────────────────────────────────────────────
print("\n[2] Quality checks...")
print(f"  Checkpoints permitted: {clean['checkpoints_permitted'].sum()}/51")
print(f"  No-refusal active: {clean['no_refusal_active'].sum()}/51")
print(f"  PBT authorized: {clean['pbt_authorized'].sum()}/51")
print(f"  IID all-offender: {clean['iid_all_offender'].sum()}/51")
print(f"  Has felony DUI: {clean['has_felony_dui'].sum()}/51")
print(f"  Open container compliant: {clean['open_container_compliant'].sum()}/51")
print(f"  ALS/ALR enacted: {clean['als_alr_enacted'].sum()}/51")
print(f"  Allows oral fluid: {clean['allows_oral_fluid'].sum()}/51")

# Check for nulls in key fields
null_counts = clean.isnull().sum()
problem_cols = null_counts[null_counts > 5]
if not problem_cols.empty:
    print(f"\n  ⚠ Columns with >5 nulls: {problem_cols.to_dict()}")

# ── Save ─────────────────────────────────────────────────────────────────────
print("\n[3] Saving...")
pq_path = INTERIM / "nasid_enforcement_clean.parquet"
clean.to_parquet(pq_path, index=False, engine="pyarrow")
print(f"  → Parquet: {pq_path.name}")

con.execute("DROP TABLE IF EXISTS nasid_enforcement_clean")
con.execute("CREATE TABLE nasid_enforcement_clean AS SELECT * FROM clean")
print(f"  → DuckDB: nasid_enforcement_clean")

# ═══════════════════════════════════════════════════════════════════════════════
# 2. VERIFY bac_testing_laws and fars_bac_testing_2024 are clean
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[4] Verifying existing clean tables...")

bac_laws = con.sql("SELECT COUNT(*) FROM bac_testing_laws").fetchone()[0]
bac_rates = con.sql("SELECT COUNT(*) FROM fars_bac_testing_2024").fetchone()[0]
print(f"  bac_testing_laws: {bac_laws} rows ✓")
print(f"  fars_bac_testing_2024: {bac_rates} rows ✓")

# Quick null check on bac_testing_laws
nulls = con.sql("""
    SELECT 
        SUM(CASE WHEN mandatory_testing_law IS NULL THEN 1 ELSE 0 END) as null_mandate,
        SUM(CASE WHEN testing_scope IS NULL THEN 1 ELSE 0 END) as null_scope
    FROM bac_testing_laws
""").fetchdf()
print(f"  bac_testing_laws nulls: mandate={nulls['null_mandate'][0]}, scope={nulls['null_scope'][0]}")

# Quick null check on fars_bac_testing_2024
nulls2 = con.sql("""
    SELECT 
        SUM(CASE WHEN pct_bac_known_killed IS NULL THEN 1 ELSE 0 END) as null_killed,
        SUM(CASE WHEN pct_bac_known_all IS NULL THEN 1 ELSE 0 END) as null_all
    FROM fars_bac_testing_2024
""").fetchdf()
print(f"  fars_bac_testing nulls: killed={nulls2['null_killed'][0]}, all={nulls2['null_all'][0]}")

con.close()
print("\n✓ Cleaning complete.")
