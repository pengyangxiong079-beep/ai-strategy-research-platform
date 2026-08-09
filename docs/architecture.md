# Architecture

The repository has four bounded layers:

1. `research_platform/` plans datasets, builds industry-aware queries, normalizes Sources and Observations, and calculates deterministic sufficiency.
2. `pipeline_v2/` orchestrates stage contracts, retries, Quality aggregation, lineage, report rendering, and revisions.
3. `app.py`, `app_pages/`, and `ui/` provide the Streamlit Research Workspace control plane.
4. `dashboard-web/` renders template-driven React/ECharts pages from `06_dashboard_data.json`.

Agents return structured payloads at explicit boundaries. Stage gates reject malformed Review ranges, missing Observation coverage, unstructured scenarios, and hash drift. Original run folders are immutable; test artifacts and revisions are separate.
