# Security policy

Please report security issues privately to the repository owner instead of opening a public issue. Do not attach run folders that may contain confidential research inputs.

The repository is designed to run its deterministic tests, Fake Agent E2E, and frontend build without an API key. Local `outputs/`, Streamlit secrets, browser profiles, `.env` files, and generated dashboard data are ignored. Before publishing, run `python -m tools.repository_check` and inspect the staged diff manually.

The platform does not bypass paywalls, authentication, CAPTCHAs, robots restrictions, or access controls. Evidence obtained from public sources should retain source attribution and short excerpts only.
