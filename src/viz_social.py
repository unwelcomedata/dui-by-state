"""Social chart export — Pillow pipeline.

This module is now a thin compatibility shim. All social chart rendering
uses the shared workspace-level Pillow pipeline:

    shared/chart_factory.py  — entry point, data loading, routing
    shared/chart_templates.py — all Pillow drawing logic

Usage in notebooks:
    from chart_factory import render_chart
    render_chart({...})

The old Altair/vl-convert functions have been removed.
"""
