"""
prepare_export_v3.py — Build the v3 master export dataset.

Changes from v2:
  - Renamed FARS raw columns: 'alcohol_*' → 'impaired_*' (these use drimpair code 9
    which captures any impairment — alcohol, drugs, medication — not just alcohol)
  - NHTSA imputed columns keep 'alcohol' (genuinely BAC ≥ .08 only)

Joins all cleaned tables into one comprehensive 51-state dataset.

Output:
  - export/dui_by_state_v3.csv
  - export/dui_by_state_v3.xlsx
  - export/dui_by_state_v3.parquet
  - export/dui_by_state_v3_codebook.md
  - data/processed/dui_master_states_v3.parquet

Run: /opt/anaconda3/envs/data_projects/bin/python scripts/prepare_export_v3.py
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
    s.lat,
    s.lng,

    -- ── Fatality outcomes (FARS raw + NHTSA imputed) ────────────────────────
    s.traffic_fatalities_2024,
    s.alcohol_fatalities_2024 AS impaired_fatalities_fars_raw,
    n.alcohol_impaired_fatalities_2024 AS alcohol_fatalities_nhtsa_imputed,
    n.total_fatalities_2024 AS total_fatalities_nhtsa,
    s.pct_alcohol_2024 AS pct_impaired_fars_raw,
    n.pct_alcohol_impaired_2024 AS pct_alcohol_nhtsa_imputed,
    n.high_bac_fatalities_2024,
    n.pct_high_bac_2024,

    -- ── Per-capita and per-VMT rates ────────────────────────────────────────
    ROUND(s.traffic_fatalities_2024 * 100000.0 / s.pop_2024, 2) AS total_fatality_rate_per_100k,
    ROUND(n.alcohol_impaired_fatalities_2024 * 100000.0 / s.pop_2024, 2) AS alcohol_fatality_rate_per_100k,
    ROUND(s.traffic_fatalities_2024 * 100.0 / (v.vmt_millions_2022 / 100.0), 2) AS total_fatality_rate_per_100m_vmt,
    ROUND(n.alcohol_impaired_fatalities_2024 * 100.0 / (v.vmt_millions_2022 / 100.0), 2) AS alcohol_fatality_rate_per_100m_vmt,

    -- ── BAC testing rates (from FARS person.csv) ────────────────────────────
    bt.pct_bac_known_killed,
    bt.pct_bac_known_all AS pct_bac_known_all_drivers,
    bt.pct_bac_known_surviving,
    bt.pct_blood_test,
    bt.total_drivers AS total_drivers_in_fatal_crashes,

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

    -- ── Existing enforcement (original dui_enforcement) ─────────────────────
    de.criminal_refusal_penalty,
    de.bac_limit,

    -- ── Criminal status ─────────────────────────────────────────────────────
    cs.first_offense_felony,

    -- ── Structural controls ─────────────────────────────────────────────────
    v.max_speed_limit_mph,
    v.vmt_millions_2022,
    ps.pct_impaired_with_prior_dwi,
    ps.pct_all_with_prior_dwi,
    ps.median_crash_speed_limit,
    ps.pct_crashes_high_speed,

    -- ── Alcohol consumption ─────────────────────────────────────────────────
    ac.ethanol_per_capita_gallons_2022,

    -- ── DUI arrests ─────────────────────────────────────────────────────────
    da.total_dui_arrests,
    da.reporting_agencies,
    da.reporting_population,
    ROUND(da.total_dui_arrests * 100000.0 / da.reporting_population, 1) AS dui_arrest_rate_per_100k_reporting

FROM states s
LEFT JOIN nhtsa_imputed_2024 n ON s.state_name = n.state_name
LEFT JOIN fars_bac_testing_2024 bt ON s.state_fips = bt.state_fips
LEFT JOIN bac_testing_laws bl ON s.state_fips = bl.state_fips
LEFT JOIN nasid_enforcement_clean ec ON s.state_fips = ec.state_fips
LEFT JOIN dui_enforcement de ON s.state_fips = de.state_fips
LEFT JOIN dui_criminal_status_clean cs ON s.state_fips = cs.state_fips
LEFT JOIN speed_limits_vmt v ON s.state_name = v.state_name
LEFT JOIN fars_prior_dwi_speed ps ON s.state_fips = ps.state_fips
LEFT JOIN alcohol_consumption ac ON s.state_fips = ac.state_fips
LEFT JOIN dui_arrests_2023 da ON s.state_fips = da.state_fips
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

# Key columns should not be null
critical_cols = ["state_fips", "state_name", "pop_2024", "traffic_fatalities_2024",
                 "pct_bac_known_killed", "mandatory_testing_law", "checkpoints_permitted"]
for col in critical_cols:
    nulls = master[col].isnull().sum()
    if nulls > 0:
        print(f"  ⚠ {col}: {nulls} nulls")
    else:
        print(f"  ✓ {col}: no nulls")

# Overall null summary
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

# Processed parquet
processed_path = PROCESSED / "dui_master_states_v3.parquet"
master.to_parquet(processed_path, index=False, engine="pyarrow")
print(f"  → {processed_path.name}")

# Export CSV
csv_path = EXPORT / "dui_by_state_v3.csv"
master.to_csv(csv_path, index=False)
print(f"  → {csv_path.name}")

# Export Parquet
pq_path = EXPORT / "dui_by_state_v3.parquet"
master.to_parquet(pq_path, index=False, engine="pyarrow")
print(f"  → {pq_path.name}")

# Export Excel
xlsx_path = EXPORT / "dui_by_state_v3.xlsx"
master.to_excel(xlsx_path, index=False, sheet_name="dui_by_state_v3", engine="openpyxl")
print(f"  → {xlsx_path.name}")

# ═══════════════════════════════════════════════════════════════════════════════
# CODEBOOK
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[4] Writing codebook...")

codebook = f"""# Codebook — dui_by_state_v3

**Dataset:** DUI Laws, Enforcement Procedures & Fatality Outcomes by State (2024)
**Rows:** {len(master)} (50 states + District of Columbia)
**Columns:** {len(master.columns)}
**Created:** 2026-08-10
**Author:** @unwelcomedata
**Changes from v2:** Renamed FARS raw columns from 'alcohol_*' to 'impaired_*' (drimpair code 9 = any impairment, not just alcohol). NHTSA imputed columns keep 'alcohol' (BAC ≥ .08 only).

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
| lat | float | Census internal point latitude |
| lng | float | Census internal point longitude |

## Fatality Outcomes

| Column | Type | Description |
|--------|------|-------------|
| traffic_fatalities_2024 | int | Total traffic fatalities (FARS 2024) |
| impaired_fatalities_fars_raw | int | Impaired-driving fatalities, FARS raw coding (drimpair code 9: alcohol + drugs + medication) |
| alcohol_fatalities_nhtsa_imputed | int | Alcohol-impaired fatalities (BAC≥.08 only), NHTSA statistical imputation |
| total_fatalities_nhtsa | int | Total fatalities per NHTSA imputed report |
| pct_impaired_fars_raw | float | % traffic deaths with any impairment involvement (FARS raw, includes drugs/meds) |
| pct_alcohol_nhtsa_imputed | int | % traffic deaths alcohol-impaired (NHTSA imputed, BAC≥.08 only) |
| high_bac_fatalities_2024 | int | High-BAC fatalities (BAC≥.15), NHTSA imputed |
| pct_high_bac_2024 | int | % traffic deaths involving high-BAC driver |

## Per-Capita and Per-VMT Rates

| Column | Type | Description |
|--------|------|-------------|
| total_fatality_rate_per_100k | float | Total traffic deaths per 100,000 population |
| alcohol_fatality_rate_per_100k | float | Alcohol-impaired deaths per 100,000 population (NHTSA imputed, BAC≥.08) |
| total_fatality_rate_per_100m_vmt | float | Total traffic deaths per 100 million vehicle miles traveled |
| alcohol_fatality_rate_per_100m_vmt | float | Alcohol-impaired deaths per 100M VMT (NHTSA imputed, BAC≥.08) |

## BAC Testing Rates (FARS 2024 Person File)

| Column | Type | Description |
|--------|------|-------------|
| pct_bac_known_killed | float | % of killed drivers with known BAC test result |
| pct_bac_known_all_drivers | float | % of all drivers in fatal crashes with known BAC |
| pct_bac_known_surviving | float | % of surviving drivers with known BAC |
| pct_blood_test | float | % of tested drivers whose test was blood (vs breath/PBT) |
| total_drivers_in_fatal_crashes | int | Total drivers involved in fatal crashes |

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

## Structural Controls

| Column | Type | Description |
|--------|------|-------------|
| max_speed_limit_mph | int | Maximum posted rural interstate speed limit (IIHS) |
| vmt_millions_2022 | int | Annual vehicle miles traveled in millions (FHWA 2022) |
| pct_impaired_with_prior_dwi | float | % of impaired drivers in fatal crashes with prior DWI conviction |
| pct_all_with_prior_dwi | float | % of all drivers in fatal crashes with prior DWI |
| median_crash_speed_limit | float | Median posted speed limit at fatal crash locations |
| pct_crashes_high_speed | float | % of fatal crashes on roads with speed limit ≥55 mph |

## Alcohol Consumption

| Column | Type | Description |
|--------|------|-------------|
| ethanol_per_capita_gallons_2022 | float | Per capita ethanol consumption in gallons (NIAAA, ages 14+) |

## DUI Arrests (FBI UCR 2023)

| Column | Type | Description |
|--------|------|-------------|
| total_dui_arrests | int | Total DUI arrests from reporting agencies |
| reporting_agencies | int | Number of agencies reporting to UCR |
| reporting_population | int | Population covered by reporting agencies |
| dui_arrest_rate_per_100k_reporting | float | DUI arrests per 100k reporting-area population |

---

## Data Caveats

1. **NHTSA imputed vs FARS raw:** The NHTSA imputed figures (BAC≥.08) use statistical modeling to estimate BAC for untested drivers — alcohol only. FARS raw (drimpair code 9) captures any impairment including drugs and medication — broader definition, lower counts because no imputation.
2. **BAC testing rates vary dramatically:** From 10% (MS) to 98% (VT) for killed drivers. States with low testing rates have more of their numbers filled by NHTSA's imputation model.
3. **Mandatory testing ≠ high testing:** CA, ID, OK have mandatory laws but <60% compliance.
4. **DUI arrests are incomplete:** UCR reporting is voluntary. State totals reflect only reporting agencies. Use per-reporting-population rates for comparison.
5. **VMT is 2022:** Most recent available complete year from FHWA.
6. **Lookback 99 = lifetime:** Some states never stop counting prior offenses.

## Sources

See SOURCES.md for complete attribution.
"""

codebook_path = EXPORT / "dui_by_state_v3_codebook.md"
codebook_path.write_text(codebook)
print(f"  → {codebook_path.name}")

print(f"\n{'='*60}")
print(f"EXPORT COMPLETE: dui_by_state_v3")
print(f"  {len(master)} rows × {len(master.columns)} columns")
print(f"  Formats: CSV, Excel, Parquet + codebook")
