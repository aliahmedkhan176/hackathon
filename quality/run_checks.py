from datetime import datetime, timezone
from pathlib import Path
import csv
import json
import sqlite3

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
STAGING = ROOT / "results" / "staging"
ATTENDANCE = ROOT / "results" / "attendance"
DB = ROOT / "indus_weave.db"
LOG = ROOT / "logs" / "dq_results.csv"

RECONCILIATIONS = {
    "raw_applications": [("staging", "applications_clean.csv")],
    "raw_biometric_punches": [
        ("staging", "biometric_punches_mapped_deduped.csv"),
        ("staging", "rejected_punches.csv"),
        ("staging", "duplicate_punches.csv"),
    ],
    "raw_departments": [("staging", "departments_clean.csv")],
    "raw_device_mapping": [("staging", "device_mapping_clean.csv")],
    "raw_employees": [
        ("staging", "employees_clean.csv"),
        ("staging", "employee_dedup_audit.csv"),
    ],
    "raw_employment_history": [
        ("staging", "employment_history_clean.csv"),
        ("staging", "employment_history_dedup_audit.csv"),
    ],
    "raw_holidays": [("staging", "holidays_clean.csv")],
    "raw_leave_requests": [("staging", "leave_requests_clean.csv")],
    "raw_overtime_requests": [("staging", "overtime_requests_clean.csv")],
    "raw_payroll_lines": [("staging", "payroll_lines_clean.csv")],
    "raw_shift_roster": [("staging", "shift_roster_clean.csv")],
}


def csv_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return max(sum(1 for _ in csv.reader(stream)) - 1, 0)


def main(final: bool = True) -> None:
    ROOT.joinpath("logs").mkdir(exist_ok=True)
    results = []
    checked_at = datetime.now(timezone.utc).isoformat()

    def record(name: str, table: str, failed: int, details: str) -> None:
        results.append({
            "check_name": name,
            "table_name": table,
            "failed_rows": int(failed),
            "status": "PASS" if failed == 0 else "FAIL",
            "details": details,
            "checked_at": checked_at,
        })

    with sqlite3.connect(DB) as conn:
        raw_tables = [
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'raw_%' ORDER BY name"
            )
        ]
        record("raw_input_tables_present", "raw_*", 0 if raw_tables else 1,
               f"found={len(raw_tables)}")

        for table in raw_tables:
            escaped = table.replace('"', '""')
            columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{escaped}")')}
            missing = {"_source_file", "_loaded_at", "_row_hash"} - columns
            null_hashes = conn.execute(
                f'SELECT COUNT(*) FROM "{escaped}" WHERE "_row_hash" IS NULL OR "_row_hash" = \'\''
            ).fetchone()[0]
            duplicate_hashes = conn.execute(
                f'SELECT COUNT(*) FROM (SELECT "_source_file","_row_hash" FROM "{escaped}" '
                'GROUP BY "_source_file","_row_hash" HAVING COUNT(*) > 1)'
            ).fetchone()[0]
            record("raw_metadata_columns", table, len(missing), f"missing={sorted(missing)}")
            record("raw_hash_not_null_and_unique", table, null_hashes + duplicate_hashes,
                   f"null_or_empty={null_hashes}; duplicate_hash_groups={duplicate_hashes}")

        if not final:
            conn.execute("DROP TABLE IF EXISTS dq_results")
            conn.execute("""CREATE TABLE dq_results(
                dq_id INTEGER PRIMARY KEY, check_name TEXT NOT NULL, table_name TEXT NOT NULL,
                failed_rows INTEGER NOT NULL, status TEXT NOT NULL, details TEXT,
                checked_at TEXT NOT NULL
            )""")
            conn.executemany(
                "INSERT INTO dq_results(check_name,table_name,failed_rows,status,details,checked_at) "
                "VALUES(?,?,?,?,?,?)",
                [(r["check_name"], r["table_name"], r["failed_rows"], r["status"],
                  r["details"], r["checked_at"]) for r in results],
            )
            conn.commit()
        else:
            for table, output_files in RECONCILIATIONS.items():
                if table not in raw_tables:
                    record("raw_to_staging_reconciliation", table, 1, "raw table is missing")
                    continue
                raw_count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                counts = []
                missing_outputs = []
                for layer, filename in output_files:
                    path = (STAGING if layer == "staging" else ATTENDANCE) / filename
                    if path.exists():
                        counts.append(csv_rows(path))
                    else:
                        missing_outputs.append(filename)
                staged_count = sum(counts)
                record(
                    "raw_to_staging_reconciliation",
                    table,
                    abs(raw_count - staged_count) + len(missing_outputs),
                    f"raw={raw_count}; outputs={counts}; staged_plus_rejected={staged_count}; "
                    f"missing_outputs={missing_outputs}",
                )

            shifts_raw = conn.execute(
                'SELECT "_json_record" FROM raw_shifts LIMIT 1'
            ).fetchone()
            shift_count = len(json.loads(shifts_raw[0]).get("shifts", [])) if shifts_raw else 0
            built_shift_count = conn.execute("SELECT COUNT(*) FROM dim_shift").fetchone()[0]
            record("raw_to_warehouse_reconciliation", "raw_shifts", abs(shift_count - built_shift_count),
                   f"source_shift_definitions={shift_count}; warehouse_shifts={built_shift_count}")

            warehouse_tables = [
                "dim_department", "dim_shift", "dim_date", "dim_employee",
                "fact_attendance_daily", "fact_leave_day", "fact_overtime_approved",
                "fact_payroll_line",
            ]
            for table in warehouse_tables:
                escaped = table.replace('"', '""')
                info = conn.execute(f'PRAGMA table_info("{escaped}")').fetchall()
                primary_key = [row[1] for row in sorted(info, key=lambda row: row[5]) if row[5]]
                if not primary_key:
                    record("primary_key_defined", table, 1, "no primary key is declared")
                    continue
                null_predicate = " OR ".join(f'"{col}" IS NULL' for col in primary_key)
                null_count = conn.execute(
                    f'SELECT COUNT(*) FROM "{escaped}" WHERE {null_predicate}'
                ).fetchone()[0]
                group_by = ", ".join(f'"{col}"' for col in primary_key)
                duplicate_count = conn.execute(
                    f'SELECT COUNT(*) FROM (SELECT {group_by} FROM "{escaped}" '
                    f'GROUP BY {group_by} HAVING COUNT(*) > 1)'
                ).fetchone()[0]
                record("primary_key_not_null_unique", table, null_count + duplicate_count,
                       f"primary_key={primary_key}; null_rows={null_count}; duplicate_groups={duplicate_count}")

            fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            record("foreign_key_integrity", "warehouse", len(fk_violations),
                   f"violations={len(fk_violations)}")

            bad_status = conn.execute(
                """SELECT COUNT(*) FROM fact_attendance_daily
                   WHERE status NOT IN ('Present','Absent','On Leave','Holiday','Weekly Off','Missing Punch')"""
            ).fetchone()[0]
            record("accepted_attendance_status", "fact_attendance_daily", bad_status,
                   "allowed statuses follow case-study rule 12")

            valid_leave_types = set()
            leave_path = STAGING / "leave_requests_clean.csv"
            if leave_path.exists():
                valid_leave_types = set(
                    pd.read_csv(leave_path, usecols=["leave_type"], dtype=str)["leave_type"]
                    .dropna().str.strip().str.casefold()
                )
            bad_leave_types = 0
            if valid_leave_types:
                accepted = tuple(sorted(valid_leave_types))
                placeholders = ",".join("?" for _ in accepted)
                bad_leave_types = conn.execute(
                    f"SELECT COUNT(*) FROM fact_leave_day WHERE lower(trim(leave_type)) NOT IN ({placeholders})",
                    accepted,
                ).fetchone()[0]
            record("accepted_leave_type", "fact_leave_day", bad_leave_types,
                   f"allowed values sourced from cleaned leave requests ({len(valid_leave_types)} types)")

            accepted_components = (
                "BASIC", "HOUSE_RENT", "MEDICAL", "CONVEYANCE", "OVERTIME",
                "INCOME_TAX", "EOBI", "ABSENCE_DEDUCTION", "LOAN_INSTALLMENT",
            )
            bad_components = conn.execute(
                "SELECT COUNT(*) FROM fact_payroll_line WHERE upper(pay_component) NOT IN "
                f"({','.join('?' for _ in accepted_components)})",
                accepted_components,
            ).fetchone()[0]
            record("accepted_pay_component", "fact_payroll_line", bad_components,
                   f"allowed={list(accepted_components)}")

            invalid_scd = conn.execute(
                """SELECT COUNT(*) FROM dim_employee a JOIN dim_employee b
                     ON a.emp_id=b.emp_id AND a.employee_key<b.employee_key
                    AND a.valid_from<=b.valid_to AND b.valid_from<=a.valid_to"""
            ).fetchone()[0]
            record("scd2_ranges_do_not_overlap", "dim_employee", invalid_scd,
                   "validity intervals are inclusive")

            long_shifts = conn.execute(
                """SELECT COUNT(*) FROM dim_shift
                   WHERE ((CAST(substr(end_time,1,2) AS INTEGER)*60+CAST(substr(end_time,4,2) AS INTEGER)
                         -CAST(substr(start_time,1,2) AS INTEGER)*60-CAST(substr(start_time,4,2) AS INTEGER)
                         +CASE WHEN crosses_midnight=1 THEN 1440 ELSE 0 END) > 960)"""
            ).fetchone()[0]
            record("shift_duration_at_most_16_hours", "dim_shift", long_shifts,
                   "duration is computed from local start/end and crosses_midnight")

            sanity = conn.execute(
                """SELECT
                     (SELECT COUNT(*) FROM fact_attendance_daily WHERE worked_hours<0 OR computed_overtime_hours<0) +
                     (SELECT COUNT(*) FROM fact_overtime_approved WHERE approved_hours<0 OR lower(request_status)<>'approved') +
                     (SELECT COUNT(*) FROM fact_payroll_line WHERE amount<0)"""
            ).fetchone()[0]
            record("business_sanity_nonnegative", "warehouse_facts", sanity,
                   "worked/approved OT hours and payroll amounts must be nonnegative")

            count_checks = [
                ("attendance_fact_reconciles_to_stage",
                 conn.execute("SELECT COUNT(*) FROM fact_attendance_daily").fetchone()[0],
                 csv_rows(ATTENDANCE / "attendance_daily.csv")),
                ("payroll_fact_reconciles_to_stage",
                 conn.execute("SELECT COUNT(*) FROM fact_payroll_line").fetchone()[0],
                 csv_rows(STAGING / "payroll_lines_clean.csv")),
            ]
            for name, actual, expected in count_checks:
                record(name, "warehouse", abs(actual - expected), f"warehouse={actual}; staging={expected}")

            conn.execute("DROP TABLE IF EXISTS dq_results")
            conn.execute("""CREATE TABLE dq_results(
                dq_id INTEGER PRIMARY KEY, check_name TEXT NOT NULL, table_name TEXT NOT NULL,
                failed_rows INTEGER NOT NULL, status TEXT NOT NULL CHECK(status IN ('PASS','FAIL','INFO')),
                details TEXT, checked_at TEXT NOT NULL
            )""")
            conn.executemany(
                "INSERT INTO dq_results(check_name,table_name,failed_rows,status,details,checked_at) "
                "VALUES(?,?,?,?,?,?)",
                [(r["check_name"], r["table_name"], r["failed_rows"], r["status"],
                  r["details"], r["checked_at"]) for r in results],
            )
            conn.commit()

    pd.DataFrame(results).to_csv(LOG, index=False)
    failed = sum(row["status"] == "FAIL" for row in results)
    print(f"Quality checks written to {LOG}: {len(results) - failed}/{len(results)} passed")
    for row in results:
        print(f"{row['status']}: {row['check_name']} ({row['table_name']}) - {row['details']}")
    if failed:
        raise RuntimeError(f"{failed} data-quality check(s) failed; see {LOG}")


if __name__ == "__main__":
    main()
