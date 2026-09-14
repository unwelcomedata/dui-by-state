#!/usr/bin/env python3
"""Pre-publish validation — re-check the chart data before anything goes public.

Re-derives the felony-threshold categories the choropleth shows (straight from
the published export parquet), confirms the per-category state counts match the
map legend and sum to 51, and checks social/web chart parity.

Exit code 0 = safe to publish. Non-zero = do NOT publish.

Usage:
    .venv/bin/python scripts/validate_charts.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parent
while not (PROJECT / "config.yaml").exists() and PROJECT != PROJECT.parent:
    PROJECT = PROJECT.parent

failures: list[str] = []
checks: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        checks.append(f"  PASS  {name}")
    else:
        failures.append(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


def _felony_label(row) -> str:
    if row["has_felony_dui"] == 0:
        return "Always a misdemeanor"
    t = row["felony_dui_threshold"]
    if pd.isna(t):
        return "Always a misdemeanor"
    t = int(t)
    return {2: "Felony on 2nd", 3: "Felony on 3rd", 4: "Felony on 4th"}.get(
        t, f"Felony on {t}th"
    )


def main() -> int:
    df = pd.read_parquet(PROJECT / "export" / "dui_by_state_v4.parquet")

    # ── Coverage: all 51 jurisdictions (50 states + DC) ───────────────────
    check("export covers 51 jurisdictions", len(df) == 51, f"got {len(df)}")

    # ── Felony-threshold categories (choropleth 1) reconcile to the legend ─
    counts = df.apply(_felony_label, axis=1).value_counts().to_dict()
    expected = {
        "Felony on 3rd": 24,
        "Felony on 4th": 20,
        "Felony on 2nd": 4,
        "Always a misdemeanor": 3,
    }
    for cat, n in expected.items():
        check(f"felony category '{cat}' has {n} states",
              counts.get(cat, 0) == n, f"got {counts.get(cat, 0)}")
    check("felony categories sum to 51", sum(counts.values()) == 51,
          f"sum {sum(counts.values())}")

    # ── Social vs web chart parity (when rendered outputs are present) ────
    social = sorted((PROJECT / "outputs" / "social").glob("*.png"))
    web_dir = PROJECT / "outputs" / "web"
    if social and web_dir.exists():
        s_names = {p.name for p in social}
        w_names = {p.name for p in web_dir.glob("*.png")}
        check("social and web sets cover the same filenames", s_names == w_names,
              f"only social: {sorted(s_names - w_names)}; only web: {sorted(w_names - s_names)}")
        try:
            from PIL import Image
            dims = {Image.open(p).size for p in web_dir.glob("*.png")}
            check("every web chart is the web canvas 1664x936", dims == {(1664, 936)},
                  f"unexpected: {sorted(dims)}")
        except ImportError:
            pass

    print("Pre-publish chart-data validation — dui-by-state")
    print("=" * 60)
    for line in checks:
        print(line)
    for line in failures:
        print(line)
    print("=" * 60)
    if failures:
        print(f"RESULT: {len(failures)} FAILURE(S) — DO NOT PUBLISH.")
        return 1
    print(f"RESULT: all {len(checks)} checks passed — safe to publish.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
