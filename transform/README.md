# Stage 2 — Cleaning and standardization

Run from the project root:

```bash
python transform/stage2_clean.py
```

The script reads only `data/raw/`; it never edits the raw files. It creates auditable outputs in `results/staging/` and a stage report in `results/profiling/stage2_report.csv`, and replaces SQLite tables named `stg_*` in `indus_weave.db`.

Implemented:
- trims text and normalizes IDs/status labels;
- parses the three employee date formats to ISO dates;
- canonicalizes department aliases using `departments.csv` names and `previous_name`;
- keeps the employee row with the latest `updated_at`, with `employee_dedup_audit.csv` as an audit trail;
- reconstructs employment-history end dates from the next effective start;
- maps punches on the required `(device_id, device_user_id)` key;
- preserves unmapped punches in `rejected_punches.csv` with a reason;
- removes repeated employee punches within 120 seconds of the previous retained punch and logs them;
- flattens leave requests and approval steps, and expands eligible leave requests to dates, excluding Sundays and applicable holidays;
- profiles punch time-of-day per device;
- detects the `DEV-SITE-01` +60-minute drift beginning 1 July 2026 from the shift-boundary distribution and corrects affected staging timestamps by subtracting 60 minutes; raw source files remain unchanged;
- records every corrected punch in `punch_clock_correction_audit.csv` and the correction decision in `device_clock_corrections.csv`.

The clock correction is evidence-based: April–June peaks align around 06:00/14:00/22:00, while July–September shift to 07:00/15:00/23:00 with 00:xx spillover. The correction is applied only to `DEV-SITE-01` events timestamped from 1 July 2026 onward.
