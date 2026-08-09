# Quality and audit policy

Run `python -m tools.audit_latest_run --run latest --revision latest --fix --offline --report` from the repository root.

Discovery parses every top-level `outputs/**/run_manifest.json` and orders by manifest `updated_at` (falling back to completion/creation fields). An incomplete newest run is identified separately while the most recent complete artifact chain becomes the audit target. Revision `latest` resolves through the manifest.

The auditor checks Scope, Review, Fact IDs and labels, full Observation lineage, time-series periods, structured scenarios, file hashes, Gap Search execution evidence, Dashboard/Quality consistency, component readiness, Revision manifests, and repository hygiene. `--fix` writes only derived reports under `audit/`; it never edits original outputs or invokes a live Agent.

Exit codes are stable: `0 PASS`, `1 WARN_ONLY`, `2 DETERMINISTIC_FAIL`, `3 INCOMPLETE_RUN`, and `4 TOOL_ERROR`. Findings that require new external evidence are labelled for a live rerun instead of being fabricated.
