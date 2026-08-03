"""Prepare stage: build the master states analysis table and export package.

This module handles:
  - Parsing penalty strings into clean numeric columns (jail days, fine dollars, suspension days)
  - Computing per-capita rates (fatalities per 100k, arrests per reporting-100k)
  - Joining all cleaned tables into a single master states table (one row per state)
  - Grouping states by punishment profile
  - Exporting the sellable dataset (CSV + Excel + Parquet + codebook)

Usage in 03-prepare.ipynb:
    from src.prepare import build_master_table, package_dataset
"""

from __future__ import annotations

import re
import textwrap
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


# ---------------------------------------------------------------------------
# Penalty string parsers
# ---------------------------------------------------------------------------

def _parse_dollar(s: str | None) -> float | None:
    """Extract the first dollar amount from a string like '$600–$2,100' or '$1,500+'."""
    if not s or pd.isna(s):
        return None
    # Find all dollar amounts
    amounts = re.findall(r"\$([\d,]+)", str(s))
    if not amounts:
        return None
    # Return the minimum (first offense minimum)
    return float(amounts[0].replace(",", ""))


def _parse_dollar_max(s: str | None) -> float | None:
    """Extract the maximum dollar amount from a range like '$600–$2,100'."""
    if not s or pd.isna(s):
        return None
    amounts = re.findall(r"\$([\d,]+)", str(s))
    if not amounts:
        return None
    return float(amounts[-1].replace(",", ""))


def _duration_to_days(s: str | None) -> float | None:
    """Convert a duration string to days.

    Handles patterns like:
      '10 days min.', 'Up to 1 year', '48 hrs–6 months',
      '90 days', '6 months', '1 year', '72 hrs min.',
      'None (standard)', '3–180 days'
    Returns the minimum duration for ranges.
    """
    if not s or pd.isna(s):
        return None
    s = str(s).strip().lower()

    # Explicit none / no jail
    if s.startswith("none"):
        return 0.0

    # Multipliers
    def _to_days(value: float, unit: str) -> float:
        unit = unit.strip().rstrip(".")
        if "year" in unit:
            return value * 365
        if "month" in unit:
            return value * 30
        if "day" in unit:
            return value
        if "hr" in unit or "hour" in unit:
            return value / 24
        return value  # fallback: assume days

    # Pattern: "Up to X unit"
    m = re.match(r"up to ([\d.]+)\s*(\w+)", s)
    if m:
        return _to_days(float(m.group(1)), m.group(2))

    # Pattern: "X unit min." or "X unit minimum"
    m = re.match(r"([\d.]+)\s*(\w+)\s*min", s)
    if m:
        return _to_days(float(m.group(1)), m.group(2))

    # Pattern: "X unit–Y unit" or "X–Y unit" (range — take minimum)
    m = re.match(r"([\d.]+)\s*(\w+)[–\-−]([\d.]+)\s*(\w+)", s)
    if m:
        return _to_days(float(m.group(1)), m.group(2))

    # Pattern: "X–Y unit" where first number has no unit
    m = re.match(r"([\d.]+)[–\-−]([\d.]+)\s*(\w+)", s)
    if m:
        return _to_days(float(m.group(1)), m.group(3))

    # Pattern: simple "X unit" (e.g. "90 days", "6 months")
    m = re.match(r"([\d.]+)\s*(\w+)", s)
    if m:
        return _to_days(float(m.group(1)), m.group(2))

    return None


def _parse_iid_category(s: str | None) -> str:
    """Normalize IID requirement into a category."""
    if not s or pd.isna(s):
        return "unknown"
    s = str(s).strip().lower()
    if "all" in s:
        return "all_offenders"
    if "repeat" in s:
        return "repeat_only"
    if "high bac" in s:
        return "high_bac"
    return "other"


def _parse_lookback_years(s: str | None) -> float | None:
    """Extract lookback period in years from strings like '10 years' or '7 years'."""
    if not s or pd.isna(s):
        return None
    m = re.search(r"(\d+)\s*year", str(s).lower())
    if m:
        return float(m.group(1))
    if "lifetime" in str(s).lower():
        return 99.0  # sentinel for lifetime
    return None


def parse_penalties(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Parse penalty string columns into clean numerics.

    Joins dui_penalties_roadlaw and dui_penalties_ailawyer on state name,
    extracts numeric jail days, fine dollars, and suspension days.

    Returns a DataFrame with one row per state (keyed by state_name).
    """
    roadlaw = con.execute("SELECT * FROM dui_penalties_roadlaw").df()
    ailawyer = con.execute("SELECT * FROM dui_penalties_ailawyer").df()

    # Parse roadlaw numerics
    roadlaw["fine_min_dollars"] = roadlaw["dwi_fines"].apply(_parse_dollar)
    roadlaw["fine_max_dollars"] = roadlaw["dwi_fines"].apply(_parse_dollar_max)
    roadlaw["jail_min_days"] = roadlaw["jail_time"].apply(_duration_to_days)
    roadlaw["suspension_days"] = roadlaw["suspension"].apply(_duration_to_days)
    roadlaw["iid_category"] = roadlaw["iid"].apply(_parse_iid_category)

    # Parse ailawyer numerics
    ailawyer["lookback_years"] = ailawyer["lookback"].apply(_parse_lookback_years)

    # Merge on state name
    merged = roadlaw[["state", "fine_min_dollars", "fine_max_dollars",
                      "jail_min_days", "suspension_days", "iid_category"]].merge(
        ailawyer[["state", "lookback_years"]],
        on="state", how="outer"
    )
    merged = merged.rename(columns={"state": "state_name"})
    return merged


# ---------------------------------------------------------------------------
# Per-capita rate computation
# ---------------------------------------------------------------------------

def compute_rates(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Compute per-capita rates using DuckDB.

    Returns a DataFrame with:
      - alcohol_fatality_rate_per_100k (NHTSA imputed / pop * 100k)
      - total_fatality_rate_per_100k
      - dui_arrest_rate_per_100k (arrests / reporting_population * 100k)
      - pct_traffic_deaths_alcohol (NHTSA imputed)
    """
    sql = """
    SELECT
        s.state_fips,
        s.state_name,
        -- Fatality rates from NHTSA imputed (authoritative)
        ROUND(n.alcohol_impaired_fatalities_2024 * 100000.0 / s.pop_2024, 2)
            AS alcohol_fatality_rate_per_100k,
        ROUND(n.total_fatalities_2024 * 100000.0 / s.pop_2024, 2)
            AS total_fatality_rate_per_100k,
        -- DUI as % of total traffic deaths
        ROUND(n.alcohol_impaired_fatalities_2024 * 100.0
              / NULLIF(n.total_fatalities_2024, 0), 1)
            AS pct_traffic_deaths_alcohol,
        -- Arrest rate per reporting population
        ROUND(a.total_dui_arrests * 100000.0
              / NULLIF(a.reporting_population, 0), 2)
            AS dui_arrest_rate_per_100k,
        a.reporting_population
    FROM states s
    JOIN nhtsa_imputed_2024 n ON s.state_fips = n.state_fips
    LEFT JOIN dui_arrests_2023 a ON s.state_fips = a.state_fips
    """
    return con.execute(sql).df()


# ---------------------------------------------------------------------------
# Master states table builder
# ---------------------------------------------------------------------------

def build_master_table(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Build the one-row-per-state master analysis table.

    Joins all source tables and computed columns into a single wide DataFrame
    suitable for export and visualization.
    """
    # Base: states reference
    states = con.execute("""
        SELECT state_fips, state_abbr, state_name, region, division,
               pop_2024, lat, lng
        FROM states
    """).df()

    # Per-capita rates
    rates = compute_rates(con)

    # NHTSA imputed fatalities (raw counts for the export)
    nhtsa = con.execute("""
        SELECT state_fips,
               alcohol_impaired_fatalities_2024,
               total_fatalities_2024,
               high_bac_fatalities_2024
        FROM nhtsa_imputed_2024
    """).df()

    # Enforcement flags
    enforcement = con.execute("""
        SELECT state_fips, checkpoints_legal, all_offender_iid,
               criminal_refusal_penalty, implied_consent,
               open_container_law, bac_limit
        FROM dui_enforcement
    """).df()

    # Criminal status / felony flags
    criminal = con.execute("""
        SELECT state_fips, first_offense_felony, felony_threshold
        FROM dui_criminal_status_clean
    """).df()

    # Alcohol consumption
    consumption = con.execute("""
        SELECT state_fips, ethanol_per_capita_gallons_2022
        FROM alcohol_consumption
    """).df()

    # Arrest counts
    arrests = con.execute("""
        SELECT state_fips, total_dui_arrests, reporting_agencies,
               reporting_population AS arrest_reporting_pop
        FROM dui_arrests_2023
    """).df()

    # License status in fatal crashes
    license_status = con.execute("""
        SELECT state_fips, total_drivers_in_fatal_crashes,
               drivers_suspended_revoked, drivers_suspended_and_impaired,
               pct_suspended, pct_suspended_who_impaired
        FROM fars_license_status_2024
    """).df()

    # Parsed penalties
    penalties = parse_penalties(con)

    # Prior DWI convictions and crash speed (from FARS vehicle.csv)
    prior_dwi = con.execute("""
        SELECT state_fips, pct_impaired_with_prior_dwi, pct_all_with_prior_dwi,
               median_crash_speed_limit, mean_crash_speed_limit,
               pct_crashes_high_speed
        FROM fars_prior_dwi_speed
    """).df()

    # State max speed limits and VMT (joined on state_name)
    speed_vmt = con.execute("""
        SELECT state_name, max_speed_limit_mph, vmt_millions_2022
        FROM speed_limits_vmt
    """).df()

    # --- Join everything on state_fips ---
    master = states.copy()

    fips_tables = [rates, nhtsa, enforcement, criminal, consumption,
                   arrests, license_status, prior_dwi]
    for tbl in fips_tables:
        # Drop state_name if present to avoid _x/_y columns
        drop_cols = [c for c in ["state_name"] if c in tbl.columns]
        tbl_clean = tbl.drop(columns=drop_cols) if drop_cols else tbl
        master = master.merge(tbl_clean, on="state_fips", how="left")

    # Join penalties on state_name
    master = master.merge(penalties, on="state_name", how="left")

    # Join speed limits / VMT on state_name
    master = master.merge(speed_vmt, on="state_name", how="left")

    # --- Derived columns ---
    # Punishment profile grouping
    master["punishment_profile"] = master.apply(_classify_punishment, axis=1)

    # Fatality rate per 100 million VMT (gold standard comparison)
    master["fatality_rate_per_100m_vmt"] = (
        master["total_fatalities_2024"] * 100.0
        / master["vmt_millions_2022"]
    ).round(2)
    master["alcohol_fatality_rate_per_100m_vmt"] = (
        master["alcohol_impaired_fatalities_2024"] * 100.0
        / master["vmt_millions_2022"]
    ).round(2)

    # Flag states with insufficient license-status sample
    master["license_status_sufficient"] = (
        master["drivers_suspended_revoked"].fillna(0) >= 15
    ).astype(int)

    # Drop reporting_population duplicate if present
    if "reporting_population" in master.columns:
        master = master.drop(columns=["reporting_population"])

    # Round float columns for clean export
    float_cols = master.select_dtypes("float64").columns
    master[float_cols] = master[float_cols].round(2)

    # Sort by state name
    master = master.sort_values("state_name").reset_index(drop=True)

    print(f"Master table built: {len(master)} states × {len(master.columns)} columns")
    return master


# ---------------------------------------------------------------------------
# Punishment profile classification
# ---------------------------------------------------------------------------

def _classify_punishment(row: pd.Series) -> str:
    """Classify a state's punishment profile for first-offense DUI.

    Categories:
      - mandatory_jail: jail_min_days > 0
      - fine_only: jail_min_days == 0 and fine_min_dollars > 0
      - both_jail_and_fine: jail > 0 and fine > 0 (most states)
      - minimal: no mandatory jail and low/no fine
    """
    jail = row.get("jail_min_days")
    fine = row.get("fine_min_dollars")

    has_jail = pd.notna(jail) and jail > 0
    has_fine = pd.notna(fine) and fine > 0

    if has_jail and has_fine:
        return "both_jail_and_fine"
    elif has_jail:
        return "mandatory_jail_only"
    elif has_fine:
        return "fine_only"
    else:
        return "minimal"


# ---------------------------------------------------------------------------
# Comparison helpers (IID, felony, etc.)
# ---------------------------------------------------------------------------

def iid_comparison(master: pd.DataFrame) -> pd.DataFrame:
    """Compare fatality and arrest rates: all-offender IID states vs non-IID."""
    iid_states = master[master["all_offender_iid"] == 1]
    non_iid = master[master["all_offender_iid"] == 0]

    metrics = ["alcohol_fatality_rate_per_100k", "alcohol_fatality_rate_per_100m_vmt",
               "dui_arrest_rate_per_100k", "pct_traffic_deaths_alcohol"]

    rows = []
    for m in metrics:
        rows.append({
            "metric": m,
            "iid_states_mean": iid_states[m].mean(),
            "iid_states_median": iid_states[m].median(),
            "non_iid_mean": non_iid[m].mean(),
            "non_iid_median": non_iid[m].median(),
            "iid_n": len(iid_states),
            "non_iid_n": len(non_iid),
        })
    return pd.DataFrame(rows).round(2)


def felony_comparison(master: pd.DataFrame) -> pd.DataFrame:
    """Compare fatality and arrest rates: always-misdemeanor vs felony states."""
    # felony_threshold == NaN means never becomes a felony (always misdemeanor)
    always_misd = master[master["felony_threshold"].isna()]
    has_felony = master[master["felony_threshold"].notna()]

    metrics = ["alcohol_fatality_rate_per_100k", "alcohol_fatality_rate_per_100m_vmt",
               "dui_arrest_rate_per_100k", "pct_traffic_deaths_alcohol"]

    rows = []
    for m in metrics:
        rows.append({
            "metric": m,
            "always_misdemeanor_mean": always_misd[m].mean(),
            "always_misdemeanor_median": always_misd[m].median(),
            "felony_states_mean": has_felony[m].mean(),
            "felony_states_median": has_felony[m].median(),
            "misdemeanor_n": len(always_misd),
            "felony_n": len(has_felony),
        })
    return pd.DataFrame(rows).round(2)


def punishment_profile_summary(master: pd.DataFrame) -> pd.DataFrame:
    """Group states by punishment_profile and summarize key metrics."""
    metrics = ["alcohol_fatality_rate_per_100k", "alcohol_fatality_rate_per_100m_vmt",
               "dui_arrest_rate_per_100k", "jail_min_days", "fine_min_dollars"]
    summary = master.groupby("punishment_profile")[metrics].agg(["mean", "median", "count"])
    summary.columns = ["_".join(c) for c in summary.columns]
    return summary.round(2)


# ---------------------------------------------------------------------------
# Trends table (methodology-consistent 2015–2020 window)
# ---------------------------------------------------------------------------

def build_trends_table(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Build a per-state trend summary for the 2015–2020 consistent window.

    Only uses years where impairment_method = 'drunk_dr_field' (pre-2021 methodology).
    """
    sql = """
    SELECT
        f.state_fips,
        s.state_abbr,
        s.state_name,
        f.year,
        f.impaired_fatalities_any,
        f.total_fatalities,
        ROUND(f.impaired_fatalities_any * 100.0
              / NULLIF(f.total_fatalities, 0), 1) AS pct_impaired
    FROM fars_trends_clean f
    JOIN states s ON f.state_fips = s.state_fips
    WHERE f.year BETWEEN 2015 AND 2020
      AND f.impairment_method = 'drunk_dr_field'
    ORDER BY s.state_name, f.year
    """
    return con.execute(sql).df()


# ---------------------------------------------------------------------------
# PII stripping
# ---------------------------------------------------------------------------

def strip_pii(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Drop columns listed under export.strip_pii_columns in config.yaml."""
    cols_to_drop = cfg.get("export", {}).get("strip_pii_columns", [])
    if cols_to_drop:
        existing = [c for c in cols_to_drop if c in df.columns]
        if existing:
            df = df.drop(columns=existing)
            print(f"Stripped PII columns: {existing}")
    return df


# ---------------------------------------------------------------------------
# Codebook
# ---------------------------------------------------------------------------

def build_codebook(
    df: pd.DataFrame,
    descriptions: dict[str, str] | None = None,
    project_name: str = "",
    notes: str = "",
) -> str:
    """Generate a plain-text codebook for the dataset.

    Args:
        df:           The export-ready DataFrame.
        descriptions: Dict mapping column name -> human-readable description.
        project_name: Printed in the header.
        notes:        Free-text notes appended at the bottom.

    Returns:
        Codebook as a string (written to a .md file by package_dataset).
    """
    descriptions = descriptions or {}
    today = date.today().isoformat()

    lines = [
        f"# {project_name} — Dataset Codebook",
        f"Generated: {today}",
        "",
        "## Columns",
        "",
    ]

    for col in df.columns:
        dtype = str(df[col].dtype)
        desc = descriptions.get(col, "_No description provided._")
        non_null = df[col].notna().sum()
        total = len(df)
        lines.append(f"### `{col}`")
        lines.append(f"- **Type**: `{dtype}`")
        lines.append(f"- **Non-null**: {non_null:,} / {total:,} ({non_null/total:.1%})")
        lines.append(f"- **Description**: {desc}")
        lines.append("")

    if notes:
        lines += ["## Notes", "", textwrap.dedent(notes).strip(), ""]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def package_dataset(
    df: pd.DataFrame,
    cfg: dict[str, Any],
    name: str,
    codebook: dict[str, str] | None = None,
    notes: str = "",
    formats: list[str] | None = None,
) -> dict[str, Path]:
    """Strip PII, export to configured formats, and write a codebook.

    Args:
        df:       Processed DataFrame ready for packaging.
        cfg:      Loaded config dict.
        name:     Base filename (no extension).
        codebook: Column description dict passed to build_codebook().
        notes:    Free-text appended to the codebook.
        formats:  Override config export.formats.

    Returns:
        Dict of {format: Path} for every file written.
    """
    df = strip_pii(df, cfg)

    export_dir = Path(cfg["paths"]["export"])
    export_dir.mkdir(parents=True, exist_ok=True)

    export_cfg = cfg.get("export", {})
    active_formats = formats or export_cfg.get("formats", ["csv"])
    include_codebook = export_cfg.get("include_codebook", True)
    project_name = cfg.get("project_name", name)

    written: dict[str, Path] = {}

    if "csv" in active_formats:
        p = export_dir / f"{name}.csv"
        df.to_csv(p, index=False, encoding=cfg["settings"]["encoding"])
        written["csv"] = p
        print(f"Exported CSV     -> {p}")

    if "xlsx" in active_formats:
        p = export_dir / f"{name}.xlsx"
        with pd.ExcelWriter(p, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="data")
        written["xlsx"] = p
        print(f"Exported Excel   -> {p}")

    if "parquet" in active_formats:
        p = export_dir / f"{name}.parquet"
        df.to_parquet(p, index=False, engine=cfg["settings"]["parquet_engine"])
        written["parquet"] = p
        print(f"Exported Parquet -> {p}")

    if include_codebook:
        cb_text = build_codebook(
            df, descriptions=codebook, project_name=project_name, notes=notes
        )
        cb_path = export_dir / f"{name}_codebook.md"
        cb_path.write_text(cb_text, encoding="utf-8")
        written["codebook"] = cb_path
        print(f"Wrote codebook   -> {cb_path}")

    print(f"\n  Package complete: {len(df):,} rows x {len(df.columns)} columns")
    return written


# ---------------------------------------------------------------------------
# Quick summary helpers
# ---------------------------------------------------------------------------

def value_counts_all(df: pd.DataFrame, top_n: int = 10) -> None:
    """Print top-N value counts for every column — quick sanity check."""
    for col in df.columns:
        print(f"\n-- {col} --")
        print(df[col].value_counts(dropna=False).head(top_n).to_string())


def numeric_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Return describe() for numeric columns, transposed for readability."""
    return df.select_dtypes("number").describe().T.round(2)
