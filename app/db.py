"""DuckDB access and dataset metadata helpers."""
from __future__ import annotations
import json
import re
import duckdb
from app.config import DB_PATH


def connect():
    con = duckdb.connect(str(DB_PATH))
    con.execute("""
        CREATE TABLE IF NOT EXISTS datasets (
            dataset_id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            table_name VARCHAR NOT NULL,
            source_path VARCHAR NOT NULL,
            row_count BIGINT NOT NULL,
            columns_json VARCHAR NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    return con


def quote_ident(identifier: str) -> str:
    """Quote a SQL identifier safely."""
    return '"' + str(identifier).replace('"', '""') + '"'


def table_name_for(dataset_id: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{32}", dataset_id):
        raise ValueError("Invalid dataset ID")
    return f"ds_{dataset_id}"


def get_dataset(con, dataset_id: str):
    row = con.execute(
        "SELECT dataset_id, name, table_name, source_path, row_count, columns_json, created_at FROM datasets WHERE dataset_id = ?",
        [dataset_id],
    ).fetchone()
    if row is None:
        return None
    return {
        "dataset_id": row[0], "name": row[1], "table_name": row[2],
        "source_path": row[3], "row_count": int(row[4]),
        "columns": json.loads(row[5]), "created_at": str(row[6]),
    }


def describe_columns(con, table_name: str):
    rows = con.execute(f"DESCRIBE SELECT * FROM {quote_ident(table_name)}").fetchall()
    return [{"name": row[0], "type": row[1]} for row in rows]
