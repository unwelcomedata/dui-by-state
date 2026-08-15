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

## DUI Enforcement & Procedures

### Sobriety Checkpoint Legality
- **Source:** Multiple legal references (Governors Highway Safety Association,
  state constitutions, case law)
- **Method:** Compiled from verified legal references — 12 states ban checkpoints
- **License:** Public legislative reference
- **States banning checkpoints:** AK, ID, IA, MI, MN, MT, OR, RI, TX, WA, WI, WY

### NCSL — State Ignition Interlock Laws (All-Offender)
- **Source:** National Conference of State Legislatures
- **URL:** https://www.ncsl.org/research/transportation/state-ignition-interlock-laws.aspx
- **Format:** HTML table (scraped)
- **License:** Public domain legislative reference
- **Notes:** `all_offender` = "Yes" means IID mandatory for all DUI offenders
  including first offense. 31 states as of 2024.

### Implied Consent & Refusal Penalties
- **Source:** Foundation for Advancing Alcohol Responsibility (responsibility.org)
- **URL:** https://www.responsibility.org/wp-content/uploads/2026/01/Implied-Consent-Refusal-Penalties_Aug-2025.pdf
- **Format:** PDF (96 pages of statutory text per state)
- **License:** Public reference
- **Notes:** All 50 states + DC have implied consent. 17 states impose criminal
  penalties (jail/fine) for test refusal; all others impose administrative
  suspension only. Wyoming is the only state without refusal penalties.

### Open Container Laws
- **Source:** NHTSA / federal compliance records
- **Notes:** 40 states meet federal open container standards. 11 states allow
  open alcohol containers in vehicles under some circumstances.

### BAC Limits
- **Notes:** All states: 0.08 g/dL. Utah: 0.05 g/dL (lowest in U.S., effective 2018).

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

## Structural Controls (added for analysis depth)

### FARS 2024 — Prior DWI Convictions & Crash Speed Limits
- **Source:** NHTSA FARS 2024 — `vehicle.csv`
- **URL:** https://static.nhtsa.gov/nhtsa/downloads/FARS/2024/National/FARS2024NationalCSV.zip
- **Fields used:** `PREV_DWI` (prior DWI convictions), `VSPD_LIM` (posted speed limit
  at crash location); joined with `drimpair.csv` code 9 to identify impaired drivers
- **License:** Public domain (U.S. government work)
- **Notes:** Aggregated to state level. `PREV_DWI` is a count of prior DWI
  convictions found on the driver's record. Codes 98/99/998 = unknown and are
  excluded. Key finding: the vast majority (85–95%) of impaired drivers in fatal
  crashes have no prior DWI conviction on record.
- **Coverage:** 50 states + DC, 2024
- **Retrieved:** 2026-08-03

### IIHS — Maximum Posted Speed Limits
- **Source:** Insurance Institute for Highway Safety (IIHS)
- **URL:** https://www.iihs.org/research-areas/speed/speed-limit-laws
- **Format:** HTML table (transcribed)
- **Fields used:** Rural interstate maximum posted speed limit per state
- **License:** IIHS public reference
- **Notes:** Reflects maximum posted limits including "specified segments of road"
  where higher limits apply (e.g., Idaho 80 mph on some interstates). Range: 55 mph
  (DC) to 85 mph (Texas).
- **Last verified:** August 2026

### FHWA — Vehicle Miles Traveled by State (2022)
- **Source:** Federal Highway Administration — Highway Statistics 2022, Table VM-2
- **URL:** https://www.fhwa.dot.gov/policyinformation/statistics/2022/vm2.cfm
- **Format:** Tabular (transcribed from published table)
- **Fields used:** Annual vehicle miles traveled in millions
- **License:** Public domain (U.S. government work)
- **Notes:** 2022 is the latest complete year available. Used to compute fatality
  rate per 100 million VMT — the standard road safety comparison metric that
  controls for how much driving occurs in a state.
- **Retrieved:** 2026-08-03

---

## BAC Testing Rates & Laws

### FARS 2024 — BAC Testing Rates by State
- **Source:** NHTSA FARS 2024 — `person.csv`
- **URL:** https://static.nhtsa.gov/nhtsa/downloads/FARS/2024/National/FARS2024NationalCSV.zip
- **Computed from:** `ALC_STATUS` field (0=Test Not Given, 2=Test Given, 8=Not Reported, 9=Unknown)
- **License:** Public domain (U.S. government work)
- **Fields:** pct_bac_known_killed, pct_bac_known_all, pct_bac_known_surviving,
  pct_blood_test (blood vs breath/PBT share), test type counts by state
- **DuckDB table:** `fars_bac_testing_2024`
- **Notes:** Computed percentage of drivers in fatal crashes with known BAC test
  results, broken out by killed vs surviving. National avg: 66.8% of killed
  drivers have known BAC. Range: 9.6% (Mississippi) to 97.7% (Vermont).
  States with mandatory coroner/ME testing laws average 78.2% vs 51.7% for
  probable-cause states.
- **Retrieved:** 2026-08-07

### State Mandatory BAC Testing Laws
- **Source:** Hand-curated from NHTSA Casanova et al. 2012 (DOT HS 811 661) +
  current state statutes
- **Reference URL:** https://rosap.ntl.bts.gov/view/dot/1940
- **Format:** CSV (`data/raw/bac_testing_laws.csv`)
- **Fields:** mandatory_testing_law, testing_scope, testing_authority,
  no_refusal_program, statute_citation, notes
- **License:** Public domain (legislative references)
- **DuckDB table:** `bac_testing_laws`
- **Notes:** 29 states require BAC testing of fatally injured drivers via
  coroner/ME statute. 22 states use probable-cause only. The Casanova 2012
  NHTSA report identified 25 mandatory states; we updated with 4 additional
  states that have enacted similar statutes since. Each entry includes the
  specific statute citation.
- **Retrieved:** 2026-08-07

---

## DUI Enforcement Procedures (NASID)

### NASID — State DUI Enforcement Laws Database
- **Source:** National Alliance to Stop Impaired Driving (NASID)
- **URL:** https://nasid.org/state/{state-slug}/
- **Format:** HTML state pages (scraped 51 pages)
- **License:** Public reference (data sourced from NHTSA/FARS, May 2024)
- **DuckDB tables:** `nasid_enforcement` (raw text), `nasid_enforcement_clean` (standardized)
- **Fields (12 per state):**
  - Sobriety Checkpoints (permitted/prohibited)
  - No Refusal Programs (active/authorized/not authorized)
  - Roadside PBT Laws (authorized/not explicit)
  - Ignition Interlocks (mandatory_all/high_bac_repeat/repeat/discretionary)
  - Felony DUI threshold (2nd/3rd/4th offense)
  - DUI Look-back Period (5–lifetime years)
  - Enhanced High-BAC Threshold (0.15–0.20)
  - Open Container compliance (federal compliant/non-compliant)
  - Implied Consent Testing Methods (blood/breath/urine/oral fluid)
  - ALS/ALR (administrative license suspension enacted)
  - Social Host Laws
  - ALR/Hardship license
- **Retrieved:** 2026-08-07
- **Notes:** Key distributions: 39 states permit checkpoints; 9 actively use
  no-refusal programs; 32 have mandatory-all-offender IID; 33 explicitly
  authorize PBT; 48 have felony DUI laws; 47 have enhanced high-BAC penalties.

---

## Source Provenance in DuckDB

Every table in `data/project.duckdb` has a corresponding entry in the
`_sources` metadata table:

```sql
SELECT * FROM _sources;
```

This table records the table name, source name, URL, license, and retrieval
date for every dataset loaded into the database.

---

## Body-Worn Camera Laws

### NCSL Body-Worn Camera Laws Database
- **Source:** National Conference of State Legislatures (NCSL)
- **URL:** https://www.ncsl.org/civil-and-criminal-justice/body-worn-camera-laws-database
- **Format:** HTML text → hand-curated CSV (`data/raw/body_cam_laws_ncsl.csv`)
- **Fields:** state_abbr, state_name, has_bwc_law, mandate_statewide, funding_provided,
  retention_policy, foia_provisions, year_first_law, notes
- **License:** Public domain (legislative information)
- **Retrieved:** 2025-08-07
- **DuckDB table:** `body_cam_laws`
- **Notes:** 34 states + DC have enacted BWC legislation. 8 states mandate
  statewide use (CO, CT, DE, IL, MD, NJ, NM, SC). Data coded from NCSL
  narrative descriptions by categorizing: (1) whether a mandate exists,
  (2) whether state funding was appropriated, (3) whether retention periods
  are specified, and (4) whether FOIA/public records provisions address BWC
  footage. Not all nuance is captured — see notes field for details.

---

## Vehicle Impound / Seizure / Forfeiture Laws

### Vehicle Sanctions by State
- **Source:** NHTSA Countermeasures That Work (2023), NHTSA DOT HS 811 028B (2008),
  CDC MV PICCS, individual state statutes
- **Primary URL:** https://www.nhtsa.gov/book/countermeasures-that-work/alcohol-impaired-driving/countermeasures/other-strategies-behavior-5
- **Secondary URL:** https://www.cdc.gov/transportation-safety/calculator/impoundment.html
- **Format:** Hand-curated CSV stored at `data/raw/vehicle_impound_laws.csv`
- **Fields:** state_fips, state_abbr, state_name, vehicle_impound_law, impound_trigger,
  impound_mandatory, impound_duration_days, vehicle_forfeiture_law, forfeiture_trigger,
  plate_impound_law, source_note
- **License:** Public domain (U.S. government work)
- **Retrieved:** 2026-08-15
- **Notes:** Compiled from NHTSA's "Countermeasures That Work" (11th edition, 2023)
  and "Update of Vehicle Sanction Laws and Their Application, Vol. II" (DOT HS 811 028B,
  2008), CDC MV PICCS intervention documentation, and current state statutes verified
  via official .gov statute databases. Distinguishes between mandatory vehicle
  impound (automatic upon arrest/conviction) and discretionary (at officer/court
  discretion). Covers impound, immobilization, forfeiture, and plate impound.
