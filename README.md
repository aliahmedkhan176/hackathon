# PeopleOps HR Pipeline — Complete Case Study Project

A reproducible Python + SQLite implementation for the supplied **PeopleOps Data Hackathon: HR Pipeline Case Study**. The supplied synthetic data is included under `data/raw/`.

## Start here

- **Dashboard:** open `web/dashboard.html` in Chrome, Edge or Firefox. It is a self-contained responsive page with inline CSS/JavaScript and embedded results; it does not require internet access or a web server.
- **Presentation:** `presentation/PeopleOps_HR_Pipeline_Results.pptx`
- **Findings:** `presentation/cfo_findings.md`
- **Build status and caveats:** `PROJECT_STATUS.md`
- **Database:** `indus_weave.db`

## Requirements

- Python 3.10 or newer
- Dependencies listed in `requirements.txt` (`pandas`, `python-pptx`)
- SQLite is included with Python

## Rebuild the pipeline

From the project root:

```bash
pip install -r requirements.txt
python run_pipeline.py
```

The pipeline loads raw files idempotently, runs source checks, creates cleaned staging CSVs, reconstructs employee-day attendance, rebuilds the constrained SQLite warehouse, executes the 10 SQL analytics queries, builds the recruitment-funnel bonus output, refreshes the CFO findings/dashboard/six-slide deck, copies the dashboard and deck to `../deliverables/`, and runs the project acceptance tests. The SQLite database and high-volume intermediate staging/attendance CSVs are generated locally and intentionally excluded from Git; the included raw sources and one-command pipeline rebuild them. The full rebuild can take several minutes because the biometric file contains 345,280 events. Run `python tests/validate_project.py` separately whenever you want to rerun the acceptance checks.

## Main folders

- `data/raw/` — all source CSV/JSON files and the data dictionary
- `ingestion/` — raw ingestion and source profiling
- `quality/` — raw data checks
- `transform/` — cleaning, deduplication and staging
- `attendance/` — shift-date attendance and overtime reconstruction
- `warehouse/` — SQLite star-schema build and ERD notes
- `analytics/` — ten executable SQL queries and runner
- `results/staging/` — cleaned data, punch audits and leave-day output
- `results/attendance/` — daily attendance and monthly rollups
- `results/analytics/` — query result CSVs, query test results and dashboard JSON
- `web/` — dashboard builder and self-contained dashboard HTML
- `presentation/` — executive deck, findings and slide outline
- `tests/` — post-build validation checks
- `../deliverables/` — ready-to-submit dashboard and six-slide PowerPoint deck
- `warehouse/erd.svg` — rendered entity-relationship diagram for the warehouse

## Business-rule implementation notes

- Employee duplicates: keep the latest `updated_at` per `emp_id`.
- Employment history: derive effective intervals from successive `effective_from` dates.
- Roster week: Monday–Sunday; missing weeks carry forward the previous known shift.
- Punch mapping: composite `device_id + device_user_id`; unmapped punches are retained in a rejected audit.
- Duplicate punches: compare against the previous retained punch per employee; events within 120 seconds are removed.
- Night shift: early-morning check-outs are assigned to the date the shift started.
- Attendance status: Sunday without punches → Weekly Off; scoped holiday without punches → Holiday; approved leave → On Leave; two or more punches → Present; one punch → Missing Punch; otherwise Absent.
- Late/early: ten-minute grace; counted on Present working days only.
- Overtime: rounded down to half-hour increments; Sunday/holiday work is all overtime.
- Leave: Manager and HR must both approve and `cancelled_at` must be empty; Sundays and scoped holidays are excluded from leave days.
- Payroll cost: sum of `EARNING` components; paid overtime hours are the `OVERTIME` line's `units`.

## Important interpretation cautions

- The dataset dictionary describes all people and values as synthetic.
- The pipeline detects `DEV-SITE-01` running +60 minutes from 1 July 2026 onward based on its shift-boundary peaks moving from 06/14/22 to 07/15/23 with 00:xx spillover. It subtracts 60 minutes for affected staging timestamps, preserves raw times, and writes a correction audit.
- Punch-computed overtime is an estimate. The difference from approved/paid hours is a review signal, not proof of an error.
- `q06_paid_ot_exceeds_computed.sql` compares hours to hours. A zero-row result means no department-month crossed the specified 15% threshold; it does not certify every individual payment.
- Query outputs are generated from the included dataset and the stated rules. There is no answer key in the supplied files, so findings should be treated as evidence-based review flags rather than official hackathon scoring.
- The employment history includes a same-day duplicate for one employee. Stage 2 keeps the last source row for each employee/effective date, writes the discarded row to `employment_history_dedup_audit.csv`, and reconciles both rows to the raw count.
- The full automated DQ report is `logs/dq_results.csv` and the corresponding SQLite `dq_results` table. A passing build records primary/foreign-key, raw-to-stage, accepted-value, SCD2 and business-sanity checks.
