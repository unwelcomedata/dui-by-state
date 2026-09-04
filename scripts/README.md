# Scripts — Pipeline Run Order

Full rebuild from raw data to export. Each step depends on the previous.

## Prerequisites

- Python 3.11+ with packages in `requirements.txt`
- `data/raw/` populated with source files (see SOURCES.md)
- Playwright + Chromium installed (for NASID scraping)

## Run order

```bash
# 1. Base ingestion — state ref, FIPS, population, FARS, NCSL, penalties, speed/VMT
python scripts/ingest_all.py

# 2. NASID scraping — enforcement data from nasid.org (requires Playwright)
python scripts/scrape_nasid.py

# 3. NASID cleaning — standardize raw text → booleans/categoricals
python scripts/clean_enforcement.py

# 4. BAC testing rates — extract from FARS 2024 person.csv
python scripts/compute_bac_testing_rates.py

# 5. Final export — join all tables → CSV/Excel/Parquet + codebook
python scripts/prepare_export_v4.py
```

## Script descriptions

| Script | Input | Output (DuckDB) | Notes |
|--------|-------|-----------------|-------|
| `ingest_all.py` | `data/raw/*` | 15+ tables | Main ingestion: state ref, FIPS, population, FARS (trends + 2024 + structural), NCSL, penalties, speed/VMT |
| `scrape_nasid.py` | nasid.org | `nasid_enforcement` | Playwright-based, cached. Rate-limited. |
| `clean_enforcement.py` | `nasid_enforcement` | `nasid_enforcement_clean` | Text → booleans. Post-hoc fix: NC/AR threshold corrected to 4. |
| `compute_bac_testing_rates.py` | `data/raw/fars_2024.zip` | `fars_bac_testing_2024` | Extracts BAC test type breakdown per state |
| `prepare_export_v4.py` | All clean tables | `export/dui_by_state_v4.*` | 51 rows × 48 cols. Generates codebook. |

## DuckDB tables

25 tables in `data/project.duckdb`. 11 are used directly in the export JOIN.
The remainder serve as audit trail, raw reference, or exploratory analysis support.
See `_sources` table for full provenance metadata.
