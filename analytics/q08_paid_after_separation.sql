-- Generated executable query. Run with SQLite against indus_weave.db.
SELECT p.emp_id,p.month_start,s.separation_date,p.pay_component,p.amount FROM fact_payroll_line p JOIN staging_separations s ON s.emp_id=p.emp_id WHERE date(p.month_start)>date(s.separation_date,'start of month') AND p.amount<>0 ORDER BY p.emp_id,p.month_start;
