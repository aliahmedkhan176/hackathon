"""Append a new punch export to the raw warehouse without reloading other files."""
import argparse
import csv
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from ingestion.load_raw import DB_PATH, LOG_DIR, read_records, row_hash

ROOT = Path(__file__).resolve().parents[1]
RAW_TABLE = "raw_biometric_punches"


def load_incremental_punches(
    source_path: Path,
    database_path: Path = DB_PATH,
    log_path: Path = LOG_DIR / "incremental_load_counts.csv",
) -> dict:
    source_path = Path(source_path)
    if not source_path.is_file() or source_path.suffix.lower() != ".csv":
        raise ValueError(f"Expected an existing CSV punch export: {source_path}")

    headers, rows = read_records(source_path)
    if not headers or len(headers) != len(set(headers)):
        raise ValueError(f"{source_path} must have a header row with unique column names")

    with closing(sqlite3.connect(database_path)) as conn:
        existing_columns = {
            row[1]
            for row in conn.execute(f'PRAGMA table_info("{RAW_TABLE}")')
        }
        if not existing_columns:
            raise RuntimeError(
                f"{RAW_TABLE} does not exist in {database_path}; run the full pipeline first"
            )
        expected_headers = [
            row[1]
            for row in conn.execute(f'PRAGMA table_info("{RAW_TABLE}")')
            if row[1] not in {"_source_file", "_loaded_at", "_row_hash"}
        ]
        if headers != expected_headers:
            raise ValueError(
                f"Punch export columns do not match {RAW_TABLE}; "
                f"expected {expected_headers}, received {headers}"
            )
        if not {"_source_file", "_loaded_at", "_row_hash"}.issubset(existing_columns):
            raise RuntimeError(f"{RAW_TABLE} is missing required raw-load metadata columns")

        before_count = conn.execute(f'SELECT COUNT(*) FROM "{RAW_TABLE}"').fetchone()[0]
        loaded_at = datetime.now(timezone.utc).isoformat()
        insert_columns = headers + ["_source_file", "_loaded_at", "_row_hash"]
        quoted_columns = ", ".join(
            '"' + column.replace('"', '""') + '"' for column in insert_columns
        )
        placeholders = ", ".join("?" for _ in insert_columns)
        new_rows = 0
        for row in rows:
            values = [row.get(header, "") for header in headers]
            values.extend([source_path.name, loaded_at, row_hash(row)])
            cursor = conn.execute(
                f'INSERT OR IGNORE INTO "{RAW_TABLE}" ({quoted_columns}) '
                f"VALUES ({placeholders})",
                values,
            )
            new_rows += cursor.rowcount

        after_count = conn.execute(f'SELECT COUNT(*) FROM "{RAW_TABLE}"').fetchone()[0]
        failed_rows = int(after_count - before_count != new_rows)
        skipped_rows = len(rows) - new_rows
        dq_details = (
            f"source_rows={len(rows)}, new_rows={new_rows}, "
            f"already_present_rows={skipped_rows}, table_rows={after_count}"
        )
        conn.execute(
            "INSERT INTO dq_results "
            "(check_name, table_name, failed_rows, status, details) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                "incremental punch raw-row reconciliation",
                RAW_TABLE,
                failed_rows,
                "FAIL" if failed_rows else "PASS",
                dq_details,
            ),
        )
        conn.commit()

    report = {
        "source_file": source_path.name,
        "table_name": RAW_TABLE,
        "source_rows": len(rows),
        "new_rows": new_rows,
        "already_present_rows": skipped_rows,
        "table_rows": after_count,
        "status": "PASS" if not failed_rows else "FAIL",
    }
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not log_path.exists() or log_path.stat().st_size == 0
    with log_path.open("a", encoding="utf-8", newline="") as log_file:
        writer = csv.DictWriter(log_file, fieldnames=report.keys())
        if write_header:
            writer.writeheader()
        writer.writerow(report)

    if failed_rows:
        raise RuntimeError(f"Incremental punch reconciliation failed: {dq_details}")
    print(
        f"{source_path.name}: source={len(rows)}, new={new_rows}, "
        f"already_present={skipped_rows}, table={after_count}"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Append only a new punch CSV to the raw punch table."
    )
    parser.add_argument(
        "--file",
        required=True,
        type=Path,
        help="Path to the new punch CSV; existing source files are not reloaded.",
    )
    args = parser.parse_args()
    load_incremental_punches(args.file)


if __name__ == "__main__":
    main()
