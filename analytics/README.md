# Analytics query notes

There is one SQLite SQL file per scored question. The pipeline builds the required helper staging tables (`staging_separations`, `staging_overtime_reconciliation`, and `staging_employee_entitlement`), executes each query, saves one CSV per question under `results/analytics/`, and writes `query_test_results.csv`.

Run from the project root with `python run_pipeline.py`. The separate `review_missing_punches.sql` and its CSV provide additional evidence for the CFO findings; they are supplemental and not an eleventh scored question. `build_recruitment_funnel.py` writes the optional bonus output. The SQLite query runner and automated acceptance checks verify outputs against the included synthetic data; there is no hidden answer key in the repository.

Question interpretation notes are recorded in SQL comments. In particular, Q5/Q6 assign computed and approved overtime to the employee's department at month-end (or last working day in a separation month); Q7 counts positive EARNING payroll only and defines zero attendance as zero Present days; Q8 reports positive EARNING totals by employee-month strictly after the separation month because monthly payroll cannot establish payment timing within the separation month.
