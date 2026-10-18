"""Small deterministic natural-language question helper; no generated SQL is executed."""
import re
from app.db import quote_ident


def answer_question(con, table_name: str, question: str) -> dict:
    q = question.strip().lower()
    table = quote_ident(table_name)
    columns = con.execute(f"DESCRIBE SELECT * FROM {table}").fetchall()
    names = [row[0] for row in columns]
    if not names:
        return {"question": question, "answer": "The dataset has no columns.", "sql": None}
    if any(term in q for term in ("how many rows", "row count", "number of rows", "total rows")):
        sql = f"SELECT COUNT(*) FROM {table}"
        value = con.execute(sql).fetchone()[0]
        return {"question": question, "answer": f"The dataset contains {value:,} rows.", "sql": sql}
    if any(term in q for term in ("how many columns", "column count", "number of columns")):
        return {"question": question, "answer": f"The dataset contains {len(names)} columns: {', '.join(names)}.", "sql": None}
    if "missing" in q or "null" in q:
        counts = []
        for name in names:
            n = int(con.execute(f"SELECT COUNT(*) FROM {table} WHERE {quote_ident(name)} IS NULL").fetchone()[0])
            if n:
                counts.append(f"{name}: {n}")
        answer = "Missing values — " + ("; ".join(counts) if counts else "none found.")
        return {"question": question, "answer": answer, "sql": "Per-column COUNT(*) WHERE column IS NULL"}
    numeric = [row[0] for row in columns if any(t in row[1].upper() for t in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "REAL"))]
    for name in names:
        if name.lower() in q and name in numeric and any(term in q for term in ("average", "mean", "avg")):
            sql = f"SELECT AVG({quote_ident(name)}) FROM {table}"
            value = con.execute(sql).fetchone()[0]
            answer = f"Average {name}: {value:,.4f}" if value is not None else f"No numeric values available in {name}."
            return {"question": question, "answer": answer, "sql": sql}
        if name.lower() in q and name in numeric and any(term in q for term in ("sum", "total")):
            sql = f"SELECT SUM({quote_ident(name)}) FROM {table}"
            value = con.execute(sql).fetchone()[0]
            return {"question": question, "answer": f"Total {name}: {value}", "sql": sql}
    return {"question": question,
            "answer": "I can answer row-count, column-count, missing-value, numeric average, and numeric total questions. Include the exact numeric column name for averages or totals.",
            "sql": None}
