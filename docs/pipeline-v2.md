# Pipeline V2

Pipeline V2 advances only after each stage writes and validates its canonical artifact. Agent stages are injected through a registry, which lets production use the configured Codex boundary while tests use deterministic Fake Agents.

Automatic repair is bounded per stage and per run. Parser or contract errors can retry the producing stage. Missing external evidence is marked `UPSTREAM_DATA_REQUIRED` or `HUMAN_REQUIRED`; it is never repaired by synthesizing a value. Gap Search targets only unresolved critical/important requirements within its configured budget.
