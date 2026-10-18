from __future__ import annotations
import csv
import json
import uuid
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field
from app.config import DATA_DIR, MAX_UPLOAD_BYTES, MAX_PREVIEW_ROWS
from app.db import connect, get_dataset, table_name_for, quote_ident, describe_columns
from app.engines.profiling import profile_dataset
from app.engines.cleaning import preview_cleaning, apply_cleaning
from app.engines.impact import simulate_cleaning_impact
from app.engines.qa import answer_question

app = FastAPI(title="AutoInsight Impact Engine", version="1.0.0",
              description="CSV profiling, SQL-backed cleaning, impact simulation, and exports. Anomaly detection is intentionally excluded.")


class CleaningRequest(BaseModel):
    drop_duplicates: bool = False
    fill_missing: str = Field(default="none", pattern="^(none|zero|mean|median|mode|constant)$")
    fill_value: str = ""


class ImpactRequest(BaseModel):
    drop_duplicates: bool = True
    fill_missing: str = "none"


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


@app.get("/health")
def health():
    return {"status": "ok", "service": "AutoInsight Impact Engine", "anomaly_detection": False}


@app.get("/", response_class=HTMLResponse)
def dashboard():
    path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(path.read_text(encoding="utf-8"))


@app.post("/api/datasets", status_code=201)
async def upload_dataset(file: UploadFile = File(...)):
    filename = Path(file.filename or "dataset.csv").name
    if Path(filename).suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")
    dataset_id = uuid.uuid4().hex
    target = (DATA_DIR / f"{dataset_id}_{filename}").resolve()
    if DATA_DIR not in target.parents:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    size = 0
    try:
        with target.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_BYTES} bytes.")
                out.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        # Validate a header before asking DuckDB to infer the full schema.
        with target.open("r", encoding="utf-8-sig", newline="") as stream:
            header = next(csv.reader(stream), [])
        if not header or not any(str(x).strip() for x in header):
            raise HTTPException(status_code=400, detail="The CSV needs a non-empty header row.")
        table_name = table_name_for(dataset_id)
        con = connect()
        try:
            escaped_path = str(target).replace("'", "''")
            con.execute(f"CREATE TABLE {quote_ident(table_name)} AS SELECT * FROM read_csv_auto('{escaped_path}', header=true, sample_size=20000)")
            rows = int(con.execute(f"SELECT COUNT(*) FROM {quote_ident(table_name)}").fetchone()[0])
            columns = describe_columns(con, table_name)
            con.execute("INSERT INTO datasets(dataset_id, name, table_name, source_path, row_count, columns_json) VALUES (?, ?, ?, ?, ?, ?)",
                        [dataset_id, filename, table_name, str(target), rows, json.dumps(columns)])
        finally:
            con.close()
        return {"dataset_id": dataset_id, "name": filename, "rows": rows,
                "columns": columns, "message": "CSV imported successfully."}
    except HTTPException:
        target.unlink(missing_ok=True)
        raise
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Could not import CSV: {exc}") from exc
    finally:
        await file.close()


@app.get("/api/datasets")
def list_datasets():
    con = connect()
    try:
        rows = con.execute("SELECT dataset_id, name, row_count, columns_json, created_at FROM datasets ORDER BY created_at DESC").fetchall()
        return [{"dataset_id": r[0], "name": r[1], "rows": int(r[2]),
                 "columns": json.loads(r[3]), "created_at": str(r[4])} for r in rows]
    finally:
        con.close()


def require_dataset(con, dataset_id: str):
    dataset = get_dataset(con, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return dataset


@app.get("/api/datasets/{dataset_id}/profile")
def get_profile(dataset_id: str):
    con = connect()
    try:
        dataset = require_dataset(con, dataset_id)
        return {"dataset_id": dataset_id, "name": dataset["name"], **profile_dataset(con, dataset["table_name"])}
    finally:
        con.close()


@app.get("/api/datasets/{dataset_id}/preview")
def get_preview(dataset_id: str, limit: int = MAX_PREVIEW_ROWS):
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 1000.")
    con = connect()
    try:
        dataset = require_dataset(con, dataset_id)
        table = quote_ident(dataset["table_name"])
        columns = [row[0] for row in con.execute(f"DESCRIBE SELECT * FROM {table}").fetchall()]
        frame = con.execute(f"SELECT * FROM {table} LIMIT ?", [limit]).fetchdf()
        frame = frame.astype(object).where(frame.notna(), None)
        rows = frame.to_dict(orient="records")
        return {"columns": columns, "rows": rows, "limit": limit}
    finally:
        con.close()


@app.get("/api/datasets/{dataset_id}/cleaning/preview")
def get_cleaning_preview(dataset_id: str):
    con = connect()
    try:
        dataset = require_dataset(con, dataset_id)
        return preview_cleaning(con, dataset["table_name"])
    finally:
        con.close()


@app.post("/api/datasets/{dataset_id}/cleaning/apply")
def clean_dataset(dataset_id: str, request: CleaningRequest):
    con = connect()
    try:
        dataset = require_dataset(con, dataset_id)
        try:
            return apply_cleaning(con, dataset, drop_duplicates=request.drop_duplicates,
                                  fill_missing=request.fill_missing, fill_value=request.fill_value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        con.close()


@app.post("/api/datasets/{dataset_id}/impact/simulate")
def impact(dataset_id: str, request: ImpactRequest):
    con = connect()
    try:
        dataset = require_dataset(con, dataset_id)
        if request.fill_missing not in {"none", "zero", "mean", "median", "mode", "constant"}:
            raise HTTPException(status_code=400, detail="Unsupported fill_missing strategy.")
        return simulate_cleaning_impact(con, dataset["table_name"], request.drop_duplicates, request.fill_missing)
    finally:
        con.close()


@app.post("/api/datasets/{dataset_id}/qa")
def qa(dataset_id: str, request: QuestionRequest):
    con = connect()
    try:
        dataset = require_dataset(con, dataset_id)
        return answer_question(con, dataset["table_name"], request.question)
    finally:
        con.close()


@app.get("/api/datasets/{dataset_id}/export.csv")
def export_csv(dataset_id: str):
    # Validate before streaming so an unknown ID produces a normal HTTP 404.
    con_check = connect()
    try:
        require_dataset(con_check, dataset_id)
    finally:
        con_check.close()

    # The generator owns its connection so it stays open until streaming completes.
    def generate():
        con = connect()
        try:
            dataset = require_dataset(con, dataset_id)
            table = quote_ident(dataset["table_name"])
            result = con.execute(f"SELECT * FROM {table}")
            columns = [d[0] for d in result.description]
            buffer = __import__("io").StringIO()
            writer = csv.writer(buffer)
            writer.writerow(columns)
            yield buffer.getvalue()
            buffer.seek(0); buffer.truncate(0)
            while True:
                batch = result.fetchmany(5000)
                if not batch:
                    break
                writer.writerows(batch)
                yield buffer.getvalue()
                buffer.seek(0); buffer.truncate(0)
        finally:
            con.close()
    return StreamingResponse(generate(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{dataset_id}.csv"'})
