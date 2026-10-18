from io import BytesIO
import os
import tempfile
from fastapi.testclient import TestClient

# Isolate each test run's DuckDB file before importing the application.
_tmp = tempfile.TemporaryDirectory()
os.environ["AUTOINSIGHT_DATA_DIR"] = _tmp.name
os.environ["AUTOINSIGHT_DB_PATH"] = os.path.join(_tmp.name, "test.duckdb")
from app.main import app

client = TestClient(app)


def uploaded():
    content = b"id,department,revenue\n1,Sales,100\n2,Sales,200\n2,Sales,200\n3,Support,\n"
    response = client.post("/api/datasets", files={"file": ("sample.csv", BytesIO(content), "text/csv")})
    assert response.status_code == 201, response.text
    return response.json()["dataset_id"]


def test_health_excludes_anomaly_detection():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["anomaly_detection"] is False


def test_upload_profile_and_preview():
    dataset_id = uploaded()
    profile = client.get(f"/api/datasets/{dataset_id}/profile")
    assert profile.status_code == 200
    assert profile.json()["rows"] == 4
    assert profile.json()["columns"] == 3
    preview = client.get(f"/api/datasets/{dataset_id}/preview")
    assert preview.status_code == 200
    assert len(preview.json()["rows"]) == 4


def test_cleaning_preview_and_impact_do_not_modify_data():
    dataset_id = uploaded()
    preview = client.get(f"/api/datasets/{dataset_id}/cleaning/preview").json()
    assert preview["rows_before"] == 4
    impact = client.post(f"/api/datasets/{dataset_id}/impact/simulate", json={"drop_duplicates": True}).json()
    assert impact["estimated_rows_after"] == 3
    assert client.get(f"/api/datasets/{dataset_id}/profile").json()["rows"] == 4


def test_cleaning_apply_and_qa():
    dataset_id = uploaded()
    result = client.post(f"/api/datasets/{dataset_id}/cleaning/apply", json={"drop_duplicates": True, "fill_missing": "none"})
    assert result.status_code == 200, result.text
    assert result.json()["rows_after"] == 3
    answer = client.post(f"/api/datasets/{dataset_id}/qa", json={"question": "How many rows?"})
    assert answer.status_code == 200
    assert "3 rows" in answer.json()["answer"]


def test_export_csv():
    dataset_id = uploaded()
    r = client.get(f"/api/datasets/{dataset_id}/export.csv")
    assert r.status_code == 200
    assert "department" in r.text


def test_reject_non_csv():
    r = client.post("/api/datasets", files={"file": ("sample.xlsx", BytesIO(b"not csv"), "application/octet-stream")})
    assert r.status_code == 400
