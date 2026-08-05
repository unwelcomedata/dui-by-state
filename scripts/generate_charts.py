"""Generate all 04-viz charts for dui-by-state project."""

import os
os.environ['MPLBACKEND'] = 'Agg'

import sys
from pathlib import Path

# Project root
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

import matplotlib
matplotlib.use('Agg')

import pandas as pd
import yaml

from src.viz import (
    choropleth_map, scatter_chart, ranked_bar_chart,
    comparison_chart, line_chart, save_chart,
)

def main():
    with open(PROJECT / 'config.yaml') as f:
        cfg = yaml.safe_load(f)

    df = pd.read_parquet(PROJECT / 'export' / 'dui_by_state_v1.parquet')
    print(f'Master table: {df.shape}', flush=True)

    # ---- MAPS ----

    print('\n[1] Map: alcohol fatality rate per 100M VMT', flush=True)
    fig = choropleth_map(
        df, column='alcohol_fatality_rate_per_100m_vmt',
        title='Alcohol-Impaired Fatality Rate by State',
        subtitle='Deaths per 100 million vehicle miles traveled (2024)',
        source='NHTSA FARS 2024, FHWA VMT 2022',
        mode='heat', legend_title='Deaths per 100M VMT',
        preset='twitter_landscape', annotate=True,
    )
    save_chart(fig, cfg, 'map_alcohol_fatality_rate_vmt', preset='twitter_landscape', add_watermark='@unwelcomedata')

    print('[2] Map: felony status', flush=True)
    df['felony_label'] = df['first_offense_felony'].map({1.0: 'Can be felony', 0.0: 'Always misdemeanor'})
    df.loc[df['felony_label'].isna(), 'felony_label'] = 'Unknown'
    fig = choropleth_map(
        df, column='felony_label',
        title='First-Offense DUI: Felony Possible?',
        subtitle='States where first DUI can be charged as felony (e.g. with child in car or injury)',
        source='NCSL DUI/DWI criminal status laws',
        mode='category',
        category_colors={'Can be felony': '#DC2626', 'Always misdemeanor': '#2563EB', 'Unknown': '#E5E7EB'},
        legend_title='First-offense status', preset='twitter_landscape',
    )
    save_chart(fig, cfg, 'map_felony_status', preset='twitter_landscape', add_watermark='@unwelcomedata')

    print('[3] Map: IID status', flush=True)
    df['iid_label'] = df['all_offender_iid'].map({1: 'All offenders', 0: 'Repeat/high-BAC only'})
    fig = choropleth_map(
        df, column='iid_label',
        title='Ignition Interlock: All First Offenders?',
        subtitle='States requiring IID for all DUI offenders vs repeat/high-BAC only',
        source='IIHS, GHSA, NHTSA enforcement compilations',
        mode='category',
        category_colors={'All offenders': '#16A34A', 'Repeat/high-BAC only': '#D97706'},
        legend_title='IID requirement', preset='twitter_landscape',
    )
    save_chart(fig, cfg, 'map_iid_status', preset='twitter_landscape', add_watermark='@unwelcomedata')

    print('[4] Map: max speed limit', flush=True)
    fig = choropleth_map(
        df, column='max_speed_limit_mph',
        title='Maximum Posted Speed Limit by State',
        subtitle='Rural interstate max speed (mph)',
        source='IIHS, August 2026',
        mode='heat', cmap=['#DBEAFE', '#60A5FA', '#2563EB', '#7C3AED', '#4C1D95'],
        legend_title='Max speed (mph)', preset='twitter_landscape', annotate=True,
    )
    save_chart(fig, cfg, 'map_max_speed_limit', preset='twitter_landscape', add_watermark='@unwelcomedata')

    print('[5] Map: prior DWI %', flush=True)
    fig = choropleth_map(
        df, column='pct_impaired_with_prior_dwi',
        title='Repeat Offenders in Fatal Crashes',
        subtitle='% of impaired drivers in fatal crashes with a prior DWI conviction',
        source='NHTSA FARS 2024',
        mode='heat', cmap=['#FEF3C7', '#FBBF24', '#D97706', '#DC2626', '#7F1D1D'],
        legend_title='% with prior DWI', preset='twitter_landscape', annotate=True,
    )
    save_chart(fig, cfg, 'map_prior_dwi_pct', preset='twitter_landscape', add_watermark='@unwelcomedata')

    # ---- SCATTER ----

    print('\n[6] Scatter: consumption vs fatality rate', flush=True)
    fig = scatter_chart(
        df,
        x='ethanol_per_capita_gallons_2022',
        y='alcohol_fatality_rate_per_100m_vmt',
        color_by='region',
        title='Alcohol Consumption vs Impaired-Driving Deaths',
        subtitle='Each dot is a state. Per-VMT fatality rate controls for driving exposure.',
        source='NIAAA consumption 2022, NHTSA FARS 2024, FHWA VMT 2022',
        xlabel='Per capita ethanol (gallons, 2022)',
        ylabel='Alcohol fatalities per 100M VMT',
        annotate=True,
        preset='twitter_landscape',
    )
    save_chart(fig, cfg, 'scatter_consumption_vs_fatality', preset='twitter_landscape', add_watermark='@unwelcomedata')

    # ---- RANKED BARS ----

    print('[7] Ranked bars: top/bottom 10 per VMT', flush=True)
    fig = ranked_bar_chart(
        df,
        x='state_name',
        y='alcohol_fatality_rate_per_100m_vmt',
        title='Worst & Best States for Impaired-Driving Deaths',
        subtitle='Alcohol fatalities per 100M vehicle miles traveled (2024)',
        source='NHTSA FARS 2024, FHWA VMT 2022',
        top_n=10,
        bottom_n=10,
        value_fmt='{:.2f}',
        preset='instagram_portrait',
    )
    save_chart(fig, cfg, 'ranked_top_bottom_10_vmt', preset='instagram_portrait', add_watermark='@unwelcomedata')

    # ---- IID COMPARISON ----

    print('[8] Comparison: IID vs non-IID', flush=True)
    df['iid_group'] = df['all_offender_iid'].map({1: 'IID for all offenders', 0: 'No universal IID'})
    fig = comparison_chart(
        df,
        group_col='iid_group',
        value_col='alcohol_fatality_rate_per_100m_vmt',
        title='Does Mandatory IID Reduce Impaired-Driving Deaths?',
        subtitle='Mean alcohol fatality rate per 100M VMT by IID policy (error bars = standard error)',
        source='NHTSA FARS 2024, FHWA VMT 2022, IIHS/GHSA enforcement data',
        colors={'IID for all offenders': '#16A34A', 'No universal IID': '#DC2626'},
        value_fmt='{:.2f}',
        preset='twitter_landscape',
    )
    save_chart(fig, cfg, 'comparison_iid_vs_no_iid', preset='twitter_landscape', add_watermark='@unwelcomedata')

    # ---- TREND ----

    print('[9] Trend: national 2015-2020', flush=True)
    trends = pd.read_parquet(PROJECT / 'export' / 'dui_trends_2015_2020.parquet')
    national = trends.groupby('year', as_index=False).agg(
        impaired_fatalities=('impaired_fatalities_any', 'sum'),
        total_fatalities=('total_fatalities', 'sum'),
    )
    fig = line_chart(
        national,
        x='year',
        y='impaired_fatalities',
        title='National Alcohol-Impaired Fatalities (2015-2020)',
        subtitle='Methodology-consistent FARS coding window (drimpair code 9)',
        source='NHTSA FARS 2015-2020',
        xlabel='Year',
        ylabel='Alcohol-impaired fatalities',
        preset='twitter_landscape',
    )
    save_chart(fig, cfg, 'trend_national_2015_2020', preset='twitter_landscape', add_watermark='@unwelcomedata')

    print('\n=== ALL 9 CHARTS GENERATED SUCCESSFULLY ===', flush=True)


if __name__ == '__main__':
    main()
