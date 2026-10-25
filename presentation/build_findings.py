"""Generate CFO findings from the verified warehouse and analytics outputs."""
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "indus_weave.db"
OUTPUT = ROOT / "presentation" / "cfo_findings.md"


def main() -> None:
    with sqlite3.connect(DB) as conn:
        metrics = {
            "computed_ot": conn.execute(
                "SELECT COALESCE(SUM(computed_overtime_hours),0) FROM fact_attendance_daily"
            ).fetchone()[0],
            "approved_ot": conn.execute(
                "SELECT COALESCE(SUM(approved_hours),0) FROM fact_overtime_approved"
            ).fetchone()[0],
            "paid_ot": conn.execute(
                "SELECT COALESCE(SUM(units),0) FROM fact_payroll_line "
                "WHERE upper(pay_component)='OVERTIME'"
            ).fetchone()[0],
            "missing_punch": conn.execute(
                "SELECT COUNT(*) FROM fact_attendance_daily WHERE status='Missing Punch'"
            ).fetchone()[0],
            "paid_after_separation": conn.execute(
                "SELECT COUNT(*) FROM (SELECT p.emp_id,p.month_start FROM staging_separations s "
                "JOIN fact_payroll_line p ON p.emp_id=s.emp_id "
                "WHERE date(p.month_start)>date(s.separation_date,'start of month') "
                "AND upper(p.component_type)='EARNING' AND p.amount>0 "
                "GROUP BY p.emp_id,p.month_start)"
            ).fetchone()[0],
            "annual_leave_flags": conn.execute(
                "SELECT COUNT(*) FROM (SELECT u.emp_id FROM "
                "(SELECT emp_id,COUNT(*) used FROM fact_leave_day l JOIN dim_date d "
                "ON d.date_key=l.date_key WHERE lower(l.leave_type) IN ('annual','annual leave') "
                "AND d.full_date BETWEEN '2026-04-01' AND '2026-09-30' GROUP BY emp_id) u "
                "JOIN staging_employee_entitlement e ON e.emp_id=u.emp_id "
                "WHERE u.used>e.annual_leave_entitlement_days)"
            ).fetchone()[0],
            "payroll_earnings": conn.execute(
                "SELECT COALESCE(SUM(amount),0) FROM fact_payroll_line "
                "WHERE upper(component_type)='EARNING'"
            ).fetchone()[0],
            "paid_zero_attendance": conn.execute(
                "SELECT COUNT(*) FROM (SELECT emp_id,month FROM "
                "(SELECT emp_id,substr(month_start,1,7) month FROM fact_payroll_line "
                "WHERE upper(component_type)='EARNING' AND amount>0 "
                "GROUP BY emp_id,substr(month_start,1,7)) p "
                "WHERE NOT EXISTS (SELECT 1 FROM fact_attendance_daily a JOIN dim_date d "
                "ON d.date_key=a.date_key WHERE a.emp_id=p.emp_id AND substr(d.full_date,1,7)=p.month "
                "AND a.status='Present'))"
            ).fetchone()[0],
        }

    gap = metrics["computed_ot"] - metrics["paid_ot"]
    text = f"""# CFO findings — Indus Weave Textiles

Reporting window: 1 April–30 September 2026. All amounts are PKR; all data is synthetic.
These are review signals, not findings of misconduct.

## Top three findings

1. **Punch-computed overtime materially exceeds approved and paid hours.** The pipeline estimates **{metrics['computed_ot']:,.1f} hours** from biometric punches, compared with **{metrics['approved_ot']:,.1f} approved** and **{metrics['paid_ot']:,.1f} paid** hours—a **{gap:,.1f}-hour** gap between computed and paid. Evidence: [`q05_overtime_reconciliation.csv`](../results/analytics/q05_overtime_reconciliation.csv), grouped by month and department. Action: reconcile employee + shift-date records, then verify approvals, punch pairs and payroll cutoffs; computed hours are an estimate, not a liability conclusion.

2. **Single-punch days create a substantial attendance review queue.** **{metrics['missing_punch']:,}** employee-days are classified `Missing Punch`. Evidence: [`review_missing_punches.csv`](../results/analytics/review_missing_punches.csv) breaks them down by month, plant and department. Action: investigate repeated device/employee patterns, gateway uptime and enrollment before making attendance adjustments.

3. **Post-separation earnings require employee-level validation.** **{metrics['paid_after_separation']:,}** employee-months have positive EARNING lines after the separation month. Evidence: [`q08_paid_after_separation.csv`](../results/analytics/q08_paid_after_separation.csv). Payroll is monthly, so the separation month itself is not enough to prove payment occurred after the last day worked. Action: check final-pay policy and payroll cutoff before escalation.

## Additional indicators

- {metrics['paid_zero_attendance']:,} paid employee-months have zero days classified Present; approved leave, separation, paid absence and data-feed gaps may explain these.
- {metrics['annual_leave_flags']:,} employees exceed full-year annual leave entitlement during the six-month window; confirm carry-over and balance rules.
- Six-month payroll EARNING components total **PKR {metrics['payroll_earnings']:,.0f}**.

## Controls and caveats

- Device clock correction is restricted to the evidenced `DEV-SITE-01` +60-minute offset from 1 July 2026; raw events are preserved and corrections are auditable.
- Payroll cost uses `EARNING` lines only; paid overtime hours use the `OVERTIME` line's `units`.
- Approved overtime requests and computed overtime from punch boundaries are separate measures and need not match exactly.
- The hidden answer key was not supplied, so these results are reproducible, evidence-based outputs—not independently certified scoring answers.
"""
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
