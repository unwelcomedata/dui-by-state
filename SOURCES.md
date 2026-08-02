# Data Sources — dui-by-state

All data used in this project is from official U.S. government sources or
hand-curated from those same sources. No data is sourced from Wikipedia or
other crowd-edited references.

---

## State Reference Data

### State FIPS Codes & Abbreviations
- **Source:** U.S. Census Bureau
- **File:** `state.txt`
- **URL:** https://www2.census.gov/geo/docs/reference/state.txt
- **Format:** Pipe-delimited text
- **Fields used:** STATE (FIPS numeric), STUSAB (2-letter abbreviation), STATE_NAME
- **License:** Public domain (U.S. government work)
- **Notes:** Official FIPS 5-2 state codes. Includes 50 states + DC + territories;
  project filters to 50 states + DC only.

### State Geographic Reference (lat/lng centroids, land area, Census region/division)
- **Source:** U.S. Census Bureau — 2024 Gazetteer Files (internal point coordinates
  and area measurements)
- **URL:** https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html
- **Format:** Hand-curated CSV stored at `data/raw/state_reference.csv`
- **Fields:** state_fips, state_abbr, state_name, lat, lng, land_area_sq_mi,
  water_area_sq_mi, region, division
- **License:** Public domain (U.S. government work)
- **Notes:** The Gazetteer file is WAF-protected against automated download.
  Values were transcribed manually from the official Census Gazetteer and the
  Census Bureau's regional classification. Lat/lng are Census internal points
  (not geographic centroids, not capital cities). Area figures are from the
  2020 Census. Regions and divisions follow the standard Census Bureau
  classification unchanged since 1984.
- **Last verified:** 2026-08-01

### State Population Estimates
- **Source:** U.S. Census Bureau — Population and Housing Unit Estimates
- **File:** `NST-EST2024-ALLDATA.csv`
- **URL:** https://www2.census.gov/programs-surveys/popest/datasets/2020-2024/state/totals/NST-EST2024-ALLDATA.csv
- **Format:** CSV
- **Fields used:** NAME, STATE (FIPS), POPESTIMATE2020–POPESTIMATE2024
- **License:** Public domain (U.S. government work)
- **Notes:** Annual state population estimates July 1 each year. 2024 estimates
  are the most recent available. Summary level 40 = state; project filters out
  national total (SUMLEV=10) and territories (STATE FIPS > 56).

---

## DUI / Traffic Safety Data

### NHTSA FARS — Fatality Analysis Reporting System (2015–2024)
- **Source:** National Highway Traffic Safety Administration (NHTSA)
- **URL pattern:** https://static.nhtsa.gov/nhtsa/downloads/FARS/{year}/National/FARS{year}NationalCSV.zip
- **Format:** ZIP containing CSV files
- **File used:** `accident.CSV` within each annual ZIP
- **Key fields:** ST_CASE, STATE, STATENAME, YEAR, FATALS, DRUNK_DR
- **License:** Public domain (U.S. government work)
- **Notes:** DRUNK_DR > 0 indicates at least one alcohol-impaired driver was
  involved in the crash. This is the gold-standard dataset for alcohol-impaired
  driving fatalities in the United States. Data covers all 50 states + DC.
  2024 data was first released April 2026.
- **Coverage:** 2015–2024 (10 years)

### NHTSA Traffic Safety Facts — State Alcohol-Impaired-Driving Estimates
- **Source:** National Highway Traffic Safety Administration (NHTSA) — CrashStats
- **URL:** https://crashstats.nhtsa.dot.gov/Api/Public/ViewPublication/813813
- **Format:** PDF
- **License:** Public domain (U.S. government work)
- **Notes:** Pre-aggregated state-level summary published annually. Includes
  alcohol-impaired fatalities per 100 million vehicle miles traveled (VMT).
  Used to cross-check FARS aggregate calculations.

---

## DUI Laws & Penalties

### NCSL — Per Se DUI/DWI Laws
- **Source:** National Conference of State Legislatures (NCSL)
- **URL:** https://www.ncsl.org/transportation/dui-dwi-per-se-laws
- **Format:** HTML table (scraped)
- **License:** Public domain legislative reference
- **Notes:** Most authoritative compiled source for state per se BAC laws.
  NCSL is a nonpartisan organization serving state legislatures.

### roadlawguide.com — DUI Penalties by State
- **Source:** roadlawguide.com
- **URL:** https://roadlawguide.com/dui-dwi-laws/penalties-by-state/
- **Format:** HTML (scraped)
- **Notes:** Structured first-offense penalty comparison table. Used as a
  secondary cross-reference. Always verify against official state statutes
  before publishing.

### ailawyer.pro — DUI Penalties by State
- **Source:** ailawyer.pro
- **URL:** https://ailawyer.pro/tools/dui-penalties-by-state
- **Format:** HTML (scraped)
- **Notes:** Structured penalty data per state for 2026. Used as tertiary
  cross-reference. Always verify against official state statutes.

---

## DUI Arrests

### FBI UCR — Arrests by Age, Sex, and Race, Summarized Yearly, 2023
- **Source:** Federal Bureau of Investigation, Uniform Crime Reporting Program
- **Distributor:** Inter-university Consortium for Political and Social Research (ICPSR)
- **Study:** ICPSR 39298
- **URL:** https://www.icpsr.umich.edu/web/NACJD/studies/39298
- **Format:** Tab-separated values (extracted from ZIP)
- **Fields used:** STATE (UCR code), OFFENSE (220=DUI), age/sex arrest counts
- **License:** ICPSR Terms of Use — no redistribution of raw data; derivative
  analysis and aggregated statistics permitted; citation required
- **Coverage:** 50 states + DC, 2023 (agency-level, aggregated to state)
- **Notes:** **Important limitation:** Not all law enforcement agencies report to
  UCR. State-level totals reflect only reporting agencies and significantly
  undercount actual arrests in most states. Coverage varies widely — some states
  have near-complete reporting, others report only a fraction of agencies. Use
  for relative comparisons and per-reporting-population rates, not as absolute
  arrest counts. Always note reporting coverage when publishing.
- **Citation:** United States Department of Justice. Federal Bureau of
  Investigation. Uniform Crime Reporting Program Data: Arrests by Age, Sex,
  and Race, Summarized Yearly, United States, 2023. Inter-university Consortium
  for Political and Social Research [distributor], 2026.
- **Retrieved:** 2026-08-02

---

## Alcohol Consumption

### NIAAA — Apparent Per Capita Alcohol Consumption by State (2022)
- **Source:** National Institute on Alcohol Abuse and Alcoholism (NIAAA)
- **Publication:** Surveillance Report #121
- **URL:** https://www.niaaa.nih.gov/sites/default/files/surveillance-report121.pdf
- **Format:** PDF — Table 2 extracted via `pdfplumber`
- **Fields used:** state_name, ethanol_per_capita_gallons_2022, consumption_decile_2022
- **License:** Public domain (U.S. government work)
- **Notes:** Per capita ethanol consumption in gallons for population ages 14+.
  Includes beer, wine, spirits, and all beverages combined. Decile 1 = highest
  consumption, 10 = lowest. National average 2022: 2.50 gallons.
- **Coverage:** 50 states + DC, 2022

---

## NHTSA Imputed Alcohol Fatality Estimates

### NHTSA Traffic Safety Facts — State Alcohol-Impaired-Driving Estimates 2024
- **Source:** NHTSA — CrashStats
- **URL:** https://crashstats.nhtsa.dot.gov/Api/Public/ViewPublication/813813
- **Format:** PDF — Table 2 extracted via `pdfplumber`
- **Fields used:** total_fatalities_2024, alcohol_impaired_fatalities_2024 (BAC≥.08),
  pct_alcohol_impaired_2024, high_bac_fatalities_2024 (BAC≥.15), pct_high_bac_2024
- **License:** Public domain (U.S. government work)
- **Notes:** Statistically imputed estimates — NHTSA uses multiple imputation to
  estimate BAC for untested drivers. More accurate than raw FARS coding. National
  2024: 11,907 alcohol-impaired fatalities (30% of 39,254 total).
- **Coverage:** 50 states + DC, 2024

---

## Notes on Data Quality & Verification

- All government source files are saved verbatim to `data/raw/` and never modified.
- Any discrepancies between scraped law/penalty sources should be resolved by
  consulting the official state statute directly.
- Population figures are estimates; the decennial Census (2020) is the only
  complete enumeration.
- FARS fatality figures may be revised in subsequent NHTSA releases; figures
  here reflect the first annual release.

---

## Source Provenance in DuckDB

Every table in `data/project.duckdb` has a corresponding entry in the
`_sources` metadata table:

```sql
SELECT * FROM _sources;
```

This table records the table name, source name, URL, license, and retrieval
date for every dataset loaded into the database.
