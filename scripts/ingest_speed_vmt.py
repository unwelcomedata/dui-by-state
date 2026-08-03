"""Ingest state max speed limits (IIHS) and VMT (FHWA) into DuckDB."""
import pandas as pd
import duckdb

print("Building state speed limits table (IIHS, August 2026)...", flush=True)

# State maximum speed limits from IIHS - rural interstates (highest posted)
# Source: https://www.iihs.org/research-areas/speed/speed-limit-laws
# Where ranges exist (e.g. "75; 80 on specified segments"), take the maximum.
speed_data = {
    "Alabama": 70, "Alaska": 65, "Arizona": 75, "Arkansas": 75,
    "California": 70, "Colorado": 75, "Connecticut": 65, "Delaware": 65,
    "District of Columbia": 55, "Florida": 70, "Georgia": 70, "Hawaii": 60,
    "Idaho": 80, "Illinois": 70, "Indiana": 70, "Iowa": 70,
    "Kansas": 75, "Kentucky": 70, "Louisiana": 75, "Maine": 75,
    "Maryland": 70, "Massachusetts": 65, "Michigan": 75, "Minnesota": 70,
    "Mississippi": 70, "Missouri": 75, "Montana": 80, "Nebraska": 75,
    "Nevada": 80, "New Hampshire": 70, "New Jersey": 65, "New Mexico": 75,
    "New York": 65, "North Carolina": 70, "North Dakota": 80,
    "Ohio": 70, "Oklahoma": 80, "Oregon": 70, "Pennsylvania": 70,
    "Rhode Island": 65, "South Carolina": 70, "South Dakota": 80,
    "Tennessee": 70, "Texas": 85, "Utah": 80, "Vermont": 65,
    "Virginia": 70, "Washington": 75, "West Virginia": 70,
    "Wisconsin": 70, "Wyoming": 80,
}

speed_df = pd.DataFrame([
    {"state_name": k, "max_speed_limit_mph": v} for k, v in speed_data.items()
])
print(f"  Speed limits: {len(speed_df)} states", flush=True)

# --- VMT by state ---
# FHWA Highway Statistics 2022 Table VM-2: Vehicle Miles Traveled
# Source: https://www.fhwa.dot.gov/policyinformation/statistics/2022/vm2.cfm
# Values in millions of miles. Using 2022 as the latest available full year.
print("Building VMT table (FHWA Highway Statistics 2022)...", flush=True)

vmt_data = {
    "Alabama": 71816, "Alaska": 5640, "Arizona": 72262, "Arkansas": 38324,
    "California": 346954, "Colorado": 55215, "Connecticut": 32543,
    "Delaware": 10676, "District of Columbia": 3628, "Florida": 229027,
    "Georgia": 131782, "Hawaii": 10537, "Idaho": 19895, "Illinois": 109222,
    "Indiana": 82776, "Iowa": 35010, "Kansas": 33913, "Kentucky": 50479,
    "Louisiana": 51143, "Maine": 15395, "Maryland": 59103,
    "Massachusetts": 62488, "Michigan": 102421, "Minnesota": 60352,
    "Mississippi": 40988, "Missouri": 74757, "Montana": 13654,
    "Nebraska": 22111, "Nevada": 28784, "New Hampshire": 14018,
    "New Jersey": 77651, "New Mexico": 26080, "New York": 123169,
    "North Carolina": 120783, "North Dakota": 10362, "Ohio": 117109,
    "Oklahoma": 51282, "Oregon": 36272, "Pennsylvania": 110791,
    "Rhode Island": 8284, "South Carolina": 59293, "South Dakota": 10740,
    "Tennessee": 82759, "Texas": 283508, "Utah": 33843, "Vermont": 7483,
    "Virginia": 88561, "Washington": 62122, "West Virginia": 20009,
    "Wisconsin": 66217, "Wyoming": 10398,
}

vmt_df = pd.DataFrame([
    {"state_name": k, "vmt_millions_2022": v} for k, v in vmt_data.items()
])
print(f"  VMT: {len(vmt_df)} states", flush=True)

# Merge and load
combined = speed_df.merge(vmt_df, on="state_name", how="outer")
print(f"  Combined: {len(combined)} states", flush=True)

# Save parquet
combined.to_parquet("data/interim/speed_limits_vmt.parquet", index=False)
print("Saved data/interim/speed_limits_vmt.parquet", flush=True)

# Load to DuckDB
con = duckdb.connect("data/project.duckdb")
con.execute("DROP TABLE IF EXISTS speed_limits_vmt")
df = combined
con.execute("CREATE TABLE speed_limits_vmt AS SELECT * FROM df")
n = con.execute("SELECT COUNT(*) FROM speed_limits_vmt").fetchone()[0]
con.close()
print(f"Loaded into DuckDB: speed_limits_vmt ({n} rows)", flush=True)
print("DONE", flush=True)
