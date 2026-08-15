"""
prepare_export_v4.py — Build the v4 master export dataset.

Changes from v3:
  - Removed non-law/penalty/fatality columns: alcohol consumption, DUI arrests,
    speed limits, VMT, prior DWI crash characteristics
  - Added vehicle impound/seizure/forfeiture columns from vehicle_impound_laws table
  - Kept VMT only for fatality rate calculation (not as standalone column)
  - Focus: laws, penalties, enforcement mechanisms, fatality outcomes

Output:
  - export/dui_by_state_v4.csv
  - export/dui_by_state_v4.xlsx
  - export/dui_by_state_v4.parquet
  - export/dui_by_state_v4_codebook.md
  - data/processed/dui_master_states_v4.parquet

Run: .venv/bin/python scripts/prepare_export_v4.py
"""

from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).parent.parent
DB = ROOT / "data" / "project.duckdb"
EXPORT = ROOT / "export"
PROCESSED = ROOT / "data" / "processed"

con = duckdb.connect(str(DB), read_only=True)

# ═══════════════════════════════════════════════════════════════════════════════
# BUILD MASTER TABLE VIA SQL JOIN
# ═══════════════════════════════════════════════════════════════════════════════
print("[1] Building master table via DuckDB join...")

master_sql = """
SELECT
    -- ── Identity ────────────────────────────────────────────────────────────
    s.state_fips,
    s.state_abbr,
    s.state_name,
    s.region,
    s.division,
    s.pop_2024,

    -- ── Fatality outcomes (FARS raw + NHTSA imputed) ────────────────────────
    s.traffic_fatalities_2024,
    s.impaired_fatalities_fars_2024 AS impaired_fatalities_fars_raw,
    n.alcohol_impaired_fatalities_2024 AS alcohol_fatalities_nhtsa_imputed,
    n.total_fatalities_2024 AS total_fatalities_nhtsa,
    s.pct_impaired_fars_2024 AS pct_impaired_fars_raw,
    n.pct_alcohol_impaired_2024 AS pct_alcohol_nhtsa_imputed,
    n.high_bac_fatalities_2024,
    n.pct_high_bac_2024,

    -- ── Per-capita rates ────────────────────────────────────────────────────
    ROUND(s.traffic_fatalities_2024 * 100000.0 / s.pop_2024, 2) AS total_fatality_rate_per_100k,
    ROUND(n.alcohol_impaired_fatalities_2024 * 100000.0 / s.pop_2024, 2) AS alcohol_fatality_rate_per_100k,

    -- ── BAC testing rates (from FARS person.csv) ────────────────────────────
    bt.pct_bac_known_killed,
    bt.pct_bac_known_all AS pct_bac_known_all_drivers,
    bt.pct_bac_known_surviving,
    bt.pct_blood_test,

    -- ── BAC testing laws ────────────────────────────────────────────────────
    bl.mandatory_testing_law,
    bl.testing_scope,
    bl.testing_authority,

    -- ── Enforcement procedures (NASID cleaned) ──────────────────────────────
    ec.checkpoints_permitted,
    ec.no_refusal_status,
    ec.no_refusal_active,
    ec.pbt_authorized,
    ec.iid_mandate,
    ec.iid_all_offender,
    ec.felony_dui_threshold,
    ec.has_felony_dui,
    ec.lookback_years,
    ec.high_bac_threshold,
    ec.has_high_bac_penalty,
    ec.open_container_compliant,
    ec.allows_oral_fluid,
    ec.als_alr_enacted,
    ec.testing_methods,

    -- ── Other enforcement ───────────────────────────────────────────────────
    de.criminal_refusal_penalty,
    de.bac_limit,
    cs.first_offense_felony,

    -- ── Vehicle sanctions (NEW in v4) ───────────────────────────────────────
    vi.vehicle_impound_law,
    vi.impound_trigger,
    vi.impound_mandatory,
    vi.vehicle_forfeiture_law,
    vi.forfeiture_trigger,
    vi.plate_impound_law,
    CASE WHEN vi.vehicle_impound_law = 'yes' AND vi.impound_mandatory = 'mandatory' THEN 1 ELSE 0 END AS has_mandatory_impound

FROM states s
LEFT JOIN nhtsa_imputed_2024 n ON s.state_name = n.state_name
LEFT JOIN fars_bac_testing_2024 bt ON s.state_fips = bt.state_fips
LEFT JOIN bac_testing_laws bl ON s.state_fips = bl.state_fips
LEFT JOIN nasid_enforcement_clean ec ON s.state_fips = ec.state_fips
LEFT JOIN dui_enforcement de ON s.state_fips = de.state_fips
LEFT JOIN dui_criminal_status_clean cs ON s.state_fips = cs.state_fips
LEFT JOIN vehicle_impound_laws vi ON s.state_fips = vi.state_fips
ORDER BY s.state_fips
"""

master = con.sql(master_sql).fetchdf()
con.close()

print(f"  Master table: {len(master)} rows × {len(master.columns)} cols")

# ═══════════════════════════════════════════════════════════════════════════════
# QUALITY CHECKS
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[2] Quality checks...")
assert len(master) == 51, f"Expected 51 rows, got {len(master)}"

critical_cols = ["state_fips", "state_name", "pop_2024", "traffic_fatalities_2024",
                 "checkpoints_permitted", "has_mandatory_impound", "vehicle_impound_law"]
for col in critical_cols:
    nulls = master[col].isnull().sum()
    if nulls > 0:
        print(f"  ⚠ {col}: {nulls} nulls")
    else:
        print(f"  ✓ {col}: no nulls")

null_pcts = (master.isnull().sum() / len(master) * 100).round(1)
high_nulls = null_pcts[null_pcts > 10]
if not high_nulls.empty:
    print(f"\n  Columns with >10% null:")
    for col, pct in high_nulls.items():
        print(f"    {col}: {pct}%")

# ═══════════════════════════════════════════════════════════════════════════════
# EXPORT
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[3] Exporting...")

EXPORT.mkdir(parents=True, exist_ok=True)
PROCESSED.mkdir(parents=True, exist_ok=True)

processed_path = PROCESSED / "dui_master_states_v4.parquet"
master.to_parquet(processed_path, index=False, engine="pyarrow")
print(f"  → {processed_path.name}")

csv_path = EXPORT / "dui_by_state_v4.csv"
master.to_csv(csv_path, index=False)
print(f"  → {csv_path.name}")

pq_path = EXPORT / "dui_by_state_v4.parquet"
master.to_parquet(pq_path, index=False, engine="pyarrow")
print(f"  → {pq_path.name}")

xlsx_path = EXPORT / "dui_by_state_v4.xlsx"
master.to_excel(xlsx_path, index=False, sheet_name="dui_by_state_v4", engine="openpyxl")
print(f"  → {xlsx_path.name}")

# ═══════════════════════════════════════════════════════════════════════════════
# CODEBOOK
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[4] Writing codebook...")

codebook = f"""# Codebook — dui_by_state_v4

**Dataset:** DUI Laws, Penalties, Enforcement & Fatality Outcomes by State (2024)
**Rows:** {len(master)} (50 states + District of Columbia)
**Columns:** {len(master.columns)}
**Created:** 2026-08-15
**Author:** @unwelcomedata
**Changes from v3:** Removed non-law columns (consumption, arrests, speed/VMT, prior DWI). Added vehicle impound/forfeiture/plate impound columns. Focused scope: laws, penalties, enforcement mechanisms, fatality outcomes.

---

## Identity & Geography

| Column | Type | Description |
|--------|------|-------------|
| state_fips | str | 2-digit FIPS code |
| state_abbr | str | 2-letter state abbreviation |
| state_name | str | Full state name |
| region | str | Census region (Northeast, Midwest, South, West) |
| division | str | Census division (9 categories) |
| pop_2024 | int | Census population estimate, July 2024 |

## Fatality Outcomes

| Column | Type | Description |
|--------|------|-------------|
| traffic_fatalities_2024 | int | Total traffic fatalities (FARS 2024) |
| impaired_fatalities_fars_raw | int | Impaired-driving fatalities, FARS raw coding (drimpair code 9: alcohol + drugs + medication) |
| alcohol_fatalities_nhtsa_imputed | int | Alcohol-impaired fatalities (BAC>=.08 only), NHTSA statistical imputation |
| total_fatalities_nhtsa | int | Total fatalities per NHTSA imputed report |
| pct_impaired_fars_raw | float | % traffic deaths with any impairment involvement (FARS raw) |
| pct_alcohol_nhtsa_imputed | int | % traffic deaths alcohol-impaired (NHTSA imputed, BAC>=.08 only) |
| high_bac_fatalities_2024 | int | High-BAC fatalities (BAC>=.15), NHTSA imputed |
| pct_high_bac_2024 | int | % traffic deaths involving high-BAC driver |

## Per-Capita Rates

| Column | Type | Description |
|--------|------|-------------|
| total_fatality_rate_per_100k | float | Total traffic deaths per 100,000 population |
| alcohol_fatality_rate_per_100k | float | Alcohol-impaired deaths per 100,000 population (NHTSA imputed) |

## BAC Testing Rates (FARS 2024 Person File)

| Column | Type | Description |
|--------|------|-------------|
| pct_bac_known_killed | float | % of killed drivers with known BAC test result |
| pct_bac_known_all_drivers | float | % of all drivers in fatal crashes with known BAC |
| pct_bac_known_surviving | float | % of surviving drivers with known BAC |
| pct_blood_test | float | % of tested drivers whose test was blood (vs breath/PBT) |

## BAC Testing Laws

| Column | Type | Description |
|--------|------|-------------|
| mandatory_testing_law | str | "yes" if state requires BAC testing of fatally injured drivers by statute |
| testing_scope | str | Scope: all_fatally_injured, probable_cause, serious_injury_or_fatal |
| testing_authority | str | Who conducts: coroner, medical_examiner, law_enforcement |

## Enforcement Procedures (NASID)

| Column | Type | Description |
|--------|------|-------------|
| checkpoints_permitted | int | 1 = sobriety checkpoints legal and permitted |
| no_refusal_status | str | No-refusal program status: active, authorized, not_authorized |
| no_refusal_active | int | 1 = state actively uses no-refusal programs |
| pbt_authorized | int | 1 = statute explicitly permits roadside preliminary breath tests |
| iid_mandate | str | IID mandate level: mandatory_all, mandatory_high_bac_repeat, etc. |
| iid_all_offender | int | 1 = IID mandatory for all offenders including first offense |
| felony_dui_threshold | float | Number of offenses before DUI becomes felony (2, 3, or 4) |
| has_felony_dui | int | 1 = state has a felony DUI law |
| lookback_years | int | Years state looks back for prior offenses (5-99, 99=lifetime) |
| high_bac_threshold | float | BAC level triggering enhanced penalties (0.15-0.20) |
| has_high_bac_penalty | int | 1 = state has enhanced penalties for high-BAC |
| open_container_compliant | int | 1 = meets federal open container requirements |
| allows_oral_fluid | int | 1 = oral fluid testing permitted under implied consent |
| als_alr_enacted | int | 1 = administrative license suspension/revocation law enacted |
| testing_methods | str | Implied consent testing methods allowed (Blood, Breath, etc.) |

## Other Enforcement

| Column | Type | Description |
|--------|------|-------------|
| criminal_refusal_penalty | int | 1 = criminal (not just administrative) penalty for test refusal |
| bac_limit | float | Per se BAC limit (0.08 all states except UT 0.05) |
| first_offense_felony | float | 1 = first DUI offense can be charged as felony |

## Vehicle Sanctions (NEW in v4)

| Column | Type | Description |
|--------|------|-------------|
| vehicle_impound_law | str | "yes" if state has a statutory vehicle impound/seizure law for DUI |
| impound_trigger | str | What triggers impound: all_dui_arrest, extreme_or_aggravated, repeat_conviction, repeat_or_suspended, dui_while_suspended, dui_while_revoked, all_dui_conviction, aggravated_or_repeat, repeat_or_high_bac |
| impound_mandatory | str | "mandatory" or "discretionary" — whether impound is automatic or at officer/court discretion |
| vehicle_forfeiture_law | str | "yes" if state allows permanent vehicle forfeiture/seizure for DUI |
| forfeiture_trigger | str | What triggers forfeiture: repeat_conviction, dui_while_revoked, statutory_summary_suspension |
| plate_impound_law | str | "yes" if state has license plate impoundment for DUI |
| has_mandatory_impound | int | 1 = state has mandatory vehicle impound (vehicle_impound_law=yes AND impound_mandatory=mandatory) |

---

## Data Caveats

1. **NHTSA imputed vs FARS raw:** NHTSA imputed (BAC>=.08) uses statistical modeling for untested drivers — alcohol only. FARS raw (drimpair code 9) captures any impairment including drugs/medication — broader but no imputation.
2. **BAC testing rates vary:** From 10% (MS) to 98% (VT) for killed drivers.
3. **Mandatory testing != high testing:** CA, ID, OK have mandatory laws but <60% compliance.
4. **Lookback 99 = lifetime:** Some states never stop counting prior offenses.
5. **Vehicle impound categories:** "all_dui_arrest" = strongest (car seized at arrest). "repeat_conviction" = only after multiple offenses. "mandatory" = automatic; "discretionary" = officer/court decides.

## Sources

See SOURCES.md for complete attribution.
"""

codebook_path = EXPORT / "dui_by_state_v4_codebook.md"
codebook_path.write_text(codebook)
print(f"  → {codebook_path.name}")

print(f"\n{'='*60}")
print(f"EXPORT COMPLETE: dui_by_state_v4")
print(f"  {len(master)} rows × {len(master.columns)} columns")
print(f"  Formats: CSV, Excel, Parquet + codebook")
