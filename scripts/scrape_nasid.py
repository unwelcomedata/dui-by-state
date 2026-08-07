"""
scrape_nasid.py — Scrape NASID state enforcement data from state pages.

Source: National Alliance to Stop Impaired Driving (nasid.org)
Each state page has standardized fields covering enforcement procedures.

Output: data/raw/nasid_enforcement.csv
        data/interim/nasid_enforcement.parquet
        DuckDB table: nasid_enforcement

Run: /opt/anaconda3/envs/data_projects/bin/python scripts/scrape_nasid.py
"""

import re
import time
from pathlib import Path

import duckdb
import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent.parent
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
DB = ROOT / "data" / "project.duckdb"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

# State slugs for NASID URLs
STATES = {
    "01": ("AL", "Alabama", "alabama"),
    "02": ("AK", "Alaska", "alaska"),
    "04": ("AZ", "Arizona", "arizona"),
    "05": ("AR", "Arkansas", "arkansas"),
    "06": ("CA", "California", "california"),
    "08": ("CO", "Colorado", "colorado"),
    "09": ("CT", "Connecticut", "connecticut"),
    "10": ("DE", "Delaware", "delaware"),
    "11": ("DC", "District of Columbia", "district-of-columbia"),
    "12": ("FL", "Florida", "florida"),
    "13": ("GA", "Georgia", "georgia"),
    "15": ("HI", "Hawaii", "hawaii"),
    "16": ("ID", "Idaho", "idaho"),
    "17": ("IL", "Illinois", "illinois"),
    "18": ("IN", "Indiana", "indiana"),
    "19": ("IA", "Iowa", "iowa"),
    "20": ("KS", "Kansas", "kansas"),
    "21": ("KY", "Kentucky", "kentucky"),
    "22": ("LA", "Louisiana", "louisiana"),
    "23": ("ME", "Maine", "maine"),
    "24": ("MD", "Maryland", "maryland"),
    "25": ("MA", "Massachusetts", "massachusetts"),
    "26": ("MI", "Michigan", "michigan"),
    "27": ("MN", "Minnesota", "minnesota"),
    "28": ("MS", "Mississippi", "mississippi"),
    "29": ("MO", "Missouri", "missouri"),
    "30": ("MT", "Montana", "montana"),
    "31": ("NE", "Nebraska", "nebraska"),
    "32": ("NV", "Nevada", "nevada"),
    "33": ("NH", "New Hampshire", "new-hampshire"),
    "34": ("NJ", "New Jersey", "new-jersey"),
    "35": ("NM", "New Mexico", "new-mexico"),
    "36": ("NY", "New York", "new-york"),
    "37": ("NC", "North Carolina", "north-carolina"),
    "38": ("ND", "North Dakota", "north-dakota"),
    "39": ("OH", "Ohio", "ohio"),
    "40": ("OK", "Oklahoma", "oklahoma"),
    "41": ("OR", "Oregon", "oregon"),
    "42": ("PA", "Pennsylvania", "pennsylvania"),
    "44": ("RI", "Rhode Island", "rhode-island"),
    "45": ("SC", "South Carolina", "south-carolina"),
    "46": ("SD", "South Dakota", "south-dakota"),
    "47": ("TN", "Tennessee", "tennessee"),
    "48": ("TX", "Texas", "texas"),
    "49": ("UT", "Utah", "utah"),
    "50": ("VT", "Vermont", "vermont"),
    "51": ("VA", "Virginia", "virginia"),
    "53": ("WA", "Washington", "washington"),
    "54": ("WV", "West Virginia", "west-virginia"),
    "55": ("WI", "Wisconsin", "wisconsin"),
    "56": ("WY", "Wyoming", "wyoming"),
}

# Fields we want to extract
FIELDS_OF_INTEREST = [
    "Administrative License Suspension/Revocation",
    "DUI Look-back Periods",
    "Enhanced Penalties for High-BAC",
    "Felony DUI",
    "Open Container - Alcohol",
    "Sobriety Checkpoints",
    "No Refusal Programs",
    "Ignition Interlocks",
    "DUID: Implied Consent Testing Methods",
    "ALR Laws",
    "Social Host Laws",
    "Roadside Preliminary Breath Test (PBT) Laws",
]


def parse_state_page(html: str) -> dict:
    """Extract enforcement data fields from a NASID state page."""
    soup = BeautifulSoup(html, "lxml")
    data = {}

    # The page has structured sections — look for field labels and their values
    text = soup.get_text(separator="\n")
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    for i, line in enumerate(lines):
        for field in FIELDS_OF_INTEREST:
            if line == field and i + 1 < len(lines):
                # Next non-empty line is the value
                value = lines[i + 1]
                # Clean up field name for column use
                col = re.sub(r"[^a-z0-9]+", "_", field.lower()).strip("_")
                data[col] = value
                break

    return data


def main():
    records = []
    failed = []

    print(f"Scraping {len(STATES)} state pages from nasid.org...")
    for fips, (abbr, name, slug) in STATES.items():
        url = f"https://nasid.org/state/{slug}/"
        try:
            time.sleep(1.5)  # Polite rate limiting
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()

            data = parse_state_page(r.text)
            data["state_fips"] = fips
            data["state_abbr"] = abbr
            data["state_name"] = name
            records.append(data)
            print(f"  ✓ {abbr} ({len(data) - 3} fields)")

        except Exception as e:
            print(f"  ✗ {abbr}: {e}")
            failed.append((abbr, str(e)))
            records.append({"state_fips": fips, "state_abbr": abbr, "state_name": name})

    df = pd.DataFrame(records)

    # Reorder columns: identifiers first
    id_cols = ["state_fips", "state_abbr", "state_name"]
    other_cols = [c for c in df.columns if c not in id_cols]
    df = df[id_cols + sorted(other_cols)]

    print(f"\nTotal: {len(df)} states, {len(df.columns)} columns")
    print(f"Columns: {list(df.columns)}")
    if failed:
        print(f"\nFailed ({len(failed)}): {[f[0] for f in failed]}")

    # Save raw CSV
    csv_path = RAW / "nasid_enforcement.csv"
    df.to_csv(csv_path, index=False)
    print(f"\n→ CSV: {csv_path.name}")

    # Save interim parquet
    pq_path = INTERIM / "nasid_enforcement.parquet"
    df.to_parquet(pq_path, index=False, engine="pyarrow")
    print(f"→ Parquet: {pq_path.name}")

    # Load to DuckDB
    con = duckdb.connect(str(DB))
    con.execute("DROP TABLE IF EXISTS nasid_enforcement")
    con.execute("CREATE TABLE nasid_enforcement AS SELECT * FROM df")
    con.close()
    print(f"→ DuckDB: nasid_enforcement")

    # Quick summary
    print(f"\n{'='*50}")
    print("SAMPLE (first 5 states):")
    print(df.head().to_string(index=False))


if __name__ == "__main__":
    main()
