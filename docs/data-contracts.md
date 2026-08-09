# Data contracts

The core chain is Source → Observation → verified Claim → Report Data → Dashboard Data.

- Sources retain publisher, URL, grade, language, access time, and access result.
- Observations retain entity, metric, value/text, unit, period, geography, definition, source ID, value type, temporal status, verification status, and comparability group.
- Claims are atomic and link Observation IDs.
- Report and Dashboard items link Fact and Observation IDs.

Comparability is metric-specific. Different metrics are never scored as mutually comparable; a single-entity time series is comparable when the same metric definition, unit, scope, and period convention are stable across periods.
