"""Dataset profiling implemented with DuckDB queries."""
from __future__ import annotations
from app.db import quote_ident


def profile_dataset(con, table_name: str) -> dict:
    table = quote_ident(table_name)
    columns = con.execute(f"DESCRIBE SELECT * FROM {table}").fetchall()
    row_count = int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    col_profiles = []
    for name, dtype, *_ in columns:
        col = quote_ident(name)
        missing = int(con.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL").fetchone()[0])
        distinct = int(con.execute(f"SELECT COUNT(DISTINCT {col}) FROM {table}").fetchone()[0])
        item = {"column": name, "dtype": dtype, "missing": missing,
                "missing_percent": round((missing / row_count * 100), 2) if row_count else 0.0,
                "distinct": distinct}
        if any(token in dtype.upper() for token in ("INT", "DECIMAL", "DOUBLE", "FLOAT", "REAL", "HUGEINT", "UBIGINT")):
            stats = con.execute(
                f"SELECT MIN({col}), MAX({col}), AVG(TRY_CAST({col} AS DOUBLE)) FROM {table}"
            ).fetchone()
            item.update({"min": stats[0], "max": stats[1], "mean": stats[2]})
        col_profiles.append(item)
    return {"rows": row_count, "columns": len(columns), "column_profiles": col_profiles}
