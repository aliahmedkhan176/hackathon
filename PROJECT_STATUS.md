# Project status

## Rebuilt and verified components
- All 12 source CSV/JSON files and the data dictionary are included in `data/raw/`; raw data remains unchanged by the pipeline.
- Idempotent raw ingestion stores source filename, load timestamp and a unique row hash.
- Stage 2 outputs include deduplicated employees, same-day employment-history resolution, leave approval flattening, mapped/rejected punches, duplicate-punch audit and device-clock correction audit.
- Attendance reconstructed for 1 April–30 September 2026 with the case-study roster, night-shift, status, late/early and overtime rules.
- SQLite star schema enforces primary/foreign keys, accepted attendance statuses and basic nonnegative-value constraints.
- Ten scored SQL queries execute and save their result CSVs; the optional recruitment funnel bonus output is generated.
- Automated DQ checks cover raw metadata, source-to-staging row reconciliation, warehouse keys/FKs, allowed values, SCD2 overlap, shift duration and business sanity.
- Dashboard, CFO findings and a six-slide presentation are generated from the rebuilt warehouse. The two submission-ready files are copied to `../deliverables/`.
- A rendered SVG ER diagram is included at `warehouse/erd.svg`.
- `python run_pipeline.py` ends by running the project acceptance tests.

## Verified snapshot
- 12 raw input tables, including 345,280 biometric events and 53,617 payroll lines.
- 1,266 unique employees; 217,584 employee-day attendance records.
- Attendance: 146,865 Present; 4,744 Absent; 26,592 Missing Punch; 8,604 On Leave; 21,998 Weekly Off; 8,781 Holiday.
- Punch-computed OT: 133,718.5 hours; approved OT: 36,401.5 hours; paid OT: 36,401.5 hours.
- Payroll EARNING components: PKR 695,019,178.
- All ten scored analytics queries passed; all generated DQ checks passed; all 20 project acceptance tests passed.

## Important interpretation notes
- The dataset is synthetic, as stated in the supplied data dictionary.
- The source employment history contains two rows for one employee on the same effective date. Stage 2 keeps the last source row for that date and preserves the discarded row in `results/staging/employment_history_dedup_audit.csv`.
- The `DEV-SITE-01` clock shift from July 2026 was identified from the change in punch peaks (06/14/22 to 07/15/23 with 00:xx spillover). A -60-minute correction is applied to its July–September staging timestamps, with raw times preserved.
- `computed_overtime_hours` is a punch-based estimate. Approved requests and payroll-paid OT are separate controls; their difference is a review signal, not proof of error.
- The annual-leave query compares six-month approved usage with the full-year entitlement, as specified by the case study.
- Q6 compares overtime hours to hours. A zero-row result under the 15% rule does not certify every individual payment.
- The case-study hidden answer key was not supplied, so query results are reproducible and evidence-based but cannot be certified against official scoring answers.

## Rebuild
From this folder:

```bash
pip install -r requirements.txt
python run_pipeline.py
```

Python 3.10+, pandas, python-pptx and the SQLite library bundled with Python are required. The dashboard is static and does not need a web server.
