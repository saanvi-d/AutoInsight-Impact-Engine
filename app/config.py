from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("AUTOINSIGHT_DATA_DIR", BASE_DIR / "data_store")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.getenv("AUTOINSIGHT_DB_PATH", DATA_DIR / "autoinsight.duckdb")).resolve()
MAX_UPLOAD_BYTES = int(os.getenv("AUTOINSIGHT_MAX_UPLOAD_BYTES", str(250 * 1024 * 1024)))
MAX_PREVIEW_ROWS = int(os.getenv("AUTOINSIGHT_MAX_PREVIEW_ROWS", "100"))
