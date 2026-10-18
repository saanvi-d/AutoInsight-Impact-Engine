"""SQL-based cleaning preview and application. Original tables are retained until replacement succeeds."""
from __future__ import annotations
from app.db import quote_ident


def preview_cleaning(con, table_name: str) -> dict:
    table = quote_ident(table_name)
    row_count = int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    duplicate_rows = int(con.execute(
        f"SELECT COALESCE(SUM(n - 1), 0) FROM (SELECT COUNT(*) AS n FROM {table} GROUP BY ALL HAVING COUNT(*) > 1) d"
    ).fetchone()[0])
    cols = con.execute(f"DESCRIBE SELECT * FROM {table}").fetchall()
    missing = []
    for name, *_ in cols:
        count = int(con.execute(f"SELECT COUNT(*) FROM {table} WHERE {quote_ident(name)} IS NULL").fetchone()[0])
        if count:
            missing.append({"column": name, "missing": count})
    return {"rows_before": row_count, "duplicate_rows_removable": duplicate_rows,
            "columns_with_missing_values": missing,
            "suggestions": [
                "Remove exact duplicate rows if they are not meaningful records.",
                "Review missing values before choosing a fill strategy.",
                "Keep an unchanged copy of the original dataset for comparison.",
            ]}


def apply_cleaning(con, dataset: dict, *, drop_duplicates: bool = False,
                   fill_missing: str = "none", fill_value: str = "") -> dict:
    allowed = {"none", "zero", "mean", "median", "mode", "constant"}
    if fill_missing not in allowed:
        raise ValueError(f"fill_missing must be one of: {', '.join(sorted(allowed))}")
    source = quote_ident(dataset["table_name"])
    new_table = quote_ident(dataset["table_name"] + "_cleaned")
    con.execute(f"DROP TABLE IF EXISTS {new_table}")
    cols = con.execute(f"DESCRIBE SELECT * FROM {source}").fetchall()
    expressions = []
    for name, dtype, *_ in cols:
        col = quote_ident(name)
        expr = col
        if fill_missing != "none":
            if fill_missing == "zero" and any(t in dtype.upper() for t in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "REAL")):
                expr = f"COALESCE({col}, 0)"
            elif fill_missing == "constant":
                literal = "'" + fill_value.replace("'", "''") + "'"
                if any(t in dtype.upper() for t in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "REAL")):
                    try:
                        float(fill_value)
                        literal = f"TRY_CAST({literal} AS {dtype})"
                    except ValueError:
                        pass
                expr = f"COALESCE({col}, {literal})"
            elif fill_missing in {"mean", "median"} and any(t in dtype.upper() for t in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "REAL")):
                fn = "AVG" if fill_missing == "mean" else "MEDIAN"
                expr = f"COALESCE({col}, (SELECT {fn}({col}) FROM {source}))"
            elif fill_missing == "mode":
                expr = f"COALESCE({col}, (SELECT {col} FROM {source} WHERE {col} IS NOT NULL GROUP BY {col} ORDER BY COUNT(*) DESC LIMIT 1))"
        expressions.append(f"{expr} AS {col}")
    distinct = "DISTINCT " if drop_duplicates else ""
    con.execute(f"CREATE TABLE {new_table} AS SELECT {distinct}{', '.join(expressions)} FROM {source}")
    before = int(con.execute(f"SELECT COUNT(*) FROM {source}").fetchone()[0])
    after = int(con.execute(f"SELECT COUNT(*) FROM {new_table}").fetchone()[0])
    # Replace table atomically after successful CTAS.
    con.execute(f"DROP TABLE {source}")
    con.execute(f"ALTER TABLE {new_table} RENAME TO {quote_ident(dataset['table_name'])}")
    columns = [{"name": row[0], "type": row[1]} for row in con.execute(f"DESCRIBE SELECT * FROM {quote_ident(dataset['table_name'])}").fetchall()]
    con.execute("UPDATE datasets SET row_count = ?, columns_json = ? WHERE dataset_id = ?",
                [after, __import__('json').dumps(columns), dataset["dataset_id"]])
    return {"rows_before": before, "rows_after": after, "rows_removed": before-after,
            "drop_duplicates": drop_duplicates, "fill_missing": fill_missing,
            "columns": columns,
            "warning": "Cleaning replaces the active dataset table. Keep the source CSV if you need an original copy."}
