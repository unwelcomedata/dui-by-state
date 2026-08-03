"""Extract PREV_DWI and VSPD_LIM from FARS 2024, aggregate by state."""
import sys
import zipfile
import pandas as pd
import duckdb

print("Starting FARS structural extraction...", flush=True)

zf = zipfile.ZipFile("data/raw/fars_2024.zip")

print("Reading vehicle.csv...", flush=True)
with zf.open("FARS2024NationalCSV/vehicle.csv") as f:
    veh = pd.read_csv(f, usecols=["STATE", "ST_CASE", "VEH_NO", "PREV_DWI", "VSPD_LIM"])
print(f"  vehicle rows: {len(veh):,}", flush=True)

print("Reading drimpair.csv...", flush=True)
with zf.open("FARS2024NationalCSV/drimpair.csv") as f:
    dr = pd.read_csv(f, usecols=["STATE", "ST_CASE", "VEH_NO", "DRIMPAIR"])
print(f"  drimpair rows: {len(dr):,}", flush=True)

# Mark impaired vehicles (alcohol = code 9)
imp = dr[dr["DRIMPAIR"] == 9][["STATE", "ST_CASE", "VEH_NO"]].drop_duplicates()
imp["is_impaired"] = 1
veh = veh.merge(imp, on=["STATE", "ST_CASE", "VEH_NO"], how="left")
veh["is_impaired"] = veh["is_impaired"].fillna(0).astype(int)
print(f"  impaired drivers: {veh['is_impaired'].sum():,}", flush=True)

# Filter known prior DWI (exclude 98, 99, 998)
veh_known = veh[~veh["PREV_DWI"].isin([98, 99, 998])].copy()
veh_known["has_prior"] = (veh_known["PREV_DWI"] > 0).astype(int)

print("Aggregating by state...", flush=True)

# Prior DWI stats - all drivers
all_agg = veh_known.groupby("STATE").agg(
    total_drivers_known_history=("has_prior", "count"),
    drivers_with_prior_dwi=("has_prior", "sum"),
).reset_index()

# Prior DWI stats - impaired drivers only
imp_agg = veh_known[veh_known["is_impaired"] == 1].groupby("STATE").agg(
    impaired_drivers_known_history=("has_prior", "count"),
    impaired_with_prior_dwi=("has_prior", "sum"),
).reset_index()

priors = all_agg.merge(imp_agg, on="STATE", how="left")
priors["pct_impaired_with_prior_dwi"] = (
    priors["impaired_with_prior_dwi"] * 100.0
    / priors["impaired_drivers_known_history"]
).round(1)
priors["pct_all_with_prior_dwi"] = (
    priors["drivers_with_prior_dwi"] * 100.0
    / priors["total_drivers_known_history"]
).round(1)

# Speed limit stats
veh_sp = veh[(veh["VSPD_LIM"] > 0) & (veh["VSPD_LIM"] < 98)]
speed_agg = veh_sp.groupby("STATE")["VSPD_LIM"].agg(
    median_crash_speed_limit="median",
    mean_crash_speed_limit="mean",
).reset_index()
speed_agg["mean_crash_speed_limit"] = speed_agg["mean_crash_speed_limit"].round(1)

# Pct high speed
high_sp = veh_sp[veh_sp["VSPD_LIM"] >= 55].groupby("STATE").size().reset_index(name="n_high")
total_sp = veh_sp.groupby("STATE").size().reset_index(name="n_total")
pct_high = high_sp.merge(total_sp, on="STATE")
pct_high["pct_crashes_high_speed"] = (pct_high["n_high"] * 100.0 / pct_high["n_total"]).round(1)

speed_agg = speed_agg.merge(pct_high[["STATE", "pct_crashes_high_speed"]], on="STATE", how="left")

# Combine
result = priors.merge(speed_agg, on="STATE", how="outer")
result["state_fips"] = result["STATE"].apply(lambda x: f"{int(x):02d}")
result = result.drop(columns=["STATE"])

print(f"\nResult: {len(result)} states", flush=True)
print(result[["state_fips", "pct_impaired_with_prior_dwi",
              "median_crash_speed_limit", "pct_crashes_high_speed"]].head(5).to_string(),
      flush=True)

# Save interim parquet
result.to_parquet("data/interim/fars_prior_dwi_speed.parquet", index=False)
print("\nSaved data/interim/fars_prior_dwi_speed.parquet", flush=True)

# Load into DuckDB
con = duckdb.connect("data/project.duckdb")
con.execute("DROP TABLE IF EXISTS fars_prior_dwi_speed")
df = result
con.execute("CREATE TABLE fars_prior_dwi_speed AS SELECT * FROM df")
n = con.execute("SELECT COUNT(*) FROM fars_prior_dwi_speed").fetchone()[0]
con.close()
print(f"Loaded into DuckDB: fars_prior_dwi_speed ({n} rows)", flush=True)
print("DONE", flush=True)
