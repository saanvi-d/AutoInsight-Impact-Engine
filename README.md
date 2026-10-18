# AutoInsight Impact Engine

A local CSV data-profiling and cleaning-impact application built with **FastAPI**, **DuckDB**, and **pandas**. The project intentionally contains **no anomaly-detection feature, code, routes, or imports**.

## Features

- CSV upload with a configurable upload-size limit.
- DuckDB-backed tables and SQL-based profiling, suitable for larger CSVs without loading the entire table into pandas for each operation.
- Column profile: data type, missing count/percentage, distinct count, and numeric min/max/mean.
- Bounded row preview.
- Cleaning preview for missing values and exact duplicate rows.
- Cleaning-impact simulation that does not modify data.
- Explicit cleaning action: remove exact duplicate rows and fill missing values using supported strategies.
- CSV export streamed in batches.
- Basic deterministic Q&A for row counts, column counts, missing values, numeric averages, and numeric totals.
- Browser dashboard and auto-generated API docs.
- Pytest API smoke tests.

## Windows setup (VS Code)

Open the `AutoInsight_Impact_Engine` folder in VS Code. In the VS Code terminal, run these commands from the folder containing `requirements.txt`:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest -q
uvicorn app.main:app --reload
```

If PowerShell blocks activation, use Command Prompt terminal instead:

```bat
.venv\Scripts\activate.bat
```

Then open:

- Dashboard: http://127.0.0.1:8000/
- Interactive API docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

## Typical workflow

1. Upload a CSV from the dashboard.
2. Review the profile and preview.
3. Preview cleaning opportunities.
4. Run impact simulation to estimate the effect without modifying data.
5. If the result is appropriate, explicitly apply cleaning.
6. Export the resulting active table as CSV.

## Cleaning behavior and data safety

- The impact simulator is read-only.
- Applying cleaning replaces the active DuckDB table. The uploaded source CSV remains on disk, so it can be re-uploaded if you need the original state.
- Exact duplicate rows are removed only when requested.
- `mean` and `median` fill strategies apply to numeric columns. `mode` applies to any column. `zero` fills numeric nulls only. `constant` uses the provided constant.
- Missing values are nulls as interpreted by DuckDB during CSV import. CSV import type inference can affect how empty cells are interpreted.
- This is a local-development project; do not expose it to untrusted networks without authentication, authorization, and deployment hardening.

## Large datasets

CSV ingestion creates a DuckDB table directly from the CSV file. Profile and cleaning operations are SQL-based. The preview is limited, and CSV export is streamed in batches. Very wide/large files still require adequate disk space and memory for DuckDB's query operations. Adjust `AUTOINSIGHT_MAX_UPLOAD_BYTES` and `AUTOINSIGHT_MAX_PREVIEW_ROWS` if needed.

## Project structure

```text
AutoInsight_Impact_Engine/
├── app/
│   ├── engines/
│   │   ├── cleaning.py
│   │   ├── impact.py
│   │   ├── profiling.py
│   │   └── qa.py
│   ├── static/index.html
│   ├── config.py
│   ├── db.py
│   └── main.py
├── data_store/
├── tests/test_api.py
├── requirements.txt
└── README.md
```

There is deliberately no `app/engines/anomaly.py` and no anomaly endpoint. If you are replacing an older local copy, use this folder as a clean project copy rather than merging old imports back into it.
