# Local development

Use Python 3.10+ and Node 20+ (Node 22 is used in CI).

```powershell
python -m pip install -r requirements.txt pytest
python -m pytest -q
python scripts/run_v2_offline_e2e.py
python -m streamlit run app.py
```

```powershell
Set-Location dashboard-web
npm.cmd ci
npm.cmd test
npm.cmd run build
npm.cmd run dev
```

Do not point automated tests at live Agents. Local outputs are audit records and must not be edited to make a check pass.
