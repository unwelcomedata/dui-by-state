# dui-by-state

Alcohol-impaired driving data by U.S. state: fatalities, arrest rates, and
laws & penalties. Built for analysis, visualization, and dataset packaging.

> **AI-Assisted Development**
> This project was built with the assistance of [Kiro](https://kiro.dev),
> an AI-powered development environment. All data sourcing decisions,
> methodology choices, and published findings are the responsibility of the
> author. AI was used for code generation, data pipeline construction, and
> research assistance — not for analysis conclusions or editorial judgment.

---

## Data Sources

All data is sourced from official U.S. government publications. Full
attribution, URLs, licenses, and retrieval notes are in [SOURCES.md](SOURCES.md).

| Dataset | Source | Coverage |
|---|---|---|
| State FIPS / abbreviations | U.S. Census Bureau | 50 states + DC |
| State geography (area, lat/lng, region) | U.S. Census Bureau Gazetteer | 50 states + DC |
| State population estimates | U.S. Census Bureau | 2020–2024 |
| Alcohol-impaired driving fatalities | NHTSA FARS | 2015–2024 |
| DUI laws & penalties | NCSL, state statutes | 50 states + DC |

---

## Project Structure

```
dui-by-state/
├── config.yaml              ← sources, paths, export settings
├── SOURCES.md               ← full data source attribution
├── requirements.txt
├── data/
│   ├── raw/                 ← original downloaded files, never modified
│   │   └── state_reference.csv  ← hand-curated Census gazetteer data
│   ├── interim/             ← cleaned Parquet files
│   └── processed/           ← analysis-ready Parquet files
├── export/                  ← packaged datasets (CSV, Excel, Parquet + codebook)
├── outputs/                 ← chart PNGs for publishing
├── notebooks/
│   ├── 01-ingest.ipynb      ← fetch sources → data/raw/ → DuckDB
│   ├── 02-clean.ipynb       ← clean + quality checks → data/interim/
│   ├── 03-prepare.ipynb     ← feature engineering + export packaging
│   └── 04-viz.ipynb         ← social charts → outputs/
└── src/
    ├── ingest.py            ← fetch helpers
    ├── clean_quality.py     ← DuckDB cleaning + quality reports
    ├── prepare.py           ← PII stripping, codebook, packaging
    └── viz.py               ← chart builders + social export
```

---

## Quickstart

```bash
cd dui-by-state
source .venv/bin/activate      # or: conda activate data_projects
jupyter lab                    # open notebooks in browser, or open in Kiro
```

Then work through the notebooks in order: 01 → 02 → 03 → 04.

## DuckDB

All data loads into a single project database at `data/project.duckdb`.
Source provenance is recorded in the `_sources` metadata table:

```sql
SELECT * FROM _sources;
```

---

## Anonymity

Commits are authored as `unwelcomedata` to keep the author's real identity
off the public commit history. Data files, exports, outputs, and `.env`
secrets are excluded from version control via `.gitignore`.
