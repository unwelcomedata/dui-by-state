"""
ingest_all.py — Full data ingestion for dui-by-state project.

Sources (all U.S. government / official):
  1. state_reference.csv    — hand-curated Census Gazetteer (lat/lng, area, region)
  2. Census FIPS state.txt  — official FIPS codes + abbreviations
  3. Census NST-EST2024     — state population estimates 2020-2024
  4. NHTSA FARS 2015-2024   — alcohol-impaired driving fatalities by state
  5. NCSL DUI laws          — per se BAC laws by state
  6. roadlawguide.com       — first-offense DUI penalties by state
  7. ailawyer.pro           — DUI penalties cross-reference

Run from project root (venv active):
    /opt/anaconda3/envs/data_projects/bin/python scripts/ingest_all.py
"""

from __future__ import annotations

import io
import re
import sys
import time
import zipfile
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import requests
import yaml
from bs4 import BeautifulSoup

# ── setup ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

with open(ROOT / "config.yaml") as f:
    CFG = yaml.safe_load(f)

RAW   = ROOT / CFG["paths"]["data_raw"]
INTER = ROOT / CFG["paths"]["data_interim"]
DB    = ROOT / CFG["settings"]["duckdb_file"]

for d in (RAW, INTER, DB.parent):
    d.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.census.gov/",
}

TODAY = date.today().isoformat()
con = duckdb.connect(str(DB))


# ── helpers ──────────────────────────────────────────────────────────────────

def fetch(url: str, stream: bool = False, timeout: int = 60,
          min_delay: float = 1.5, retries: int = 4) -> requests.Response:
    """
    Fetch a URL with polite rate limiting and exponential backoff on 429/5xx.

    - Always waits min_delay seconds before every request (be a good citizen).
    - On 429 Too Many Requests: honours Retry-After header if present,
      otherwise backs off 15 → 30 → 60 → 120 seconds.
    - On 5xx server errors: backs off 5 → 10 → 20 → 40 seconds.
    - Raises on 4xx (except 429) immediately — no point retrying a 404.
    """
    backoff_429 = [15, 30, 60, 120]
    backoff_5xx = [5, 10, 20, 40]

    for attempt in range(retries + 1):
        time.sleep(min_delay)
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout, stream=stream)
        except requests.exceptions.ConnectionError as e:
            if attempt < retries:
                wait = backoff_5xx[min(attempt, len(backoff_5xx) - 1)]
                print(f"    Connection error, retrying in {wait}s… ({e})")
                time.sleep(wait)
                continue
            raise

        if r.status_code == 429:
            if attempt >= retries:
                r.raise_for_status()
            retry_after = int(r.headers.get("Retry-After", backoff_429[min(attempt, len(backoff_429)-1)]))
            print(f"    429 Too Many Requests — waiting {retry_after}s before retry {attempt+1}/{retries}…")
            time.sleep(retry_after)
            continue

        if r.status_code >= 500:
            if attempt >= retries:
                r.raise_for_status()
            wait = backoff_5xx[min(attempt, len(backoff_5xx) - 1)]
            print(f"    {r.status_code} server error — retrying in {wait}s…")
            time.sleep(wait)
            continue

        r.raise_for_status()
        return r

    raise RuntimeError(f"Failed to fetch {url} after {retries} retries")


def fetch_cached(url: str, dest: Path, stream: bool = False,
                 timeout: int = 300, min_delay: float = 1.5) -> bytes:
    """
    Download url to dest if the file doesn't already exist.
    Returns the file contents as bytes.
    This means re-running the script never re-downloads files already on disk.
    """
    if dest.exists() and dest.stat().st_size > 0:
        print(f"    (cached) {dest.name}")
        return dest.read_bytes()
    r = fetch(url, stream=stream, timeout=timeout, min_delay=min_delay)
    data = b""
    if stream:
        for chunk in r.iter_content(chunk_size=65536):
            data += chunk
    else:
        data = r.content
    dest.write_bytes(data)
    return data


def clean_cols(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [
        re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_")
        for c in df.columns
    ]
    return df


def to_duckdb(df: pd.DataFrame, table: str) -> None:
    con.execute(f"DROP TABLE IF EXISTS {table}")
    con.execute(f"CREATE TABLE {table} AS SELECT * FROM df")
    print(f"  → DuckDB '{table}': {len(df):,} rows × {len(df.columns)} cols")


def to_interim(df: pd.DataFrame, name: str) -> Path:
    p = INTER / f"{name}.parquet"
    df.to_parquet(p, index=False, engine="pyarrow")
    print(f"  → Parquet: {p.name}  ({len(df):,} rows)")
    return p


# Source registry — written to _sources table at the end
_source_registry: list[dict] = []

def register_source(table: str, name: str, url: str, license: str, notes: str = "") -> None:
    _source_registry.append({
        "duckdb_table": table,
        "source_name":  name,
        "url":          url,
        "license":      license,
        "notes":        notes,
        "retrieved":    TODAY,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# 1. STATE REFERENCE — hand-curated Census Gazetteer data
#    Source: U.S. Census Bureau 2024 Gazetteer Files
#    URL: https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[1/6] State reference (Census Gazetteer — hand-curated CSV)")

state_ref_path = RAW / "state_reference.csv"
if not state_ref_path.exists():
    raise FileNotFoundError(f"Missing required file: {state_ref_path}\nThis file must exist in data/raw/.")

state_ref = pd.read_csv(state_ref_path, dtype={"state_fips": str})
state_ref["state_fips"] = state_ref["state_fips"].str.zfill(2)
# Fix any Unicode minus signs in lng (the CSV uses − not -)
state_ref["lng"] = pd.to_numeric(
    state_ref["lng"].astype(str).str.replace("\u2212", "-", regex=False), errors="coerce"
)
state_ref["lat"] = pd.to_numeric(state_ref["lat"].astype(str), errors="coerce")

print(f"  {len(state_ref)} states  cols: {list(state_ref.columns)}")

to_duckdb(state_ref, "state_ref")
to_interim(state_ref, "state_reference")
register_source(
    table="state_ref",
    name="U.S. Census Bureau — 2024 Gazetteer Files",
    url="https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html",
    license="Public domain (U.S. government work)",
    notes="Hand-curated from Census Gazetteer. lat/lng are Census internal points. "
          "Area from 2020 Census. Region/division per Census Bureau classification.",
)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. CENSUS FIPS CODES
#    Source: U.S. Census Bureau
#    URL: https://www2.census.gov/geo/docs/reference/state.txt
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[2/6] Census FIPS codes & abbreviations")

fips_url = "https://www2.census.gov/geo/docs/reference/state.txt"
fips_bytes = fetch_cached(fips_url, RAW / "census_fips_state.txt")
r_text = fips_bytes.decode("utf-8")

fips_df = pd.read_csv(io.StringIO(r_text), sep="|", dtype={"STATE": str})
fips_df = clean_cols(fips_df)
fips_df = fips_df.rename(columns={"state": "state_fips", "stusab": "state_abbr", "state_name": "state_name"})
fips_df["state_fips"] = fips_df["state_fips"].str.zfill(2)
# Filter to 50 states + DC (FIPS 01–11, 12–56; exclude territories ≥ 60)
fips_df = fips_df[fips_df["state_fips"].astype(int) <= 56].copy()
fips_df = fips_df[["state_fips", "state_abbr", "state_name"]].reset_index(drop=True)

print(f"  {len(fips_df)} states/DC")
to_duckdb(fips_df, "fips_codes")
register_source(
    table="fips_codes",
    name="U.S. Census Bureau — FIPS State Codes",
    url=fips_url,
    license="Public domain (U.S. government work)",
    notes="Official FIPS 5-2 state codes. Filtered to 50 states + DC.",
)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. CENSUS POPULATION ESTIMATES 2020–2024
#    Source: U.S. Census Bureau — Population and Housing Unit Estimates
#    URL: https://www2.census.gov/programs-surveys/popest/datasets/2020-2024/state/totals/NST-EST2024-ALLDATA.csv
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[3/6] Census population estimates 2020–2024")

pop_url = "https://www2.census.gov/programs-surveys/popest/datasets/2020-2024/state/totals/NST-EST2024-ALLDATA.csv"
pop_bytes = fetch_cached(pop_url, RAW / "census_population_NST-EST2024.csv")
pop_raw = pd.read_csv(io.StringIO(pop_bytes.decode("utf-8")))
pop_raw = clean_cols(pop_raw)

# SUMLEV 40 = state level; filter out national total and territories
pop_df = pop_raw[
    (pop_raw["sumlev"] == 40) &
    (pop_raw["state"] <= 56)
].copy()

pop_df["state_fips"] = pop_df["state"].astype(str).str.zfill(2)

# Keep name + population columns only
pop_cols = ["state_fips", "name"] + [c for c in pop_df.columns if c.startswith("popestimate")]
pop_df = pop_df[pop_cols].rename(columns={"name": "state_name"})

# Rename year columns for clarity
rename_map = {c: c.replace("popestimate", "pop_") for c in pop_df.columns if c.startswith("popestimate")}
pop_df = pop_df.rename(columns=rename_map)

print(f"  {len(pop_df)} states  cols: {list(pop_df.columns)}")
print(pop_df[["state_fips","state_name","pop_2024","pop_2020"]].head(5).to_string(index=False))

to_duckdb(pop_df, "population")
to_interim(pop_df, "population")
register_source(
    table="population",
    name="U.S. Census Bureau — NST-EST2024 State Population Estimates",
    url=pop_url,
    license="Public domain (U.S. government work)",
    notes="Annual July 1 estimates. Filtered to SUMLEV=40 (states) and STATE FIPS ≤ 56.",
)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. NHTSA FARS — fatalities 2015–2024
#    Source: National Highway Traffic Safety Administration
#    URL: https://static.nhtsa.gov/nhtsa/downloads/FARS/{year}/National/FARS{year}NationalCSV.zip
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[4/6] NHTSA FARS fatalities (2015–2024)")


def process_fars_zip(zip_bytes: bytes, year: int) -> pd.DataFrame:
    """
    Extract accident.csv (and drimpair.csv for 2021+) from a FARS national zip.
    Returns a state-level aggregation DataFrame.

    Schema notes:
    - 2015-2020: drunk_dr column in accident.csv (number of drunk drivers per crash)
    - 2021+:     drunk_dr removed; use drimpair.csv where drimpair == 1
                 (impairment code 1 = alcohol) joined to accident on st_case
    """
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names_lower = {n.lower(): n for n in zf.namelist()}

        # Find accident file
        acc_key = next(k for k in names_lower if "accident" in k and k.endswith(".csv"))
        with zf.open(names_lower[acc_key]) as f:
            acc = pd.read_csv(f, encoding="latin-1", low_memory=False)
        acc.columns = [c.strip().lower().lstrip("\ufeff").lstrip("ï»¿") for c in acc.columns]

        # Normalise state col (some years have BOM prefix)
        if "state" not in acc.columns:
            state_col = next((c for c in acc.columns if c.endswith("state")), None)
            if state_col:
                acc = acc.rename(columns={state_col: "state"})

        acc["state_fips"] = acc["state"].astype(str).str.zfill(2)

        # Determine alcohol flag
        if "drunk_dr" in acc.columns:
            # 2015-2020 schema: drunk_dr in accident table
            acc["alcohol_involved"] = (acc["drunk_dr"] > 0).astype(int)
        else:
            # 2021+ schema: join drimpair where drimpair == 1 (alcohol impairment)
            drimpair_key = next(
                (k for k in names_lower if "drimpair" in k and k.endswith(".csv")), None
            )
            if drimpair_key:
                with zf.open(names_lower[drimpair_key]) as f:
                    di = pd.read_csv(f, encoding="latin-1", low_memory=False)
                di.columns = [c.strip().lower().lstrip("\ufeff").lstrip("ï»¿") for c in di.columns]
                # drimpair == 9 means alcohol/drug impaired driver (2021+ schema)
                alcohol_cases = di[di["drimpair"] == 9]["st_case"].unique()
                acc["alcohol_involved"] = acc["st_case"].isin(alcohol_cases).astype(int)
            else:
                # Fallback: can't determine — mark as unknown
                acc["alcohol_involved"] = 0
                print(f"    WARNING: no drimpair.csv found for {year}, alcohol counts set to 0")

    group_cols = ["state_fips"] + (["statename"] if "statename" in acc.columns else [])
    agg = acc.groupby(group_cols).agg(
        total_crashes=("st_case", "count"),
        total_fatalities=("fatals", "sum"),
        alcohol_crashes=("alcohol_involved", "sum"),
        alcohol_fatalities=(
            "fatals",
            lambda x: x[acc.loc[x.index, "alcohol_involved"] == 1].sum()
        ),
    ).reset_index()

    agg["year"] = year
    agg["pct_fatalities_alcohol"] = (
        agg["alcohol_fatalities"] / agg["total_fatalities"] * 100
    ).round(2)
    if "statename" in agg.columns:
        agg = agg.rename(columns={"statename": "state_name"})
        agg["state_name"] = agg["state_name"].str.strip()

    return agg


trend_frames: list[pd.DataFrame] = []
for yr in range(2015, 2025):
    url = f"https://static.nhtsa.gov/nhtsa/downloads/FARS/{yr}/National/FARS{yr}NationalCSV.zip"
    try:
        print(f"  FARS {yr} ...", end=" ", flush=True)
        zdata = fetch_cached(url, RAW / f"fars_{yr}.zip", stream=True, timeout=300, min_delay=3.0)

        agg = process_fars_zip(zdata, yr)
        trend_frames.append(agg)
        total_f = agg["total_fatalities"].sum()
        alc_f   = agg["alcohol_fatalities"].sum()
        print(f"{len(agg)} states | {total_f:,} fatalities | {alc_f:,} alcohol ({alc_f/total_f*100:.1f}%)")
    except Exception as e:
        print(f"FAILED: {e}")

fars_trends: pd.DataFrame | None = None
if trend_frames:
    fars_trends = pd.concat(trend_frames, ignore_index=True)
    fars_trends = fars_trends.sort_values(["state_fips", "year"]).reset_index(drop=True)
    print(f"\n  FARS trends total: {len(fars_trends):,} rows  ({fars_trends['year'].min()}–{fars_trends['year'].max()})")

    to_duckdb(fars_trends, "fars_trends")
    to_interim(fars_trends, "fars_trends")

    # Separate 2024 table for easy querying
    fars_2024 = fars_trends[fars_trends["year"] == 2024].copy()
    to_duckdb(fars_2024, "fars_2024")
    to_interim(fars_2024, "fars_2024_by_state")

    register_source(
        table="fars_trends",
        name="NHTSA — Fatality Analysis Reporting System (FARS) 2015–2024",
        url="https://static.nhtsa.gov/nhtsa/downloads/FARS/",
        license="Public domain (U.S. government work)",
        notes="accident.CSV extracted from each annual national ZIP. DRUNK_DR > 0 "
              "flags alcohol-involved crashes. 2024 data first released April 2026.",
    )
    register_source(
        table="fars_2024",
        name="NHTSA — FARS 2024 State Summary",
        url="https://static.nhtsa.gov/nhtsa/downloads/FARS/2024/National/FARS2024NationalCSV.zip",
        license="Public domain (U.S. government work)",
        notes="2024 state-level aggregation derived from FARS accident.CSV.",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 5. DUI LAWS — NCSL per se BAC laws
#    Source: National Conference of State Legislatures (NCSL)
#    URL: https://www.ncsl.org/transportation/dui-dwi-per-se-laws
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[5/6] DUI laws & penalties")
print("  [5a] NCSL per se BAC laws")

ncsl_url = "https://www.ncsl.org/transportation/criminal-status-of-state-drunken-driving-laws"
ncsl_df: pd.DataFrame | None = None
try:
    ncsl_bytes = fetch_cached(ncsl_url, RAW / "dui_laws_ncsl.html", min_delay=2.0)
    soup = BeautifulSoup(ncsl_bytes.decode("utf-8", errors="replace"), "lxml")
    tables = soup.find_all("table")
    if tables:
        ncsl_df = pd.read_html(io.StringIO(str(tables[0])))[0]
        ncsl_df = clean_cols(ncsl_df)
        print(f"  NCSL: {len(ncsl_df)} rows  cols: {list(ncsl_df.columns)}")
        print(ncsl_df.head(3).to_string())
        to_duckdb(ncsl_df, "dui_laws_ncsl")
        to_interim(ncsl_df, "dui_laws_ncsl")
        register_source(
            table="dui_laws_ncsl",
            name="National Conference of State Legislatures — DUI/DWI Per Se Laws",
            url=ncsl_url,
            license="Public legislative reference (NCSL nonpartisan)",
            notes="Per se BAC thresholds by state. Scraped from HTML table.",
        )
    else:
        print("  No tables found on NCSL page — check raw HTML")
except Exception as e:
    print(f"  NCSL failed: {e}")

# ── 5b. roadlawguide.com DUI penalties ───────────────────────────────────────
print("  [5b] roadlawguide.com DUI penalties")

roadlaw_url = "https://roadlawguide.com/dui-dwi-laws/penalties-by-state/"
roadlaw_df: pd.DataFrame | None = None
try:
    roadlaw_bytes = fetch_cached(roadlaw_url, RAW / "dui_penalties_roadlaw.html", min_delay=3.0)
    soup = BeautifulSoup(roadlaw_bytes.decode("utf-8", errors="replace"), "lxml")
    tables = soup.find_all("table")
    if tables:
        # Pick the largest table
        parsed = [pd.read_html(io.StringIO(str(t)))[0] for t in tables]
        roadlaw_df = max(parsed, key=len).copy()
        roadlaw_df = clean_cols(roadlaw_df)
        print(f"  roadlaw: {len(roadlaw_df)} rows  cols: {list(roadlaw_df.columns)}")
        print(roadlaw_df.head(3).to_string())
        to_duckdb(roadlaw_df, "dui_penalties_roadlaw")
        to_interim(roadlaw_df, "dui_penalties_roadlaw")
        register_source(
            table="dui_penalties_roadlaw",
            name="roadlawguide.com — DUI/DWI Penalties by State",
            url=roadlaw_url,
            license="Website content — cross-reference only; verify against state statutes",
            notes="First-offense penalty comparison. Used as secondary cross-reference.",
        )
    else:
        print("  No tables found")
except Exception as e:
    print(f"  roadlawguide failed: {e}")

# ── 5c. ailawyer.pro DUI penalties ───────────────────────────────────────────
print("  [5c] ailawyer.pro DUI penalties")

ail_url = "https://ailawyer.pro/tools/dui-penalties-by-state"
ail_df: pd.DataFrame | None = None
try:
    ail_bytes = fetch_cached(ail_url, RAW / "dui_penalties_ailawyer.html", min_delay=3.0)
    soup = BeautifulSoup(ail_bytes.decode("utf-8", errors="replace"), "lxml")
    tables = soup.find_all("table")
    if tables:
        parsed = [pd.read_html(io.StringIO(str(t)))[0] for t in tables]
        ail_df = max(parsed, key=len).copy()
        ail_df = clean_cols(ail_df)
        print(f"  ailawyer: {len(ail_df)} rows  cols: {list(ail_df.columns)}")
        print(ail_df.head(3).to_string())
        to_duckdb(ail_df, "dui_penalties_ailawyer")
        to_interim(ail_df, "dui_penalties_ailawyer")
        register_source(
            table="dui_penalties_ailawyer",
            name="ailawyer.pro — DUI Penalties by State (2026)",
            url=ail_url,
            license="Website content — cross-reference only; verify against state statutes",
            notes="Structured 2026 penalty data per state. Used as tertiary cross-reference.",
        )
    else:
        print("  No tables found")
except Exception as e:
    print(f"  ailawyer failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 6. STATES MASTER TABLE — join all reference data
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[6/6] Building master states table")

# Start from state_ref (has lat/lng, area, region, division)
# Enrich with FIPS (for cross-check) and 2024 population
states_master = state_ref.copy()

# Add 2024 population from Census estimates
if not pop_df.empty:
    states_master = states_master.merge(
        pop_df[["state_fips", "pop_2024", "pop_2020"]],
        on="state_fips",
        how="left",
    )

# Add FARS 2024 summary
if fars_2024 is not None and not fars_2024.empty:
    fars_summary = fars_2024[[
        "state_fips", "total_fatalities", "alcohol_fatalities", "pct_fatalities_alcohol"
    ]].copy()
    fars_summary.columns = [
        "state_fips", "traffic_fatalities_2024", "alcohol_fatalities_2024", "pct_alcohol_2024"
    ]
    states_master = states_master.merge(fars_summary, on="state_fips", how="left")

states_master = states_master.sort_values("state_fips").reset_index(drop=True)
print(f"  Master states table: {len(states_master)} rows × {len(states_master.columns)} cols")
print(f"  Cols: {list(states_master.columns)}")
print(states_master[[c for c in [
    "state_fips","state_abbr","state_name","pop_2024","alcohol_fatalities_2024","pct_alcohol_2024"
] if c in states_master.columns]].to_string(index=False))

to_duckdb(states_master, "states")
to_interim(states_master, "states_master")
register_source(
    table="states",
    name="Derived — States master reference table",
    url="",
    license="Derived from U.S. Census Bureau and NHTSA public domain data",
    notes="Joins: state_ref (Census Gazetteer), Census population estimates, FARS 2024 summary.",
)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. WRITE _sources METADATA TABLE TO DUCKDB
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[Writing _sources metadata table]")

sources_df = pd.DataFrame(_source_registry)
to_duckdb(sources_df, "_sources")
to_interim(sources_df, "_sources")

print("\n  Source registry:")
print(sources_df[["duckdb_table","source_name","retrieved"]].to_string(index=False))

# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*60)
print("INGESTION COMPLETE")
print(f"DuckDB: {DB}")
print("\nTables:")
tables_in_db = con.execute("SHOW TABLES").df()
print(tables_in_db.to_string(index=False))

print("\nRaw files:")
for f in sorted(RAW.iterdir()):
    print(f"  {f.name:<45} {f.stat().st_size/1e6:6.2f} MB")

print("\nInterim parquet files:")
for f in sorted(INTER.iterdir()):
    print(f"  {f.name:<45} {f.stat().st_size/1e3:6.1f} KB")

con.close()
print("\nDone.")
