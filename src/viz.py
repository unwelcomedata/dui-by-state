"""DUI-by-state visualization module.

Produces publication-ready PNG images sized for social media platforms.
All charts generated with matplotlib and exported via Pillow for exact
pixel-level control.

Supported presets:
  - instagram_square   : 1080x1080
  - instagram_portrait : 1080x1350
  - twitter_landscape  : 1600x900
  - twitter_square     : 1080x1080

Key functions:
  - choropleth_map()    : Flexible US state map, numeric heat or categorical
  - scatter_chart()     : X-Y scatter with region coloring
  - ranked_bar_chart()  : Top/bottom N horizontal bars
  - comparison_chart()  : Group comparison (e.g. IID vs non-IID)
  - line_chart()        : Trend lines over time
  - save_chart()        : Export to PNG with watermark
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd
from PIL import Image

# Import shared brand library from workspace root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from viz import BRAND, PALETTE, REGION_COLORS, PRESETS, STYLE  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SHAPEFILE = Path(__file__).resolve().parents[1] / "data" / "raw" / "geo" / "cb_2022_us_state_20m.shp"
_TERRITORIES = {"60", "66", "69", "72", "78"}  # exclude from maps

# Alaska/Hawaii inset transforms (shift + scale for CONUS layout)
_AK_SCALE = 0.35
_AK_TRANSLATE = (0, -1_400_000)
_HI_TRANSLATE = (5_200_000, -1_500_000)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fig_for_preset(preset: str) -> tuple[plt.Figure, plt.Axes]:
    """Create a (fig, ax) pair sized for the given platform preset."""
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset '{preset}'. Choose from: {list(PRESETS)}")
    w_px, h_px, dpi = PRESETS[preset]
    fig_w = w_px / dpi
    fig_h = h_px / dpi
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
    return fig, ax


def _load_states_geo() -> gpd.GeoDataFrame:
    """Load US states shapefile, exclude territories, reproject to Albers."""
    gdf = gpd.read_file(_SHAPEFILE)
    gdf = gdf[~gdf["STATEFP"].isin(_TERRITORIES)].copy()
    # Project to Albers Equal Area (standard for US thematic maps)
    gdf = gdf.to_crs("EPSG:5070")
    return gdf


def _shift_alaska_hawaii(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Move Alaska and Hawaii to inset positions below CONUS."""
    from shapely.affinity import scale, translate

    gdf = gdf.copy()

    # Alaska: scale down and shift
    ak_mask = gdf["STUSPS"] == "AK"
    if ak_mask.any():
        ak_geom = gdf.loc[ak_mask, "geometry"].values[0]
        centroid = ak_geom.centroid
        ak_scaled = scale(ak_geom, xfact=_AK_SCALE, yfact=_AK_SCALE, origin=centroid)
        ak_shifted = translate(ak_scaled, xoff=_AK_TRANSLATE[0], yoff=_AK_TRANSLATE[1])
        gdf.loc[ak_mask, "geometry"] = ak_shifted

    # Hawaii: shift only
    hi_mask = gdf["STUSPS"] == "HI"
    if hi_mask.any():
        hi_geom = gdf.loc[hi_mask, "geometry"].values[0]
        hi_shifted = translate(hi_geom, xoff=_HI_TRANSLATE[0], yoff=_HI_TRANSLATE[1])
        gdf.loc[hi_mask, "geometry"] = hi_shifted

    return gdf


def _add_title_block(
    fig: plt.Figure,
    ax: plt.Axes,
    title: str,
    subtitle: str,
    source: str = "",
    use_tight_layout: bool = True,
) -> None:
    """Add title, subtitle, and source line with consistent styling."""
    if title:
        ax.set_title(
            title,
            fontsize=BRAND["title_size"],
            fontweight=BRAND["title_weight"],
            pad=12,
            loc="left",
        )
    if subtitle:
        fig.text(
            0.125, 0.93, subtitle,
            fontsize=BRAND["subtitle_size"],
            color=BRAND["subtitle_color"],
            ha="left", va="top",
            transform=fig.transFigure,
        )
    if source:
        fig.text(
            0.125, 0.02, f"Source: {source}",
            fontsize=7, color=PALETTE["mid"],
            ha="left", va="bottom",
            transform=fig.transFigure,
        )
    if use_tight_layout:
        fig.tight_layout(rect=[0, 0.03, 1, 0.91] if subtitle else [0, 0.03, 1, 0.97])


def _add_watermark(fig: plt.Figure, text: str) -> None:
    """Draw a faint watermark in the lower-right corner."""
    fig.text(
        0.98, 0.02, text,
        fontsize=BRAND["watermark_size"],
        color=BRAND["watermark_color"],
        alpha=BRAND["watermark_alpha"],
        ha="right", va="bottom",
        transform=fig.transFigure,
    )


# ---------------------------------------------------------------------------
# Choropleth map
# ---------------------------------------------------------------------------

def choropleth_map(
    df: pd.DataFrame,
    column: str,
    title: str = "",
    subtitle: str = "",
    source: str = "",
    fips_col: str = "state_fips",
    mode: str = "heat",
    cmap: str | list[str] | None = None,
    category_colors: dict[str, str] | None = None,
    legend_title: str = "",
    vmin: float | None = None,
    vmax: float | None = None,
    preset: str = "twitter_landscape",
    edgecolor: str = "#FFFFFF",
    linewidth: float = 0.5,
    missing_color: str = "#E5E7EB",
    annotate: bool = False,
    annotation_col: str = "state_abbr",
) -> plt.Figure:
    """Flexible US state choropleth map.

    Supports two modes:
      - "heat": Continuous numeric column → sequential/diverging colormap
      - "category": Discrete column → distinct category colors

    Args:
        df:              DataFrame with state data (must include fips_col).
        column:          Column to map (numeric for heat, string for category).
        title:           Bold headline.
        subtitle:        Smaller subtitle below title.
        source:          Source attribution line at bottom.
        fips_col:        Column in df with 2-digit FIPS codes.
        mode:            "heat" for numeric, "category" for discrete.
        cmap:            Matplotlib colormap name, or list of hex colors for
                         custom LinearSegmentedColormap. Defaults to brand ramp.
        category_colors: Dict mapping category values → hex colors (for mode="category").
        legend_title:    Title for the colorbar or legend.
        vmin/vmax:       Override range for numeric colorbar.
        preset:          Platform size preset.
        edgecolor:       State border color.
        linewidth:       State border width.
        missing_color:   Fill for states with no data.
        annotate:        If True, label each state with its abbreviation.
        annotation_col:  Column to use for annotation text.

    Returns:
        matplotlib Figure ready for save_chart().
    """
    # Load and prepare geodata
    geo = _load_states_geo()
    geo = _shift_alaska_hawaii(geo)

    # Merge data
    df_merge = df[[fips_col, column]].copy()
    if annotate and annotation_col in df.columns:
        df_merge[annotation_col] = df[annotation_col].values
    df_merge[fips_col] = df_merge[fips_col].astype(str).str.zfill(2)
    geo = geo.merge(df_merge, left_on="STATEFP", right_on=fips_col, how="left")

    # Create figure
    fig, ax = _fig_for_preset(preset)
    ax.set_axis_off()

    if mode == "heat":
        # Numeric heat map
        if cmap is None:
            cmap_obj = mcolors.LinearSegmentedColormap.from_list(
                "brand_heat", PALETTE["heat_ramp"], N=256
            )
        elif isinstance(cmap, list):
            cmap_obj = mcolors.LinearSegmentedColormap.from_list("custom", cmap, N=256)
        else:
            cmap_obj = plt.get_cmap(cmap)

        col_min = vmin if vmin is not None else geo[column].min()
        col_max = vmax if vmax is not None else geo[column].max()

        # Plot missing states
        geo_missing = geo[geo[column].isna()]
        if not geo_missing.empty:
            geo_missing.plot(ax=ax, color=missing_color, edgecolor=edgecolor, linewidth=linewidth)

        # Plot data states
        geo_data = geo[geo[column].notna()]
        geo_data.plot(
            ax=ax,
            column=column,
            cmap=cmap_obj,
            vmin=col_min,
            vmax=col_max,
            edgecolor=edgecolor,
            linewidth=linewidth,
            legend=False,
        )

        # Colorbar
        sm = plt.cm.ScalarMappable(
            cmap=cmap_obj,
            norm=mcolors.Normalize(vmin=col_min, vmax=col_max),
        )
        sm._A = []
        cbar = fig.colorbar(sm, ax=ax, fraction=0.02, pad=0.02, aspect=30)
        cbar.ax.tick_params(labelsize=8)
        if legend_title:
            cbar.set_label(legend_title, fontsize=9)

    elif mode == "category":
        # Discrete category map
        categories = sorted(geo[column].dropna().unique())

        if category_colors is None:
            cat_palette = [
                PALETTE["cat_1"], PALETTE["cat_2"], PALETTE["cat_3"],
                PALETTE["cat_4"], PALETTE["cat_5"], PALETTE["cat_6"],
            ]
            category_colors = {cat: cat_palette[i % len(cat_palette)] for i, cat in enumerate(categories)}

        # Assign colors
        geo["_fill"] = geo[column].map(category_colors).fillna(missing_color)

        # Plot missing
        geo_missing = geo[geo[column].isna()]
        if not geo_missing.empty:
            geo_missing.plot(ax=ax, color=missing_color, edgecolor=edgecolor, linewidth=linewidth)

        # Plot each category
        for cat in categories:
            subset = geo[geo[column] == cat]
            if not subset.empty:
                subset.plot(ax=ax, color=category_colors[cat], edgecolor=edgecolor, linewidth=linewidth)

        # Legend
        patches = [
            mpatches.Patch(color=category_colors[cat], label=cat)
            for cat in categories
        ]
        leg = ax.legend(
            handles=patches,
            loc="lower left",
            fontsize=8,
            framealpha=0.9,
            title=legend_title or column,
            title_fontsize=9,
        )

    else:
        raise ValueError(f"mode must be 'heat' or 'category', got '{mode}'")

    # Annotations
    if annotate:
        for _, row in geo.iterrows():
            if pd.notna(row.get(annotation_col)):
                centroid = row.geometry.centroid
                ax.annotate(
                    row[annotation_col],
                    xy=(centroid.x, centroid.y),
                    ha="center", va="center",
                    fontsize=5, color=PALETTE["dark"],
                )

    # Skip tight_layout for maps — colorbar + geo axes trigger matplotlib
    # recursion bug on Python 3.14. Use manual subplots_adjust instead.
    _add_title_block(fig, ax, title, subtitle, source, use_tight_layout=False)
    fig.subplots_adjust(left=0.02, right=0.88, top=0.88, bottom=0.05)
    return fig


# ---------------------------------------------------------------------------
# Scatter chart
# ---------------------------------------------------------------------------

def scatter_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    color_by: str = "region",
    color_map: dict[str, str] | None = None,
    size: float = 50,
    title: str = "",
    subtitle: str = "",
    source: str = "",
    xlabel: str = "",
    ylabel: str = "",
    annotate: bool = False,
    annotation_col: str = "state_abbr",
    preset: str = "twitter_landscape",
) -> plt.Figure:
    """Scatter plot with optional categorical coloring and state labels.

    Args:
        df:             DataFrame with x, y, and color_by columns.
        x:              Numeric column for x-axis.
        y:              Numeric column for y-axis.
        color_by:       Column for point coloring (categorical).
        color_map:      Dict mapping color_by values → hex colors.
        size:           Marker size.
        title:          Bold headline.
        subtitle:       Smaller text below title.
        source:         Source attribution line.
        xlabel/ylabel:  Axis labels.
        annotate:       Label each point with state abbreviation.
        annotation_col: Column for annotation text.
        preset:         Platform size preset.

    Returns:
        matplotlib Figure.
    """
    fig, ax = _fig_for_preset(preset)

    if color_map is None:
        color_map = REGION_COLORS

    with plt.rc_context(STYLE):
        groups = df.groupby(color_by, observed=True)
        for name, group in groups:
            color = color_map.get(name, PALETTE["mid"])
            ax.scatter(
                group[x], group[y],
                c=color, s=size, alpha=0.8,
                label=name, edgecolors="white", linewidths=0.5,
            )

        if annotate and annotation_col in df.columns:
            for _, row in df.iterrows():
                ax.annotate(
                    row[annotation_col],
                    (row[x], row[y]),
                    fontsize=6, ha="left", va="bottom",
                    xytext=(3, 3), textcoords="offset points",
                    color=PALETTE["dark"],
                )

        ax.set_xlabel(xlabel or x, fontsize=10)
        ax.set_ylabel(ylabel or y, fontsize=10)
        ax.legend(fontsize=9, framealpha=0.9, loc="best")
        _add_title_block(fig, ax, title, subtitle, source)

    return fig


# ---------------------------------------------------------------------------
# Ranked bar chart
# ---------------------------------------------------------------------------

def ranked_bar_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str = "",
    subtitle: str = "",
    source: str = "",
    top_n: int = 10,
    bottom_n: int = 0,
    color: str | None = None,
    highlight_color: str | None = None,
    highlight_values: list[str] | None = None,
    value_fmt: str = "{:.2f}",
    preset: str = "instagram_portrait",
) -> plt.Figure:
    """Top-N (and optionally bottom-N) horizontal bar chart.

    If bottom_n > 0, shows both top and bottom in a single chart
    with a visual divider.

    Args:
        df:               DataFrame with x (labels) and y (values).
        x:                Category column (state names/abbrs).
        y:                Numeric column.
        title:            Bold headline.
        subtitle:         Smaller subtitle.
        source:           Source line.
        top_n:            Number of highest-value states to show.
        bottom_n:         Number of lowest-value states to show (0 = skip).
        color:            Bar fill color.
        highlight_color:  Color for highlighted bars.
        highlight_values: x values to highlight.
        value_fmt:        Format string for bar labels.
        preset:           Platform size preset.

    Returns:
        matplotlib Figure.
    """
    color = color or PALETTE["accent"]
    highlight_color = highlight_color or PALETTE["primary"]

    data = df[[x, y]].dropna().copy()

    if bottom_n > 0:
        top = data.nlargest(top_n, y)
        bottom = data.nsmallest(bottom_n, y)
        data = pd.concat([top, bottom]).drop_duplicates().sort_values(y, ascending=True)
    else:
        data = data.nlargest(top_n, y).sort_values(y, ascending=True)

    fig, ax = _fig_for_preset(preset)

    with plt.rc_context(STYLE):
        # Determine bar colors
        bar_colors = []
        for v in data[x]:
            if bottom_n > 0 and v in bottom.nsmallest(bottom_n, y)[x].values:
                bar_colors.append(PALETTE["success"])
            elif highlight_values and str(v) in highlight_values:
                bar_colors.append(highlight_color)
            else:
                bar_colors.append(color)

        bars = ax.barh(data[x].astype(str), data[y], color=bar_colors)
        ax.bar_label(bars, fmt=value_fmt, padding=4, fontsize=9)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.1f}"))

        # Add divider line if showing both top and bottom
        if bottom_n > 0:
            divider_y = bottom_n - 0.5
            ax.axhline(y=divider_y, color=PALETTE["mid"], linewidth=0.8, linestyle="--", alpha=0.5)

        _add_title_block(fig, ax, title, subtitle, source)

    return fig


# ---------------------------------------------------------------------------
# Comparison chart (group means)
# ---------------------------------------------------------------------------

def comparison_chart(
    df: pd.DataFrame,
    group_col: str,
    value_col: str,
    title: str = "",
    subtitle: str = "",
    source: str = "",
    colors: dict[str, str] | None = None,
    show_n: bool = True,
    value_fmt: str = "{:.2f}",
    preset: str = "twitter_landscape",
) -> plt.Figure:
    """Compare mean values between groups (e.g. IID vs non-IID states).

    Shows bars with mean value, confidence indicators, and group size.

    Args:
        df:          DataFrame with group_col and value_col.
        group_col:   Categorical column defining groups.
        value_col:   Numeric column to compare.
        title:       Bold headline.
        subtitle:    Smaller subtitle.
        source:      Source line.
        colors:      Dict mapping group values → hex colors.
        show_n:      Show group counts on bars.
        value_fmt:   Format string for bar labels.
        preset:      Platform size preset.

    Returns:
        matplotlib Figure.
    """
    fig, ax = _fig_for_preset(preset)

    with plt.rc_context(STYLE):
        # Compute group stats
        stats = (
            df.groupby(group_col, observed=True)[value_col]
            .agg(["mean", "std", "count"])
            .reset_index()
            .sort_values("mean", ascending=False)
        )

        # Colors
        default_colors = [PALETTE["primary"], PALETTE["accent"], PALETTE["success"], PALETTE["warning"]]
        if colors is None:
            colors = {row[group_col]: default_colors[i % len(default_colors)]
                      for i, (_, row) in enumerate(stats.iterrows())}

        bar_colors = [colors.get(g, PALETTE["mid"]) for g in stats[group_col]]

        bars = ax.bar(
            stats[group_col].astype(str),
            stats["mean"],
            color=bar_colors,
            width=0.6,
            edgecolor="white",
            linewidth=1,
        )

        # Error bars (standard error)
        se = stats["std"] / np.sqrt(stats["count"])
        ax.errorbar(
            range(len(stats)),
            stats["mean"],
            yerr=se,
            fmt="none",
            color=PALETTE["dark"],
            capsize=5,
            linewidth=1.5,
        )

        # Labels
        for bar, (_, row) in zip(bars, stats.iterrows()):
            label = value_fmt.format(row["mean"])
            if show_n:
                label += f"\n(n={int(row['count'])})"
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + se.max() * 0.3,
                label,
                ha="center", va="bottom",
                fontsize=10, fontweight="bold",
            )

        ax.set_ylabel(value_col.replace("_", " ").title(), fontsize=10)
        ax.set_xlabel("")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.1f}"))
        _add_title_block(fig, ax, title, subtitle, source)

    return fig


# ---------------------------------------------------------------------------
# Line chart (trends)
# ---------------------------------------------------------------------------

def line_chart(
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
    markers: bool = True,
) -> plt.Figure:
    """Line chart supporting one or multiple y series.

    Args:
        y: Single column name, or list of column names for multi-line.
    """
    y_cols = [y] if isinstance(y, str) else y
    default_colors = [PALETTE["primary"], PALETTE["accent"], PALETTE["success"],
                      PALETTE["warning"], PALETTE["cat_5"]]
    colors = colors or default_colors[:len(y_cols)]

    fig, ax = _fig_for_preset(preset)

    with plt.rc_context(STYLE):
        for col, clr in zip(y_cols, colors):
            ax.plot(
                df[x], df[col],
                color=clr, linewidth=2.5,
                marker="o" if markers else None,
                markersize=5, label=col.replace("_", " ").title(),
            )
        if len(y_cols) > 1:
            ax.legend(framealpha=0.8, fontsize=9)
        ax.set_xlabel(xlabel or x, fontsize=10)
        ax.set_ylabel(ylabel or (y_cols[0] if len(y_cols) == 1 else ""), fontsize=10)
        _add_title_block(fig, ax, title, subtitle, source)

    return fig


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save_chart(
    fig: plt.Figure,
    cfg: dict[str, Any],
    filename: str,
    preset: str = "twitter_landscape",
    add_watermark: str = "@unwelcomedata",
    close: bool = True,
) -> Path:
    """Save a matplotlib figure to outputs/ as a PNG.

    Args:
        fig:           Figure returned by any chart builder above.
        cfg:           Loaded config dict (needs paths.outputs).
        filename:      Output filename without extension.
        preset:        Used to verify final pixel dimensions.
        add_watermark: Branding text in bottom-right corner.
        close:         If True, close the figure after saving.
                       Set to False in notebooks to keep inline display.

    Returns:
        Path to the saved PNG file.
    """
    out_dir = Path(cfg["paths"]["outputs"])
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{filename}.png"

    if add_watermark:
        _add_watermark(fig, add_watermark)

    w_px, h_px, dpi = PRESETS.get(preset, (1600, 900, 150))
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor())

    if close:
        plt.close(fig)

    # Verify and resize to exact pixel dimensions
    img = Image.open(out_path)
    if img.size != (w_px, h_px):
        img = img.resize((w_px, h_px), Image.LANCZOS)
        img.save(out_path, format="PNG", optimize=True)

    print(f"Saved chart -> {out_path}  ({w_px}x{h_px} px, preset={preset})")
    return out_path
