# Dashboard design

The dashboard uses one rendering engine, an analysis-template registry, and reusable components. Templates define the decision question, page order, required datasets, widget priority, evidence policy, and Empty States.

The renderer consumes structured JSON only. It filters unsupported values, labels partial evidence, preserves actual/forecast/target/modelled semantics, and hides optional empty widgets while keeping a professional Empty State for required widgets. Quality-blocked reports may be previewed with a prominent warning, but never presented as ready.
