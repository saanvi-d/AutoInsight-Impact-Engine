
"""Simple, transparent impact estimates for common cleaning actions."""
from app.db import quote_ident


def simulate_cleaning_impact(
    con,
    table_name: str,
    drop_duplicates: bool = True,
    fill_missing: str = "none",
) -> dict:
    table = quote_ident(table_name)

    # Count the original rows.
    rows = int(
        con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    )

    # Count rows that would be removed as exact duplicates.
    duplicate_count = 0

    if drop_duplicates:
        columns = con.execute(
            f"DESCRIBE SELECT * FROM {table}"
        ).fetchall()

        column_names = [row[0] for row in columns]

        if column_names:
            group_columns = ", ".join(
                quote_ident(name) for name in column_names
            )

            duplicate_count = int(
                con.execute(
                    f"""
                    SELECT COALESCE(SUM(n - 1), 0)
                    FROM (
                        SELECT COUNT(*) AS n
                        FROM {table}
                        GROUP BY {group_columns}
                        HAVING COUNT(*) > 1
                    ) AS duplicate_groups
                    """
                ).fetchone()[0]
            )

    # Count NULL cells without modifying the dataset.
    missing_cells = 0

    for row in con.execute(
        f"DESCRIBE SELECT * FROM {table}"
    ).fetchall():
        column_name = row[0]

        missing_cells += int(
            con.execute(
                f"""
                SELECT COUNT(*)
                FROM {table}
                WHERE {quote_ident(column_name)} IS NULL
                """
            ).fetchone()[0]
        )

    projected_rows = rows - duplicate_count

    return {
        "rows_before": rows,
        "estimated_rows_after": projected_rows,
        "estimated_rows_removed": duplicate_count,
        "missing_cells_detected": missing_cells,
        "fill_missing_strategy": fill_missing,
        "actions": {
            "drop_exact_duplicates": drop_duplicates,
            "fill_missing": fill_missing,
        },
        "limitations": [
            "Estimates are based on exact duplicate rows and NULL counts.",
            "This simulation does not modify the dataset.",
            "No anomaly detection is performed.",
        ],
    }
