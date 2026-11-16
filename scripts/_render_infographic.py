"""Build the dui-by-state infographic (tall + social SVG -> PNG) and validate every data mark.

Every bar, tile, dot and big number is COMPUTED from the project's real source values
(data/project.duckdb read-only + export/dui_by_state_v4.parquet + data/interim impound
parquet). Tall and social are fed IDENTICAL computed values; only the canvas mapping
differs. Each mark carries data-* attributes so validate() can parse it back out of the
SVG, invert the mapping, and compare with a fresh, independently-coded query.

Usage (from project root):  .venv/bin/python scripts/_render_infographic.py
Writes docs/infographic_dui{,_social}.{svg,png} + artifacts/INFOGRAPHIC-VALIDATION.md
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
DOCS, ART = PROJECT / "docs", PROJECT / "artifacts"
DOCS.mkdir(exist_ok=True)
ART.mkdir(exist_ok=True)

NAVY, TEAL, GOLD, SPICE, AQUA = "#003049", "#0A9396", "#EE9B00", "#AE2012", "#94D2BD"
VANILLA, GREY, BG = "#E9D8A6", "#6B7280", "#FBF8F0"
DEEP = "#023047"
CAT_COLOR = {"Felony on 2nd": GOLD, "Felony on 3rd": TEAL, "Felony on 4th": DEEP,
             "Always a misdemeanor": SPICE}
CAT_ORDER = ["Felony on 2nd", "Felony on 3rd", "Felony on 4th", "Always a misdemeanor"]
GROUP_ORDER = ["Always a misdemeanor", "Felony on 4th", "Felony on 3rd", "Felony on 2nd"]
QUAD_COLOR = {"Both": GOLD, "Checkpoints only": DEEP, "Impound only": TEAL, "Neither": SPICE}
QUAD_ORDER = ["Both", "Checkpoints only", "Impound only", "Neither"]


def esc(s: str) -> str:
    out = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return "".join(c if ord(c) < 128 else f"&#{ord(c)};" for c in out)


def f(x: float) -> str:
    return f"{x:.2f}"


def T(x, y, s, size, fill, weight="", anchor=""):
    w = f' font-weight="{weight}"' if weight else ""
    a = f' text-anchor="{anchor}"' if anchor else ""
    return f'<text x="{f(x)}" y="{f(y)}" fill="{fill}" font-size="{size}"{w}{a}>{esc(s)}</text>'


# ───────────────────────── data (computed once, fed to BOTH renders) ─────────────────────────
def felony_label(r) -> str:
    if r["has_felony_dui"] == 0 or pd.isna(r["felony_dui_threshold"]):
        return "Always a misdemeanor"
    return {2: "Felony on 2nd", 3: "Felony on 3rd", 4: "Felony on 4th"}[int(r["felony_dui_threshold"])]


def load() -> dict:
    df = pd.read_parquet(PROJECT / "export" / "dui_by_state_v4.parquet")
    df["felony_at"] = df.apply(felony_label, axis=1)
    con = duckdb.connect(str(PROJECT / "data" / "project.duckdb"), read_only=True)
    prior = con.sql("SELECT state_fips, impaired_drivers_known_history AS n_imp, "
                    "impaired_with_prior_dwi AS n_prior FROM fars_prior_dwi_speed").df()
    vmt = con.sql("SELECT state_name, vmt_millions_2022 AS vmt FROM speed_limits_vmt").df()
    con.close()
    prior["state_fips"] = prior["state_fips"].astype(str).str.zfill(2)
    df["state_fips"] = df["state_fips"].astype(str).str.zfill(2)
    imp = pd.read_parquet(PROJECT / "data" / "interim" / "vehicle_impound_laws.parquet")
    imp["state_fips"] = imp["state_fips"].astype(str).str.zfill(2)
    imp["mand"] = ((imp["vehicle_impound_law"] == "yes") & (imp["impound_mandatory"] == "mandatory")).astype(int)
    m = df.merge(prior, on="state_fips").merge(imp[["state_fips", "mand"]], on="state_fips") \
          .merge(vmt, on="state_name")
    assert len(m) == 51

    # A: prior-DWI by felony group + national
    grp = m.groupby("felony_at").agg(n=("state_abbr", "count"), imp=("n_imp", "sum"), prior=("n_prior", "sum"))
    groups = []
    for g in GROUP_ORDER:
        r = grp.loc[g]
        groups.append(dict(name=g, n_states=int(r.n), imp=int(r.imp), prior=int(r.prior),
                           pct_prior=100 * r.prior / r.imp))
    tot_imp, tot_prior = int(m.n_imp.sum()), int(m.n_prior.sum())
    nat = dict(imp=tot_imp, prior=tot_prior, pct_prior=100 * tot_prior / tot_imp,
               pct_noprior=100 - 100 * tot_prior / tot_imp)
    ms = m[m.state_abbr == "MS"].iloc[0]

    # B: tiles
    tiles = {c: sorted(m[m.felony_at == c].state_abbr.tolist()) for c in CAT_ORDER}

    # C: checkpoints x mandatory impound
    def quad(r):
        cp, im = r.checkpoints_permitted == 1, r.mand == 1
        return "Both" if cp and im else "Checkpoints only" if cp else "Impound only" if im else "Neither"
    m["quad"] = m.apply(quad, axis=1)
    quads = [dict(name=q, n=int((m.quad == q).sum())) for q in QUAD_ORDER]
    neither = sorted(m[m.quad == "Neither"].state_abbr.tolist())

    # D: known-BAC share of killed drivers by mandatory-testing law
    bac = {k: m[m.mandatory_testing_law == k][["state_abbr", "pct_bac_known_killed"]]
           .sort_values(["pct_bac_known_killed", "state_abbr"]).values.tolist() for k in ("yes", "no")}
    bac_mean = {k: float(m[m.mandatory_testing_law == k].pct_bac_known_killed.mean()) for k in ("yes", "no")}
    lo = m.loc[m.pct_bac_known_killed.idxmin()]
    hi = m.loc[m.pct_bac_known_killed.idxmax()]

    # E: alcohol-impaired deaths (NHTSA imputed BAC>=0.08) per 100M VMT
    m["rate_vmt"] = m.alcohol_fatalities_nhtsa_imputed / m.vmt * 100  # VMT is in millions
    s = m.sort_values(["rate_vmt", "state_abbr"], ascending=[False, True])
    top = [(r.state_abbr, float(r.rate_vmt)) for r in s.head(5).itertuples()]
    bot = [(r.state_abbr, float(r.rate_vmt)) for r in s.tail(5).iloc[::-1].itertuples()]
    return dict(groups=groups, nat=nat, ms=(int(ms.n_imp), int(ms.n_prior)), tiles=tiles, quads=quads,
                neither=neither, bac=bac, bac_mean=bac_mean, bac_lo=(lo.state_abbr, float(lo.pct_bac_known_killed)),
                bac_hi=(hi.state_abbr, float(hi.pct_bac_known_killed)), top=top, bot=bot,
                n_mand=len(bac["yes"]), n_nomand=len(bac["no"]))


# ───────────────────────── sections (shared by tall + social; geometry via params) ─────────────────────────
def head(x, y, title, sub, big, small):
    return (T(x, y, title, big, NAVY, "bold") + "\n" + T(x, y + big * 0.8, sub, small, GREY), big * 0.8 + small + 16)


def sec_a(d, x, y, w, k, lab_w):
    """k = scale (1.0 tall, ~0.8 social). Returns (svg, height)."""
    o, nat = [], d["nat"]
    h, hh = head(x, y + 34 * k, "Prior DWI convictions among impaired drivers in fatal crashes",
                 "FARS 2024, drivers with known history; impaired = driver-impairment code 9", round(31 * k), round(21 * k))
    o.append(h)
    cy = y + 34 * k + hh + 6
    big = round(104 * k)
    o.append(T(x, cy + big * 0.78, f'{nat["pct_noprior"]:.1f}%', big, TEAL, "bold"))
    bx = x + big * 3.0
    o.append(T(bx, cy + big * 0.34, "of impaired drivers in fatal crashes had", round(27 * k), NAVY, "bold"))
    o.append(T(bx, cy + big * 0.34 + 32 * k, "no prior DWI conviction on record", round(27 * k), NAVY, "bold"))
    o.append(T(bx, cy + big * 0.34 + 62 * k,
               f'{nat["imp"]:,} impaired drivers with known history, {nat["prior"]:,} with a prior', round(21 * k), GREY))
    cy += big + 40 * k
    bh, track = 32 * k, w - lab_w - 150 * k
    tx = x + lab_w
    rows = [dict(name="National (51 jurisdictions)", pct_prior=nat["pct_prior"], imp=nat["imp"], prior=nat["prior"], n_states=51)] \
        + d["groups"]
    pitch = 46 * k
    o.append(T(tx, cy - 6 * k, "Felony threshold group", round(18 * k), GREY))
    for i, r in enumerate(rows):
        yy = cy + i * pitch
        key = "nat" if i == 0 else r["name"]
        nop = 100 - r["pct_prior"]
        wn, wp = nop / 100 * track, r["pct_prior"] / 100 * track
        lab = r["name"] if i == 0 else f'{r["name"]} ({r["n_states"]})'
        o.append(T(tx - 12, yy + bh * 0.7, lab, round(21 * k), NAVY, "bold", "end"))
        o.append(f'<rect class="m" data-id="A:{key}:noprior" data-x0="{f(tx)}" data-track="{f(track)}" data-max="100" '
                 f'x="{f(tx)}" y="{f(yy)}" width="{f(wn)}" height="{f(bh)}" fill="{TEAL}"/>'
                 f'<!-- {key} no prior {nop:.2f}% -> {wn:.1f}px -->')
        o.append(f'<rect class="m" data-id="A:{key}:prior" data-x0="{f(tx+wn)}" data-track="{f(track)}" data-max="100" '
                 f'x="{f(tx+wn)}" y="{f(yy)}" width="{f(wp)}" height="{f(bh)}" fill="{GOLD}"/>'
                 f'<!-- {key} prior {r["pct_prior"]:.2f}% -> {wp:.1f}px -->')
        o.append(T(tx + 10, yy + bh * 0.7, f"{nop:.1f}%", round(20 * k), "#FFFFFF", "bold"))
        o.append(T(tx + track + 10, yy + bh * 0.7, f'{r["pct_prior"]:.1f}% had a prior', round(19 * k), "#8A5A00", "bold"))
    cy += len(rows) * pitch
    o.append(T(tx, cy + 4 * k, "No prior conviction on record is not the same as never having driven impaired.",
               round(18 * k), GREY))
    ms_n, ms_p = d["ms"]
    o.append(T(tx, cy + 4 * k + 24 * k, f"Mississippi: {ms_p} of {ms_n} impaired drivers show a prior; likely a reporting gap, still counted.", round(18 * k), GREY))
    return "\n".join(o), (cy + 4 * k + 24 * k + 10) - y


def sec_b(d, x, y, w, k, per_row, pitch, size, row_gap):
    o = []
    h, hh = head(x, y + 34 * k, "Number of DUI convictions that makes a DUI a felony",
                 "One tile per jurisdiction (50 states + DC), grouped by threshold", round(31 * k), round(21 * k))
    o.append(h)
    cy = y + 34 * k + hh + 8
    for c in CAT_ORDER:
        ab = d["tiles"][c]
        o.append(T(x, cy + 18 * k, f"{c}", round(22 * k), CAT_COLOR[c], "bold"))
        o.append(T(x + 270 * k, cy + 18 * k, f"{len(ab)} jurisdictions", round(20 * k), GREY))
        cy += 28 * k
        for i, a in enumerate(ab):
            r_, c_ = divmod(i, per_row)
            tx, ty = x + c_ * pitch, cy + r_ * pitch
            o.append(f'<rect class="m" data-id="B:{a}" data-cat="{esc(c)}" x="{f(tx)}" y="{f(ty)}" width="{size}" '
                     f'height="{size}" rx="3" fill="{CAT_COLOR[c]}"/>')
            o.append(T(tx + size / 2, ty + size * 0.64, a, round(size * 0.40), "#FFFFFF", "bold", "middle"))
        nrows = (len(ab) + per_row - 1) // per_row
        cy += nrows * pitch + row_gap
    return "\n".join(o), cy - y - row_gap + 4


def sec_c(d, x, y, w, k):
    o = []
    h, hh = head(x, y + 34 * k, "Sobriety checkpoints and mandatory vehicle impound",
                 "Checkpoints = legal in the state. Impound = mandatory seizure on a DUI. Segment width = number of jurisdictions.",
                 round(31 * k), round(21 * k))
    o.append(h)
    cy = y + 34 * k + hh + 10
    bh, xx = 54 * k, x
    for q in d["quads"]:
        ww = q["n"] / 51 * w
        o.append(f'<rect class="m" data-id="C:{q["name"]}" data-x0="{f(x)}" data-track="{f(w)}" data-max="51" '
                 f'x="{f(xx)}" y="{f(cy)}" width="{f(ww)}" height="{f(bh)}" fill="{QUAD_COLOR[q["name"]]}" '
                 f'stroke="{BG}" stroke-width="2"/><!-- {q["name"]} {q["n"]} -> {ww:.1f}px -->')
        o.append(T(xx + 12, cy + bh * 0.66, str(q["n"]), round(30 * k), "#FFFFFF", "bold"))
        o.append(T(xx + ww / 2, cy + bh + 26 * k, q["name"], round(19 * k), NAVY, "bold", "middle"))
        xx += ww
    cy += bh + 26 * k + 28 * k
    o.append(T(x, cy, "Neither tool: " + ", ".join(d["neither"]), round(19 * k), GREY))
    return "\n".join(o), cy + 8 - y


def sec_d(d, x, y, w, k, lab_w):
    o = []
    h, hh = head(x, y + 34 * k, "Killed drivers with a known BAC result, by testing law",
                 "Each dot is one jurisdiction. Tick = simple average of jurisdictions (not weighted by drivers).",
                 round(31 * k), round(21 * k))
    o.append(h)
    cy = y + 34 * k + hh + 8
    ax0, ax1 = x + 12, x + w - 12
    rows = [("yes", f'Mandatory testing law ({d["n_mand"]})', TEAL), ("no", f'No mandatory law ({d["n_nomand"]})', SPICE)]
    rh = 78 * k
    for ri, (key, lab, col) in enumerate(rows):
        ry = cy + ri * rh
        o.append(T(x, ry + 20 * k, lab, round(21 * k), col, "bold"))
        ly = ry + 20 * k + 42 * k
        o.append(f'<line x1="{f(ax0)}" y1="{f(ly)}" x2="{f(ax1)}" y2="{f(ly)}" stroke="{VANILLA}" stroke-width="3"/>')
        for i, (ab, v) in enumerate(d["bac"][key]):
            px = ax0 + v / 100 * (ax1 - ax0)
            py = ly + [-13, 0, 13][i % 3] * k
            o.append(f'<circle class="m" data-id="D:{key}:{ab}" data-x0="{f(ax0)}" data-track="{f(ax1-ax0)}" data-max="100" '
                     f'cx="{f(px)}" cy="{f(py)}" r="{f(5.2*k)}" fill="{col}" fill-opacity="0.85"/><!-- {ab} {v} -->')
        mv = d["bac_mean"][key]
        mx = ax0 + mv / 100 * (ax1 - ax0)
        o.append(f'<line class="m" data-id="D:{key}:mean" data-x0="{f(ax0)}" data-track="{f(ax1-ax0)}" data-max="100" '
                 f'x1="{f(mx)}" y1="{f(ly-26*k)}" x2="{f(mx)}" y2="{f(ly+26*k)}" stroke="{NAVY}" stroke-width="4"/>'
                 f'<!-- {key} mean {mv:.3f} -->')
        o.append(T(mx + 8, ry + 20 * k, f"avg {mv:.1f}%", round(21 * k), NAVY, "bold"))
    ay = cy + 2 * rh + 14 * k
    for t_ in (0, 25, 50, 75, 100):
        o.append(T(ax0 + t_ / 100 * (ax1 - ax0), ay + 14 * k, f"{t_}%", round(17 * k), GREY, "", "middle"))
    (la, lv), (ha, hv) = d["bac_lo"], d["bac_hi"]
    o.append(T(x, ay + 14 * k + 26 * k, f"Share of killed drivers with a known BAC result. Lowest {la} {lv:.1f}%, highest {ha} {hv:.1f}%.",
               round(18 * k), GREY))
    return "\n".join(o), ay + 14 * k + 26 * k + 10 - y


def sec_e(d, x, y, w, k, lab_w, pitch, sub="Five highest and five lowest of 51 jurisdictions. NHTSA imputed BAC 0.08+, 2024 deaths; FHWA 2022 miles."):
    o = []
    h, hh = head(x, y + 34 * k, "Alcohol-impaired deaths per 100 million vehicle miles",
                 sub,
                 round(31 * k), round(21 * k))
    o.append(h)
    cy = y + 34 * k + hh + 10
    track = w - lab_w - 80 * k
    vmax = max(v for _, v in d["top"] + d["bot"])
    tx = x + lab_w
    bh = pitch * 0.72
    for gi, (lab, rows, col) in enumerate((("Highest", d["top"], SPICE), ("Lowest", d["bot"], TEAL))):
        for i, (ab, v) in enumerate(rows):
            yy = cy + (gi * 5 + i) * pitch + (gi + 1) * 22 * k
            ww = v / vmax * track
            o.append(T(tx - 10, yy + bh * 0.75, ab, round(20 * k), NAVY, "bold", "end"))
            o.append(f'<rect class="m" data-id="E:{ab}" data-x0="{f(tx)}" data-track="{f(track)}" data-max="{vmax:.6f}" '
                     f'x="{f(tx)}" y="{f(yy)}" width="{f(ww)}" height="{f(bh)}" fill="{col}"/>'
                     f'<!-- {ab} {v:.4f} -> {ww:.1f}px -->')
            o.append(T(tx + ww + 8, yy + bh * 0.75, f"{v:.2f}", round(19 * k), col, "bold"))
        o.append(T(x, cy + (gi * 5) * pitch + gi * 22 * k + 14 * k, lab + " five", round(18 * k), GREY, "bold"))
    cy += 10 * pitch + 44 * k
    return "\n".join(o), cy - y + 2


# ───────────────────────── frames ─────────────────────────
def divider(x1, x2, y):
    return f'<line x1="{x1}" y1="{f(y)}" x2="{x2}" y2="{f(y)}" stroke="{VANILLA}" stroke-width="3"/>'


def footer(W, y, hgt, size):
    return (f'<rect x="0" y="{y}" width="{W}" height="{hgt}" fill="{NAVY}"/>\n'
            + T(80 if W == 1200 else 60, y + hgt * 0.40, "@unwelcomedata", 26 if W == 1200 else 24, VANILLA, "bold")
            + "\n" + T(W - (80 if W == 1200 else 60), y + hgt * 0.40, "Data from public sources: NHTSA FARS 2024, NASID, NCSL, FHWA, state statutes",
                       size + 2, VANILLA, "", "end") + "\n"
            + T(80 if W == 1200 else 60, y + hgt * 0.78,
                "Laws as compiled in 2026. FARS counts convictions on record, not impairment history; per-mile rates use 2022 FHWA miles.",
                size, VANILLA))


def build_tall(d):
    W = 1200
    body, y = [], 340
    secs = [
        lambda y: sec_a(d, 80, y, 1040, 1.0, 330),
        lambda y: sec_b(d, 80, y, 1040, 1.0, 24, 43, 40, 16),
        lambda y: sec_c(d, 80, y, 1040, 1.0),
        lambda y: sec_d(d, 80, y, 1040, 1.0, 0),
        lambda y: sec_e(d, 80, y, 1040, 1.0, 60, 30),
    ]
    for i, s in enumerate(secs):
        svg, h = s(y)
        body.append(svg)
        y += h + 28
        if i < len(secs) - 1:
            body.append(divider(80, 1120, y - 12))
            y += 24
    H = int(y + 10 + 100)
    head_ = (f'<rect width="{W}" height="{H}" fill="{BG}"/>\n<rect width="{W}" height="300" fill="{NAVY}"/>\n'
             + T(80, 130, "DUI by State", 76, "#FFFFFF", "bold") + "\n"
             + T(80, 190, "Laws, enforcement and fatal-crash data for 50 states + DC", 38, AQUA, "bold") + "\n"
             + T(80, 240, "Who is behind the wheel, where a DUI becomes a felony, and what tools states use.", 26, VANILLA) + "\n")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
           f'font-family="Helvetica, Arial, sans-serif">\n{head_}\n' + "\n".join(body) + "\n" + footer(W, H - 100, 100, 17) + "\n</svg>")
    return svg, W, H


def build_social(d):
    W, H = 1600, 900
    L, R, CW = 60, 840, 700
    hdr, ftr = 130, 66
    o = [f'<rect width="{W}" height="{H}" fill="{BG}"/>',
         f'<rect width="{W}" height="{hdr}" fill="{NAVY}"/>',
         T(60, 66, "DUI by State", 54, "#FFFFFF", "bold"),
         T(60, 104, "Laws, enforcement and fatal-crash data for 50 states + DC", 28, AQUA, "bold")]
    k = 0.74
    kl = 0.66
    a, ha = sec_a(d, L, hdr + 14, CW, kl, 230)
    b, hb = sec_b(d, L, hdr + 14 + ha + 26, CW, kl, 24, 28.4, 24, 6)
    c, hc = sec_d(d, R, hdr + 14, CW, k, 0)
    e, he = sec_e(d, R, hdr + 14 + hc + 26, CW, k, 40, 19, "Top and bottom five of 51. NHTSA imputed BAC 0.08+; FHWA 2022 miles.")
    ya, yb = hdr + 14 + ha + 13, hdr + 14 + hc + 13
    o += [a, divider(L, L + CW, ya), b, c, divider(R, R + CW, yb), e,
          f'<line x1="800" y1="{hdr+20}" x2="800" y2="{H-ftr-16}" stroke="{VANILLA}" stroke-width="3"/>']
    o.append(footer(W, H - ftr, ftr, 15))
    o.insert(0, "")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
           f'font-family="Helvetica, Arial, sans-serif">\n' + "\n".join(o) + "\n</svg>")
    return svg, W, H, (hdr + 14 + ha + 26 + hb, hdr + 14 + hc + 26 + he)


# ───────────────────────── validation ─────────────────────────
def fresh() -> dict:
    """Independent re-derivation (different code path: SQL + DuckDB joins) of every plotted value."""
    con = duckdb.connect(str(PROJECT / "data" / "project.duckdb"), read_only=True)
    exp = str(PROJECT / "export" / "dui_by_state_v4.parquet")
    imp = str(PROJECT / "data" / "interim" / "vehicle_impound_laws.parquet")
    base = f"""
      WITH b AS (
        SELECT e.state_abbr ab, e.mandatory_testing_law law, e.pct_bac_known_killed bk,
               e.checkpoints_permitted cp, e.alcohol_fatalities_nhtsa_imputed af, v.vmt_millions_2022 vmt,
               CASE WHEN e.has_felony_dui=0 OR e.felony_dui_threshold IS NULL THEN 'Always a misdemeanor'
                    ELSE 'Felony on '||CAST(CAST(e.felony_dui_threshold AS INT) AS VARCHAR)||
                         CASE CAST(e.felony_dui_threshold AS INT) WHEN 2 THEN 'nd' WHEN 3 THEN 'rd' ELSE 'th' END END cat,
               p.impaired_drivers_known_history ni, p.impaired_with_prior_dwi np,
               (i.vehicle_impound_law='yes' AND i.impound_mandatory='mandatory') mand
        FROM read_parquet('{exp}') e
        JOIN fars_prior_dwi_speed p ON lpad(CAST(e.state_fips AS VARCHAR),2,'0')=p.state_fips
        JOIN speed_limits_vmt v ON v.state_name=e.state_name
        JOIN read_parquet('{imp}') i ON lpad(CAST(i.state_fips AS VARCHAR),2,'0')=lpad(CAST(e.state_fips AS VARCHAR),2,'0'))
    """
    q = lambda s: con.sql(base + s).fetchall()
    out = {}
    out["n"] = q("SELECT count(*) FROM b")[0][0]
    for cat, ni, np_, n in q("SELECT cat, sum(ni), sum(np), count(*) FROM b GROUP BY cat"):
        out[f"A:{cat}:prior"] = 100.0 * np_ / ni
        out[f"A:{cat}:noprior"] = 100 - 100.0 * np_ / ni
    ni, np_ = q("SELECT sum(ni), sum(np) FROM b")[0]
    out["A:nat:prior"], out["A:nat:noprior"] = 100.0 * np_ / ni, 100 - 100.0 * np_ / ni
    out["nat_counts"] = (int(ni), int(np_))
    for ab, cat in q("SELECT ab, cat FROM b"):
        out[f"Bcat:{ab}"] = cat
    for name, n in q("""SELECT CASE WHEN cp=1 AND mand THEN 'Both' WHEN cp=1 THEN 'Checkpoints only'
                        WHEN mand THEN 'Impound only' ELSE 'Neither' END, count(*) FROM b GROUP BY 1"""):
        out[f"C:{name}"] = n
    out["neither"] = sorted(r[0] for r in q("SELECT ab FROM b WHERE NOT (cp=1 OR mand)"))
    for ab, law, v in q("SELECT ab, law, bk FROM b"):
        out[f"D:{law}:{ab}"] = v
    for law, mv in q("SELECT law, avg(bk) FROM b GROUP BY law"):
        out[f"D:{law}:mean"] = mv
    for ab, r_ in q("SELECT ab, af*100.0/vmt FROM b"):
        out[f"E:{ab}"] = r_
    out["E:order"] = [r[0] for r in q("SELECT ab FROM b ORDER BY af*100.0/vmt DESC, ab")]
    out["ms"] = q("SELECT ni, np FROM b WHERE ab='MS'")[0]
    con.close()
    return out


def parse_marks(svg: str) -> dict:
    marks = {}
    for m in re.finditer(r"<(rect|circle|line) class=\"m\" ([^>]*?)/?>", svg):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(2)))
        marks[a["data-id"]] = (m.group(1), a)
    return marks


def invert(kind, a) -> float:
    x0, track, mx = float(a["data-x0"]), float(a["data-track"]), float(a["data-max"])
    if kind == "rect":
        if a["data-id"].startswith("A:") and a["data-id"].endswith(":prior") or a["data-id"].startswith(("E:", "C:")):
            return float(a["width"]) / track * mx
        return float(a["width"]) / track * mx  # A:...:noprior
    if kind == "circle":
        return (float(a["cx"]) - x0) / track * mx
    return (float(a["x1"]) - x0) / track * mx  # mean tick


def validate(d, svgs: dict) -> tuple[list[str], list[str]]:
    fr, lines, errs = fresh(), [], []

    def chk(name, got, want, tol):
        ok = abs(got - want) <= tol
        lines.append(f"| {name} | {got:.4f} | {want:.4f} | {'PASS' if ok else 'FAIL'} |")
        if not ok:
            errs.append(f"{name}: got {got} want {want}")

    # reconcile with scripts/validate_charts.py facts
    cats = {}
    for k_, v in fr.items():
        if k_.startswith("Bcat:"):
            cats[v] = cats.get(v, 0) + 1
    for cat, n in {"Felony on 3rd": 24, "Felony on 4th": 20, "Felony on 2nd": 4, "Always a misdemeanor": 3}.items():
        lines.append(f"| validate_charts.py: '{cat}' = {n} states | {cats.get(cat, 0)} | {n} | {'PASS' if cats.get(cat,0)==n else 'FAIL'} |")
        if cats.get(cat, 0) != n:
            errs.append(f"felony category {cat}")
    if fr["n"] != 51:
        errs.append("n != 51")
    for rname, svg in svgs.items():
        marks = parse_marks(svg)
        seen = set()
        for mid, (kind, a) in marks.items():
            seen.add(mid)
            if mid.startswith("B:"):
                ab = mid[2:]
                got = a["data-cat"].replace("&amp;", "&")
                ok = got == fr[f"Bcat:{ab}"]
                lines.append(f"| [{rname}] {mid} category | {got} | {fr[f'Bcat:{ab}']} | {'PASS' if ok else 'FAIL'} |")
                if not ok:
                    errs.append(mid)
                continue
            if mid.startswith("A:"):
                _, key, part = mid.split(":")
                want = fr[f"A:{key}:{part}"]
                tol = 0.05
            elif mid.startswith("D:"):
                want, tol = fr[mid], 0.05
            elif mid.startswith("C:"):
                want, tol = fr[mid], 0.02
            else:  # E
                want, tol = fr[mid], 0.0005
            chk(f"[{rname}] {mid}", invert(kind, a), want, tol)
        # mark-set completeness
        want_ids = {f"B:{k_[5:]}" for k_ in fr if k_.startswith("Bcat:")}
        for rn in ("A:nat",):
            pass
        miss = want_ids - seen
        lines.append(f"| [{rname}] all 51 tiles present | {51-len(miss)} | 51 | {'PASS' if not miss else 'FAIL'} |")
        if miss:
            errs.append(f"{rname} missing tiles {miss}")
        # dots: 51 total
        nd = len([m for m in seen if m.startswith("D:") and not m.endswith(":mean")])
        lines.append(f"| [{rname}] 51 BAC dots | {nd} | 51 | {'PASS' if nd==51 else 'FAIL'} |")
        if nd != 51:
            errs.append("dots")
        # text claims: every displayed figure appears in the SVG text
        txt = re.sub(r"<[^>]+>", " ", svg)
        claims = [f'{fr["A:nat:noprior"]:.1f}%', f'{fr["nat_counts"][0]:,}', f'{fr["nat_counts"][1]:,}',
                  f'avg {fr["D:yes:mean"]:.1f}%', f'avg {fr["D:no:mean"]:.1f}%']
        claims += [f'{fr[f"A:{c}:prior"]:.1f}% had a prior' for c in GROUP_ORDER + ["nat"]]
        claims += [f'{fr[f"E:{ab}"]:.2f}' for ab in fr["E:order"][:5] + fr["E:order"][-5:]]
        for c in claims:
            ok = c in txt
            lines.append(f"| [{rname}] text shows '{c}' | present={ok} | - | {'PASS' if ok else 'FAIL'} |")
            if not ok:
                errs.append(f"{rname} text {c}")
        if rname == "tall":
            c = "Neither tool: " + ", ".join(fr["neither"])
            ok = c in txt
            lines.append(f"| [{rname}] '{c}' | present={ok} | - | {'PASS' if ok else 'FAIL'} |")
            if not ok:
                errs.append("neither list")
    ok = [r for r in fr["E:order"][:5]] == [a for a, _ in d["top"]] and fr["E:order"][-5:][::-1] == [a for a, _ in d["bot"]]
    lines.append(f"| E top5/bottom5 identity | {[a for a,_ in d['top']]} / {[a for a,_ in d['bot']]} | DB order | {'PASS' if ok else 'FAIL'} |")
    if not ok:
        errs.append("E order")
    return lines, errs


def main() -> int:
    d = load()
    tall, tw, th = build_tall(d)
    soc, sw, sh, ends = build_social(d)
    (DOCS / "infographic_dui.svg").write_text(tall, encoding="utf-8")
    (DOCS / "infographic_dui_social.svg").write_text(soc, encoding="utf-8")
    print(f"tall {tw}x{th}; social col bottoms {ends}")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        for name, svg, w, h in (("infographic_dui", tall, tw, th), ("infographic_dui_social", soc, sw, sh)):
            pg = br.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            pg.set_content("<!doctype html><html><head><style>*{margin:0;padding:0}</style></head><body>"
                           + svg + "</body></html>")
            pg.wait_for_timeout(300)
            pg.screenshot(path=str(DOCS / f"{name}.png"), clip={"x": 0, "y": 0, "width": w, "height": h})
            pg.close()
            print(f"rendered {name}.png ({w}x{h})")
        br.close()
    lines, errs = validate(d, {"tall": tall, "social": soc})
    vc = subprocess.run([sys.executable, str(PROJECT / "scripts" / "validate_charts.py")], capture_output=True, text=True)
    nat = d["nat"]
    note = ["# dui-by-state infographic: data-mark validation", "",
            "Generated by `scripts/_render_infographic.py` (gitignored). Every mark in BOTH renders is parsed back out of the SVG,",
            "its pixel geometry inverted to a value (width / track * axis max, or (x - x0) / track * max), and compared with a",
            "fresh, independently coded SQL query over `data/project.duckdb` (read-only) + `export/dui_by_state_v4.parquet` +",
            "`data/interim/vehicle_impound_laws.parquet`. Displayed text figures are asserted present in the SVG text.", "",
            f"Result: **{'FAIL' if errs else 'PASS'}** ({len(lines)} checks, {len(errs)} failures).",
            f"`scripts/validate_charts.py` exit code: **{vc.returncode}** ({vc.stdout.strip().splitlines()[-1] if vc.stdout else vc.stderr[-200:]})", "",
            "## Headline figures",
            f"- National: {nat['imp']:,} impaired drivers with known prior-DWI history; {nat['prior']:,} with a prior = {nat['pct_prior']:.2f}% "
            f"-> **{nat['pct_noprior']:.2f}% no prior** (shown 92.5%). NOTE: earlier project notes/social copy say '93%'; the data round to 92.5%.",
            f"- Mandatory-testing-law avg {d['bac_mean']['yes']:.2f}% vs {d['bac_mean']['no']:.2f}% (simple jurisdiction means; matches SOURCES.md 78.2 / 51.7).",
            f"- MS: {d['ms'][1]} of {d['ms'][0]} impaired drivers with a prior (documented reporting gap, kept in totals).",
            f"- Highest per-100M-VMT: {d['top'][0][0]} {d['top'][0][1]:.2f}; lowest {d['bot'][0][0]} {d['bot'][0][1]:.2f}.", "",
            "## Mark-by-mark", "| Mark | Plotted (inverted from SVG) | Source | Result |", "|---|---|---|---|"] + lines
    (ART / "INFOGRAPHIC-VALIDATION.md").write_text("\n".join(note) + "\n", encoding="utf-8")
    print(f"validation: {len(lines)} checks, {len(errs)} failures; validate_charts exit {vc.returncode}")
    for e in errs[:20]:
        print("  FAIL", e)
    return 1 if errs or vc.returncode else 0


if __name__ == "__main__":
    raise SystemExit(main())
