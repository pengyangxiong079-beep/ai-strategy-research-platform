# Repository agent guide

## Structure

- `pipeline_v2/`: canonical orchestration, gates, quality and revision logic.
- `research_platform/`: data requirements, acquisition, normalization and sufficiency.
- `app.py`, `app_pages/`, `ui/`: Streamlit Research Workspace V2.
- `dashboard-web/`: React, TypeScript, Vite and ECharts dashboard.
- `tests/`: deterministic unit, schema and Fake Agent end-to-end tests.
- `outputs/`: local immutable run audit records; do not edit or publish directly.
- `examples/`: explicitly sanitized public fixtures only.

## Commands

- Streamlit: `python -m streamlit run app.py`
- Python tests: `python -m pytest -q`
- Audit: `python -m tools.audit_latest_run --run latest --revision latest --offline --report`
- Dashboard tests: `cd dashboard-web; npm.cmd test`
- Dashboard build: `cd dashboard-web; npm.cmd run build`

## Long-term rules

- Canonical JSON is the source of truth; Markdown and HTML are derived views.
- Treat original `outputs/` and revisions as immutable audit evidence. Regenerate derived artifacts only in a new revision or temporary fixture.
- Discover runs from parsed manifests, never folder names or filesystem timestamps alone.
- Obtain user approval before any live Agent rerun. Default to offline Fake Agents and deterministic checks.
- Never invent evidence or require a paid API/OpenAI API key for tests or CI.
- Every production fix requires a regression test. Quality PASS means contract checks passed, not that every real-world fact is absolutely true.
- Before public release, scan for secrets, personal paths, large files and unsanitized outputs. Do not add, commit, push or publish unless explicitly requested.
- Completion requires applicable tests, schema checks, Fake Agent E2E, dashboard tests/build, an audit report and explicit disclosure of anything not run.

See `docs/quality-and-audit.md` for the detailed audit policy.
