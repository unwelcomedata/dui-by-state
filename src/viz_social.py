"""Social-ready chart export using Altair + vl-convert.

Produces publication-quality PNG images for Instagram/Twitter posting.
Uses the @unwelcomedata brand palette (Coolors) and Inter typography.

All charts are rendered to PNG via vl-convert — no browser needed.

Key functions:
    social_scatter()      — X-Y scatter with region coloring
    social_ranked_bars()  — Top/bottom N horizontal bars
    social_comparison()   — Group mean comparison (e.g. IID vs non-IID)
    social_trend()        — Line chart over time
    social_choropleth()   — US state map (heat or category)
    save_social()         — Export Altair chart to PNG with watermark

Platform presets:
    instagram_portrait : 1080×1350
    twitter_landscape  : 1600×900
    instagram_square   : 1080×1080
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import vl_convert as vlc
from PIL import Image, ImageDraw, ImageFont

# Import shared brand library from workspace root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from viz import (  # noqa: E402
    BRAND, COOLORS, COOLORS_SCALE, PALETTE, PRESETS,
    REGION_COLORS, SOCIAL_THEME,
)

# ---------------------------------------------------------------------------
# Register @unwelcomedata Altair theme
# ---------------------------------------------------------------------------

def _unwelcome_theme() -> dict:
    """Altair theme config using brand identity."""
    return {
        "config": {
            "background": SOCIAL_THEME["background"],
            "font": SOCIAL_THEME["font"],
            "title": SOCIAL_THEME["title"],
            "axis": SOCIAL_THEME["axis"],
            "legend": SOCIAL_THEME["legend"],
            "view": SOCIAL_THEME["view"],
            "range": SOCIAL_THEME["range"],
            "mark": SOCIAL_THEME["mark"],
            "bar": {"cornerRadiusEnd": 3},
            "point": {"size": 60, "filled": True},
            "line": {"strokeWidth": 3},
        }
    }


alt.themes.register("unwelcomedata", _unwelcome_theme)
alt.themes.enable("unwelcomedata")

# ---------------------------------------------------------------------------
# Shapefile path for choropleth
# ---------------------------------------------------------------------------

_SHAPEFILE = Path(__file__).resolve().parents[1] / "data" / "raw" / "geo" / "cb_2022_us_state_20m.shp"
_TERRITORIES = {"60", "66", "69", "72", "78"}


# ---------------------------------------------------------------------------
# Scatter chart
# ---------------------------------------------------------------------------

def social_scatter(
    df: pd.DataFrame,
    x: str,
    y: str,
    color_by: str = "region",
    color_map: dict[str, str] | None = None,
    title: str = "",
    subtitle: str = "",
    source: str = "",
    xlabel: str = "",
    ylabel: str = "",
    label_col: str | None = "state_abbr",
    preset: str = "twitter_landscape",
) -> alt.Chart:
    """Scatter plot with categorical coloring and optional state labels.

    Args:
        df:         DataFrame with x, y, color_by columns.
        x:          Numeric column for x-axis.
        y:          Numeric column for y-axis.
        color_by:   Column for point coloring.
        color_map:  Dict mapping values → hex colors.
        title:      Chart title.
        subtitle:   Subtitle text.
        source:     Source attribution.
        xlabel:     X-axis label.
        ylabel:     Y-axis label.
        label_col:  Column for point labels (None to skip).
        preset:     Platform size preset.

    Returns:
        Altair Chart object.
    """
    w, h = _preset_size(preset)
    color_map = color_map or REGION_COLORS

    domain = list(color_map.keys())
    range_ = list(color_map.values())

    base = alt.Chart(df).encode(
        x=alt.X(x, title=xlabel or _pretty(x), scale=alt.Scale(zero=False)),
        y=alt.Y(y, title=ylabel or _pretty(y), scale=alt.Scale(zero=False)),
        color=alt.Color(
            color_by,
            scale=alt.Scale(domain=domain, range=range_),
            legend=alt.Legend(title=_pretty(color_by)),
        ),
    )

    points = base.mark_circle(size=70, opacity=0.85, strokeWidth=1, stroke="white")

    layers = [points]

    if label_col and label_col in df.columns:
        labels = base.mark_text(
            align="left", dx=7, dy=-2, fontSize=9,
            color=PALETTE["dark"],
        ).encode(text=label_col)
        layers.append(labels)

    chart = alt.layer(*layers).properties(
        width=w - 120,
        height=h - 140,
        title=alt.Title(title, subtitle=[subtitle] if subtitle else []),
    )

    if source:
        chart = _add_source(chart, source, w)

    return chart


# ---------------------------------------------------------------------------
# Ranked bar chart
# ---------------------------------------------------------------------------

def social_ranked_bars(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str = "",
    subtitle: str = "",
    source: str = "",
    top_n: int = 10,
    bottom_n: int = 0,
    bar_color: str | None = None,
    worst_color: str | None = None,
    best_color: str | None = None,
    value_fmt: str = ".2f",
    preset: str = "instagram_portrait",
) -> alt.Chart:
    """Horizontal bar chart showing top (and optionally bottom) N states.

    Args:
        df:           DataFrame with x (labels) and y (values).
        x:            Category column (state names).
        y:            Numeric column.
        title:        Chart title.
        subtitle:     Subtitle.
        source:       Source line.
        top_n:        Show top N highest values.
        bottom_n:     Show bottom N lowest values (0 = skip).
        bar_color:    Default bar color.
        worst_color:  Color for top (worst) bars.
        best_color:   Color for bottom (best) bars.
        value_fmt:    Number format spec for bar labels.
        preset:       Platform size preset.

    Returns:
        Altair Chart object.
    """
    w, h = _preset_size(preset)
    worst_color = worst_color or COOLORS["coral"]
    best_color = best_color or COOLORS["teal"]
    bar_color = bar_color or COOLORS["charcoal"]

    data = df[[x, y]].dropna().copy()

    if bottom_n > 0:
        top = data.nlargest(top_n, y).assign(_group="worst")
        bottom = data.nsmallest(bottom_n, y).assign(_group="best")
        data = pd.concat([top, bottom]).drop_duplicates(subset=[x])
    else:
        data = data.nlargest(top_n, y).assign(_group="worst")

    # Assign bar colors
    data["_color"] = data["_group"].map({"worst": worst_color, "best": best_color})

    bars = alt.Chart(data).mark_bar(cornerRadiusEnd=4).encode(
        x=alt.X(y, title=_pretty(y)),
        y=alt.Y(x, sort=alt.SortField(field=y, order="descending"), title=""),
        color=alt.Color("_color:N", scale=None),
    )

    labels = alt.Chart(data).mark_text(
        align="left", dx=5, fontSize=11, fontWeight="bold",
        color=PALETTE["dark"],
    ).encode(
        x=alt.X(y),
        y=alt.Y(x, sort=alt.SortField(field=y, order="descending")),
        text=alt.Text(y, format=value_fmt),
    )

    chart = (bars + labels).properties(
        width=w - 200,
        height=h - 120,
        title=alt.Title(title, subtitle=[subtitle] if subtitle else []),
    )

    if source:
        chart = _add_source(chart, source, w)

    return chart


# ---------------------------------------------------------------------------
# Comparison chart (group means)
# ---------------------------------------------------------------------------

def social_comparison(
    df: pd.DataFrame,
    group_col: str,
    value_col: str,
    title: str = "",
    subtitle: str = "",
    source: str = "",
    colors: dict[str, str] | None = None,
    value_fmt: str = ".2f",
    preset: str = "twitter_landscape",
) -> alt.Chart:
    """Compare mean values between groups with labeled bars.

    Args:
        df:          DataFrame with group_col and value_col.
        group_col:   Categorical column defining groups.
        value_col:   Numeric column to compare.
        title:       Chart title.
        subtitle:    Subtitle.
        source:      Source line.
        colors:      Dict mapping group values → hex colors.
        value_fmt:   Number format for labels.
        preset:      Platform size preset.

    Returns:
        Altair Chart object.
    """
    w, h = _preset_size(preset)

    stats = (
        df.groupby(group_col, observed=True)[value_col]
        .agg(["mean", "std", "count"])
        .reset_index()
    )
    stats["se"] = stats["std"] / (stats["count"] ** 0.5)
    stats["ci_lo"] = stats["mean"] - stats["se"]
    stats["ci_hi"] = stats["mean"] + stats["se"]
    stats["label"] = stats.apply(
        lambda r: f"{r['mean']:{value_fmt}} (n={int(r['count'])})", axis=1
    )

    if colors:
        domain = list(colors.keys())
        range_ = list(colors.values())
    else:
        domain = stats[group_col].tolist()
        range_ = COOLORS_SCALE[:len(domain)]

    bars = alt.Chart(stats).mark_bar(
        cornerRadiusEnd=5, width=60,
    ).encode(
        x=alt.X(group_col, title="", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("mean:Q", title=_pretty(value_col), scale=alt.Scale(zero=True)),
        color=alt.Color(
            group_col, scale=alt.Scale(domain=domain, range=range_), legend=None
        ),
    )

    error = alt.Chart(stats).mark_errorbar(ticks=True).encode(
        x=alt.X(group_col),
        y=alt.Y("ci_lo:Q", title=""),
        y2=alt.Y2("ci_hi:Q"),
    )

    labels = alt.Chart(stats).mark_text(
        dy=-15, fontSize=14, fontWeight="bold", color=PALETTE["dark"],
    ).encode(
        x=alt.X(group_col),
        y=alt.Y("mean:Q"),
        text="label:N",
    )

    chart = (bars + error + labels).properties(
        width=w - 200,
        height=h - 140,
        title=alt.Title(title, subtitle=[subtitle] if subtitle else []),
    )

    if source:
        chart = _add_source(chart, source, w)

    return chart


# ---------------------------------------------------------------------------
# Trend line chart
# ---------------------------------------------------------------------------

def social_trend(
    df: pd.DataFrame,
    x: str,
    y: str | list[str],
    title: str = "",
    subtitle: str = "",
    source: str = "",
    xlabel: str = "",
    ylabel: str = "",
    colors: list[str] | None = None,
    preset: str = "twitter_landscape",
) -> alt.Chart:
    """Line chart for time series trends.

    Args:
        df:      DataFrame with x and y columns.
        x:       Time/numeric x-axis column.
        y:       Column name or list of column names for multi-line.
        title:   Chart title.
        subtitle: Subtitle.
        source:  Source line.
        xlabel:  X-axis label.
        ylabel:  Y-axis label.
        colors:  List of hex colors for lines.
        preset:  Platform size preset.

    Returns:
        Altair Chart object.
    """
    w, h = _preset_size(preset)
    y_cols = [y] if isinstance(y, str) else y
    colors = colors or COOLORS_SCALE[:len(y_cols)]

    if len(y_cols) == 1:
        chart = alt.Chart(df).mark_line(
            point=True, strokeWidth=3, color=colors[0],
        ).encode(
            x=alt.X(x, title=xlabel or _pretty(x)),
            y=alt.Y(y_cols[0], title=ylabel or _pretty(y_cols[0])),
        )
    else:
        # Melt for multi-line
        melted = df.melt(id_vars=[x], value_vars=y_cols, var_name="series", value_name="value")
        chart = alt.Chart(melted).mark_line(
            point=True, strokeWidth=3,
        ).encode(
            x=alt.X(x, title=xlabel or _pretty(x)),
            y=alt.Y("value:Q", title=ylabel or ""),
            color=alt.Color(
                "series:N",
                scale=alt.Scale(domain=y_cols, range=colors),
                legend=alt.Legend(title=""),
            ),
        )

    chart = chart.properties(
        width=w - 120,
        height=h - 140,
        title=alt.Title(title, subtitle=[subtitle] if subtitle else []),
    )

    if source:
        chart = _add_source(chart, source, w)

    return chart


# ---------------------------------------------------------------------------
# Choropleth map
# ---------------------------------------------------------------------------

def social_choropleth(
    df: pd.DataFrame,
    column: str,
    title: str = "",
    subtitle: str = "",
    source: str = "",
    fips_col: str = "state_fips",
    mode: str = "heat",
    color_scale: list[str] | None = None,
    category_colors: dict[str, str] | None = None,
    legend_title: str = "",
    preset: str = "twitter_landscape",
) -> alt.Chart:
    """US state choropleth using Altair + TopoJSON inline data.

    Args:
        df:              DataFrame with state data.
        column:          Column to map (numeric for heat, string for category).
        title:           Chart title.
        subtitle:        Subtitle.
        source:          Source line.
        fips_col:        Column with 2-digit FIPS codes.
        mode:            "heat" for numeric, "category" for discrete.
        color_scale:     List of hex colors for sequential scale.
        category_colors: Dict mapping category → hex color.
        legend_title:    Legend title.
        preset:          Platform size preset.

    Returns:
        Altair Chart object.
    """
    import geopandas as gpd

    w, h = _preset_size(preset)

    # Load geometry
    geo = gpd.read_file(_SHAPEFILE)
    geo = geo[~geo["STATEFP"].isin(_TERRITORIES)].copy()

    # Merge data
    df_merge = df[[fips_col, column]].copy()
    df_merge[fips_col] = df_merge[fips_col].astype(str).str.zfill(2)
    geo = geo.merge(df_merge, left_on="STATEFP", right_on=fips_col, how="left")

    # Convert to GeoJSON for Altair
    geo_json = geo.__geo_interface__

    if mode == "heat":
        color_scale = color_scale or PALETTE["heat_ramp"]
        color_enc = alt.Color(
            f"{column}:Q",
            scale=alt.Scale(range=color_scale),
            legend=alt.Legend(title=legend_title or _pretty(column)),
        )
    elif mode == "category":
        if category_colors:
            domain = list(category_colors.keys())
            range_ = list(category_colors.values())
        else:
            vals = sorted(df[column].dropna().unique())
            domain = vals
            range_ = COOLORS_SCALE[:len(vals)]
        color_enc = alt.Color(
            f"{column}:N",
            scale=alt.Scale(domain=domain, range=range_),
            legend=alt.Legend(title=legend_title or _pretty(column)),
        )
    else:
        raise ValueError(f"mode must be 'heat' or 'category', got '{mode}'")

    chart = alt.Chart(
        alt.Data(values=geo_json["features"])
    ).mark_geoshape(
        stroke="white", strokeWidth=0.5,
    ).encode(
        color=color_enc,
        tooltip=[alt.Tooltip("properties.NAME:N", title="State"),
                 alt.Tooltip(f"properties.{column}:Q" if mode == "heat" else f"properties.{column}:N",
                             title=legend_title or column)],
    ).transform_lookup(
        lookup="id",
        from_=alt.LookupData(data=alt.Data(values=geo_json["features"]), key="id"),
    ).project(
        type="albersUsa",
    ).properties(
        width=w - 80,
        height=h - 120,
        title=alt.Title(title, subtitle=[subtitle] if subtitle else []),
    )

    if source:
        chart = _add_source(chart, source, w)

    return chart


# ---------------------------------------------------------------------------
# Bubble choropleth (color + proportional symbols)
# ---------------------------------------------------------------------------

def social_bubble_choropleth(
    df: pd.DataFrame,
    color_col: str,
    size_col: str,
    title: str = "",
    subtitle: str = "",
    source: str = "",
    fips_col: str = "state_fips",
    color_scale: list[str] | None = None,
    color_legend: str = "",
    size_legend: str = "",
    preset: str = "twitter_landscape",
) -> alt.Chart:
    """Choropleth with state fill color + proportional bubble overlay.

    Variable 1 → state fill color (sequential)
    Variable 2 → circle size at state centroid

    Args:
        df:            DataFrame with state data.
        color_col:     Numeric column for state fill color.
        size_col:      Numeric column for bubble size.
        title:         Chart title.
        subtitle:      Subtitle.
        source:        Source line.
        fips_col:      Column with 2-digit FIPS codes.
        color_scale:   List of hex colors for fill ramp.
        color_legend:  Legend title for color.
        size_legend:   Legend title for bubble size.
        preset:        Platform size preset.

    Returns:
        Altair LayerChart object.
    """
    import geopandas as gpd

    w, h = _preset_size(preset)
    color_scale = color_scale or PALETTE["heat_ramp"]

    # Load geometry
    geo = gpd.read_file(_SHAPEFILE)
    geo = geo[~geo["STATEFP"].isin(_TERRITORIES)].copy()

    # Merge data
    cols_needed = [fips_col, color_col, size_col]
    if "lat" in df.columns and "lng" in df.columns:
        cols_needed += ["lat", "lng"]
    df_merge = df[list(set(cols_needed))].copy()
    df_merge[fips_col] = df_merge[fips_col].astype(str).str.zfill(2)
    geo = geo.merge(df_merge, left_on="STATEFP", right_on=fips_col, how="left")

    # Compute centroids for bubbles (WGS84 is fine for US state-level)
    geo_projected = geo.to_crs("EPSG:4326")
    with pd.option_context("mode.chained_assignment", None):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            geo_projected["_centroid_lng"] = geo_projected.geometry.centroid.x
            geo_projected["_centroid_lat"] = geo_projected.geometry.centroid.y

    geo_json = geo.__geo_interface__

    # Base map — filled by color_col
    base_map = alt.Chart(
        alt.Data(values=geo_json["features"])
    ).mark_geoshape(
        stroke="white", strokeWidth=0.5,
    ).encode(
        color=alt.Color(
            f"properties.{color_col}:Q",
            scale=alt.Scale(range=color_scale),
            legend=alt.Legend(title=color_legend or _pretty(color_col)),
        ),
        tooltip=[
            alt.Tooltip("properties.NAME:N", title="State"),
            alt.Tooltip(f"properties.{color_col}:Q", title=color_legend or color_col, format=".2f"),
            alt.Tooltip(f"properties.{size_col}:Q", title=size_legend or size_col, format=".1f"),
        ],
    ).project(type="albersUsa")

    # Bubble overlay — sized by size_col
    bubble_df = geo_projected[["NAME", "_centroid_lng", "_centroid_lat", color_col, size_col]].dropna().copy()

    bubbles = alt.Chart(bubble_df).mark_circle(
        opacity=0.6, stroke=COOLORS["charcoal"], strokeWidth=0.8,
    ).encode(
        longitude="_centroid_lng:Q",
        latitude="_centroid_lat:Q",
        size=alt.Size(
            f"{size_col}:Q",
            scale=alt.Scale(range=[30, 500]),
            legend=alt.Legend(title=size_legend or _pretty(size_col)),
        ),
        color=alt.value(COOLORS["coral"]),
        tooltip=[
            alt.Tooltip("NAME:N", title="State"),
            alt.Tooltip(f"{size_col}:Q", title=size_legend or size_col, format=".1f"),
        ],
    ).project(type="albersUsa")

    chart = (base_map + bubbles).properties(
        width=w - 80,
        height=h - 120,
        title=alt.Title(title, subtitle=[subtitle] if subtitle else []),
    )

    if source:
        chart = _add_source(chart, source, w)

    return chart


# ---------------------------------------------------------------------------
# Bivariate choropleth (2D color matrix)
# ---------------------------------------------------------------------------

def social_bivariate_choropleth(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str = "",
    subtitle: str = "",
    source: str = "",
    fips_col: str = "state_fips",
    n_bins: int = 3,
    x_label: str = "",
    y_label: str = "",
    preset: str = "twitter_landscape",
) -> alt.Chart:
    """Bivariate choropleth — two variables encoded in a 2D color grid.

    Bins each variable into n_bins quantile groups, assigns each state a
    color from a 3×3 (or n×n) matrix. States in the top-right corner are
    high on both variables.

    Color scheme: teal (low-x, low-y) → gold (high-x, low-y)
                  charcoal (low-x, high-y) → coral (high-x, high-y)

    Args:
        df:        DataFrame with state data.
        x_col:     Numeric column for x-axis of the color grid.
        y_col:     Numeric column for y-axis of the color grid.
        title:     Chart title.
        subtitle:  Subtitle.
        source:    Source line.
        fips_col:  Column with 2-digit FIPS codes.
        n_bins:    Number of quantile bins per axis (default 3 → 9 colors).
        x_label:   Label for x variable in legend.
        y_label:   Label for y variable in legend.
        preset:    Platform size preset.

    Returns:
        Altair Chart object.
    """
    import geopandas as gpd
    import numpy as np

    w, h = _preset_size(preset)

    # 3×3 bivariate color matrix (row = y_col low→high, col = x_col low→high)
    # Bottom-left = low/low, top-right = high/high
    _BIVARIATE_COLORS_3x3 = [
        # y_low
        ["#E8E8E8", "#B8D6BE", "#2A9D8F"],  # x_low → x_high
        # y_mid
        ["#DFC27D", "#B5A068", "#6D8A6D"],
        # y_high
        ["#E76F51", "#C45A3C", "#264653"],   # x_low → x_high
    ]

    # Bin the data
    data = df[[fips_col, x_col, y_col]].dropna().copy()
    data[fips_col] = data[fips_col].astype(str).str.zfill(2)

    # Quantile bins (0-indexed)
    data["_x_bin"] = pd.qcut(data[x_col], n_bins, labels=False, duplicates="drop")
    data["_y_bin"] = pd.qcut(data[y_col], n_bins, labels=False, duplicates="drop")

    # Assign bivariate color
    def _get_color(row):
        xi = int(min(row["_x_bin"], n_bins - 1))
        yi = int(min(row["_y_bin"], n_bins - 1))
        return _BIVARIATE_COLORS_3x3[yi][xi]

    data["_biv_color"] = data.apply(_get_color, axis=1)

    # Load geometry
    geo = gpd.read_file(_SHAPEFILE)
    geo = geo[~geo["STATEFP"].isin(_TERRITORIES)].copy()
    geo = geo.merge(data, left_on="STATEFP", right_on=fips_col, how="left")

    # Fill missing states gray
    geo["_biv_color"] = geo["_biv_color"].fillna("#E5E7EB")

    geo_json = geo.__geo_interface__

    # Main map
    map_chart = alt.Chart(
        alt.Data(values=geo_json["features"])
    ).mark_geoshape(
        stroke="white", strokeWidth=0.5,
    ).encode(
        color=alt.Color(
            "properties._biv_color:N",
            scale=None,
        ),
        tooltip=[
            alt.Tooltip("properties.NAME:N", title="State"),
            alt.Tooltip(f"properties.{x_col}:Q", title=x_label or x_col, format=".2f"),
            alt.Tooltip(f"properties.{y_col}:Q", title=y_label or y_col, format=".1f"),
        ],
    ).project(type="albersUsa").properties(
        width=w - 160,
        height=h - 140,
    )

    # Build legend as a small layered chart
    legend_data = []
    for yi in range(n_bins):
        for xi in range(n_bins):
            legend_data.append({
                "x": xi, "y": yi,
                "color": _BIVARIATE_COLORS_3x3[yi][xi],
            })
    legend_df = pd.DataFrame(legend_data)

    legend_chart = alt.Chart(legend_df).mark_rect(
        strokeWidth=0.5, stroke="white",
    ).encode(
        x=alt.X("x:O", title=x_label or _pretty(x_col), axis=alt.Axis(labels=False, ticks=False)),
        y=alt.Y("y:O", title=y_label or _pretty(y_col), axis=alt.Axis(labels=False, ticks=False),
                 sort="descending"),
        color=alt.Color("color:N", scale=None),
    ).properties(width=60, height=60, title="Legend")

    # Combine map + legend side by side
    chart = alt.hconcat(
        map_chart, legend_chart
    ).resolve_scale(color="independent").properties(
        title=alt.Title(title, subtitle=[subtitle] if subtitle else []),
    )

    if source:
        # Add source as a text mark below
        source_chart = alt.Chart(
            pd.DataFrame([{"text": f"Source: {source}"}])
        ).mark_text(
            align="left", fontSize=9, color=PALETTE["mid"],
        ).encode(text="text:N").properties(width=w - 120, height=15)
        chart = alt.vconcat(chart, source_chart).configure_concat(spacing=5)

    return chart


# ---------------------------------------------------------------------------
# Save to PNG
# ---------------------------------------------------------------------------

def save_social(
    chart: alt.Chart,
    cfg: dict[str, Any],
    filename: str,
    preset: str = "twitter_landscape",
    add_watermark: str = "@unwelcomedata",
    scale: float = 2.0,
) -> Path:
    """Render an Altair chart to PNG and save to outputs/.

    Args:
        chart:         Altair Chart object.
        cfg:           Project config dict (needs paths.outputs).
        filename:      Output filename without extension.
        preset:        Platform preset for final dimensions.
        add_watermark: Watermark text (bottom-right corner).
        scale:         Render scale factor for sharpness.

    Returns:
        Path to saved PNG.
    """
    out_dir = Path(cfg["paths"]["outputs"])
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{filename}.png"

    w_px, h_px, _ = PRESETS[preset]

    # Render to PNG bytes via vl-convert
    png_bytes = vlc.vegalite_to_png(
        chart.to_dict(),
        scale=scale,
    )

    # Write initial render
    out_path.write_bytes(png_bytes)

    # Resize to exact platform dimensions + add watermark
    img = Image.open(out_path)
    img = img.resize((w_px, h_px), Image.LANCZOS)

    if add_watermark:
        img = _draw_watermark(img, add_watermark)

    img.save(out_path, format="PNG", optimize=True)
    print(f"Saved social chart -> {out_path}  ({w_px}x{h_px} px, preset={preset})")
    return out_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _preset_size(preset: str) -> tuple[int, int]:
    """Get (width, height) in pixels for a preset."""
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset '{preset}'. Choose from: {list(PRESETS)}")
    w, h, _ = PRESETS[preset]
    return w, h


def _pretty(col: str) -> str:
    """Convert column_name to Pretty Title."""
    return col.replace("_", " ").title()


def _add_source(chart: alt.Chart, source: str, width: int) -> alt.Chart:
    """Add a source attribution line below the chart."""
    source_text = alt.Chart(
        pd.DataFrame([{"text": f"Source: {source}"}])
    ).mark_text(
        align="left", fontSize=9, color=PALETTE["mid"], dy=10,
    ).encode(
        text="text:N",
    ).properties(width=width - 120, height=20)

    return alt.vconcat(chart, source_text).configure_concat(spacing=5)


def _draw_watermark(img: Image.Image, text: str) -> Image.Image:
    """Draw watermark text on bottom-right of image."""
    draw = ImageDraw.Draw(img)

    # Try to use a system font, fall back to default
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
    except (OSError, IOError):
        font = ImageFont.load_default()

    # Get text bounding box
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # Position: bottom-right with padding
    x = img.width - text_w - 20
    y = img.height - text_h - 15

    # Draw with transparency effect (gray color)
    draw.text((x, y), text, fill=(156, 163, 175, 180), font=font)

    return img
