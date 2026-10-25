# CFO findings — Indus Weave Textiles

Reporting window: 1 April–30 September 2026. All amounts are PKR; all data is synthetic.
These are review signals, not findings of misconduct.

## Top three findings

1. **Punch-computed overtime materially exceeds approved and paid hours.** The pipeline estimates **133,718.5 hours** from biometric punches, compared with **36,401.5 approved** and **36,401.5 paid** hours—a **97,317.0-hour** gap between computed and paid. Evidence: [`q05_overtime_reconciliation.csv`](../results/analytics/q05_overtime_reconciliation.csv), grouped by month and department. Action: reconcile employee + shift-date records, then verify approvals, punch pairs and payroll cutoffs; computed hours are an estimate, not a liability conclusion.

2. **Single-punch days create a substantial attendance review queue.** **26,592** employee-days are classified `Missing Punch`. Evidence: [`review_missing_punches.csv`](../results/analytics/review_missing_punches.csv) breaks them down by month, plant and department. Action: investigate repeated device/employee patterns, gateway uptime and enrollment before making attendance adjustments.

3. **Post-separation earnings require employee-level validation.** **21** employee-months have positive EARNING lines after the separation month. Evidence: [`q08_paid_after_separation.csv`](../results/analytics/q08_paid_after_separation.csv). Payroll is monthly, so the separation month itself is not enough to prove payment occurred after the last day worked. Action: check final-pay policy and payroll cutoff before escalation.

## Additional indicators

- 59 paid employee-months have zero days classified Present; approved leave, separation, paid absence and data-feed gaps may explain these.
- 20 employees exceed full-year annual leave entitlement during the six-month window; confirm carry-over and balance rules.
- Six-month payroll EARNING components total **PKR 695,019,178**.

## Controls and caveats

- Device clock correction is restricted to the evidenced `DEV-SITE-01` +60-minute offset from 1 July 2026; raw events are preserved and corrections are auditable.
- Payroll cost uses `EARNING` lines only; paid overtime hours use the `OVERTIME` line's `units`.
- Approved overtime requests and computed overtime from punch boundaries are separate measures and need not match exactly.
- The hidden answer key was not supplied, so these results are reproducible, evidence-based outputs—not independently certified scoring answers.
