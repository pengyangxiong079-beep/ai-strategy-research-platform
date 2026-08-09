# Contributing

Use canonical JSON as the source of truth and treat `outputs/` as immutable local audit evidence. Start from a focused issue, add a regression test, and keep live Agent calls outside automated tests.

Before proposing a change, run:

```powershell
python -m pytest -q
python scripts/run_v2_offline_e2e.py
python -m tools.repository_check
Set-Location dashboard-web
npm.cmd test
npm.cmd run build
```

Do not commit credentials, local outputs, generated dashboard data, or personal paths. A Quality `PASS` means the deterministic contracts passed; it is not a guarantee that every external fact is true.
