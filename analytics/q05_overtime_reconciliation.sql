-- Generated executable query. Run with SQLite against indus_weave.db.
-- Computed and approved OT are attributed to the employee month-end department, or last-working-day department after separation; paid OT is grouped by payroll department. Values are hours.
SELECT month,department_name,ROUND(computed_hours,2) computed_hours,ROUND(approved_hours,2) approved_hours,ROUND(paid_hours,2) paid_hours,ROUND(paid_hours-computed_hours,2) paid_minus_computed_hours FROM staging_overtime_reconciliation ORDER BY month,department_name;
