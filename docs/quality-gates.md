# Quality gates

Quality rules classify deterministic errors, parser false positives, heuristic warnings, and evidence gaps. Blocking errors carry an artifact and JSON Pointer; repeated item-level failures are aggregated into a root cause while raw issues remain available.

Examples of blocking contracts include malformed Review IDs, broken Observation lineage, missing structured scenarios, invalid fact references, incompatible ranking inputs, and Final/Report Data hash drift. Warnings do not block unless the policy explicitly promotes them. Quality checks do not recursively inspect their own generated prose.
