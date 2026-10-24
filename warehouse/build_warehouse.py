"""Build a small star-schema warehouse in SQLite from cleaned/staged data."""
from pathlib import Path
import sqlite3, pandas as pd, json
ROOT=Path(__file__).resolve().parents[1]; ST=ROOT/'results/staging'; AT=ROOT/'results/attendance'; DB=ROOT/'indus_weave.db'
def rd(folder,name): return pd.read_csv(folder/f'{name}.csv',keep_default_na=False)
def main():
 emp=rd(ST,'employees_clean'); hist=rd(ST,'employment_history_clean'); depts=rd(ST,'departments_clean'); daily=rd(AT,'attendance_daily'); leaves=rd(ST,'approved_leave_days'); ot=rd(ST,'overtime_requests_clean'); pay=rd(ST,'payroll_lines_clean'); hol=rd(ST,'holidays_clean')
 for c in ['hire_date','separation_date']: emp[c]=pd.to_datetime(emp[c],errors='coerce')
 for c in ['effective_from','effective_to']: hist[c]=pd.to_datetime(hist[c],errors='coerce')
 with sqlite3.connect(DB) as con:
  con.execute('PRAGMA foreign_keys=ON')
  for t in ['fact_attendance_daily','fact_leave_day','fact_overtime_approved','fact_payroll_line','dim_employee','dim_department','dim_shift','dim_date','dq_results','staging_monthly_headcount','staging_separations','staging_employee_entitlement','staging_overtime_reconciliation']:
   con.execute(f'DROP TABLE IF EXISTS {t}')
  con.executescript('''
  CREATE TABLE dim_department(department_key INTEGER PRIMARY KEY,department_id TEXT NOT NULL UNIQUE,department_name TEXT NOT NULL,plant_name TEXT NOT NULL,cost_center TEXT);
  CREATE TABLE dim_shift(shift_key INTEGER PRIMARY KEY,shift_id TEXT NOT NULL UNIQUE,shift_name TEXT NOT NULL,start_time TEXT NOT NULL,end_time TEXT NOT NULL,crosses_midnight INTEGER NOT NULL CHECK(crosses_midnight IN (0,1)),grace_minutes INTEGER NOT NULL CHECK(grace_minutes>=0));
  CREATE TABLE dim_date(date_key INTEGER PRIMARY KEY,full_date TEXT NOT NULL UNIQUE,year INTEGER NOT NULL,month INTEGER NOT NULL,day INTEGER NOT NULL,month_start TEXT NOT NULL,month_end TEXT NOT NULL,is_sunday INTEGER NOT NULL CHECK(is_sunday IN (0,1)),is_holiday INTEGER NOT NULL CHECK(is_holiday IN (0,1)));
  CREATE TABLE dim_employee(employee_key INTEGER PRIMARY KEY,emp_id TEXT NOT NULL,employee_name TEXT NOT NULL,department_key INTEGER NOT NULL,job_title TEXT,grade TEXT,employment_status TEXT,valid_from TEXT NOT NULL,valid_to TEXT NOT NULL,is_current INTEGER NOT NULL CHECK(is_current IN (0,1)),annual_leave_entitlement_days INTEGER NOT NULL CHECK(annual_leave_entitlement_days>=0),hire_date TEXT,separation_date TEXT,UNIQUE(emp_id,valid_from),CHECK(valid_from<=valid_to),FOREIGN KEY(department_key) REFERENCES dim_department(department_key));
  CREATE INDEX ix_dim_employee_asof ON dim_employee(emp_id,valid_from,valid_to);
  CREATE TABLE fact_attendance_daily(attendance_key INTEGER PRIMARY KEY,emp_id TEXT NOT NULL,date_key INTEGER NOT NULL,employee_key INTEGER NOT NULL,shift_key INTEGER,status TEXT NOT NULL CHECK(status IN ('Present','Absent','On Leave','Holiday','Weekly Off','Missing Punch')),check_in TEXT,check_out TEXT,worked_hours REAL NOT NULL CHECK(worked_hours>=0),late_minutes INTEGER NOT NULL CHECK(late_minutes>=0),early_departure_minutes INTEGER NOT NULL CHECK(early_departure_minutes>=0),computed_overtime_hours REAL NOT NULL CHECK(computed_overtime_hours>=0),UNIQUE(emp_id,date_key),FOREIGN KEY(date_key) REFERENCES dim_date(date_key),FOREIGN KEY(employee_key) REFERENCES dim_employee(employee_key),FOREIGN KEY(shift_key) REFERENCES dim_shift(shift_key));
  CREATE TABLE fact_leave_day(leave_day_key INTEGER PRIMARY KEY,emp_id TEXT NOT NULL,employee_key INTEGER NOT NULL,date_key INTEGER NOT NULL,leave_type TEXT NOT NULL,request_id TEXT,FOREIGN KEY(employee_key) REFERENCES dim_employee(employee_key),FOREIGN KEY(date_key) REFERENCES dim_date(date_key));
  CREATE TABLE fact_overtime_approved(overtime_key INTEGER PRIMARY KEY,emp_id TEXT NOT NULL,employee_key INTEGER NOT NULL,date_key INTEGER NOT NULL,approved_hours REAL NOT NULL CHECK(approved_hours>=0),request_status TEXT NOT NULL CHECK(lower(request_status)='approved'),FOREIGN KEY(employee_key) REFERENCES dim_employee(employee_key),FOREIGN KEY(date_key) REFERENCES dim_date(date_key));
  CREATE TABLE fact_payroll_line(payroll_line_key INTEGER PRIMARY KEY,emp_id TEXT NOT NULL,employee_key INTEGER NOT NULL,month_start TEXT NOT NULL,department_key INTEGER NOT NULL,pay_component TEXT NOT NULL,component_type TEXT NOT NULL,units REAL,amount REAL NOT NULL CHECK(amount>=0),FOREIGN KEY(employee_key) REFERENCES dim_employee(employee_key),FOREIGN KEY(department_key) REFERENCES dim_department(department_key));
  CREATE TABLE dq_results(dq_id INTEGER PRIMARY KEY,check_name TEXT,table_name TEXT,failed_rows INTEGER,status TEXT,details TEXT,checked_at TEXT DEFAULT CURRENT_TIMESTAMP);
  CREATE TABLE staging_monthly_headcount(month_start TEXT,department_name TEXT,opening_headcount INTEGER,closing_headcount INTEGER);
  CREATE TABLE staging_separations(emp_id TEXT,department_name TEXT,month_start TEXT,separation_date TEXT);
  CREATE TABLE staging_employee_entitlement(emp_id TEXT,annual_leave_entitlement_days INTEGER);
  CREATE TABLE staging_overtime_reconciliation(month TEXT,department_name TEXT,computed_overtime_value REAL,paid_overtime_value REAL,computed_hours REAL,approved_hours REAL,paid_hours REAL);
  ''')
  drows=[(i+1,r.dept_id,r.dept_name,r.plant,r.cost_center) for i,r in enumerate(depts.itertuples(index=False))]
  con.executemany('INSERT INTO dim_department VALUES(?,?,?,?,?)',drows); deptkey={r[1]:r[0] for r in drows}
  shifts=json.loads((ROOT/'data/raw/shifts.json').read_text())['shifts']
  con.executemany('INSERT INTO dim_shift VALUES(?,?,?,?,?,?,?)',[(i+1,s['shift_code'],s['name'],s['start_time'],s['end_time'],int(s['crosses_midnight']),s['grace_minutes']) for i,s in enumerate(shifts)])
  holidays_bydate={}
  for h in hol.itertuples(index=False): holidays_bydate.setdefault(h.holiday_date,[]).append(h.scope)
  dates=pd.date_range('2026-04-01','2026-09-30',freq='D'); date_rows=[]
  for d in dates:
   ds=d.strftime('%Y-%m-%d'); scopes=holidays_bydate.get(ds,[]); date_rows.append((int(ds.replace('-','')),ds,d.year,d.month,d.day,d.replace(day=1).strftime('%Y-%m-%d'),(d+pd.offsets.MonthEnd(0)).strftime('%Y-%m-%d'),int(d.weekday()==6),int(bool(scopes))))
  con.executemany('INSERT INTO dim_date VALUES(?,?,?,?,?,?,?,?,?)',date_rows)
  emp_lookup=emp.set_index('emp_id').to_dict('index'); versions=[]; key_for=[]; k=1
  for eid,g in hist.sort_values(['emp_id','effective_from']).groupby('emp_id'):
   ee=emp_lookup.get(eid,{})
   for _,h in g.iterrows():
    start=pd.to_datetime(h.effective_from); end=pd.to_datetime(h.effective_to,errors='coerce')
    if pd.isna(end): end=pd.Timestamp('2262-04-11')
    versions.append((k,eid,ee.get('full_name',''),deptkey.get(h.dept_id),h.designation,h.grade,ee.get('status',''),start.strftime('%Y-%m-%d'),end.strftime('%Y-%m-%d'),int(end.year>=2262),int(float(ee.get('annual_leave_entitlement',0) or 0)),str(ee.get('hire_date',''))[:10],str(ee.get('separation_date',''))[:10] if pd.notna(ee.get('separation_date')) else ''))
    key_for.append((eid,start,end,k)); k+=1
  con.executemany('INSERT INTO dim_employee VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',versions)
  key_by_emp={}
  for ee,ss,eeend,kk in key_for: key_by_emp.setdefault(ee,[]).append((ss,eeend,kk))
  def empkey(eid,day):
   for ss,eeend,kk in key_by_emp.get(eid,[]):
    if ss<=day<=eeend:return kk
   return None
  print('employee versions',len(versions),'building attendance facts',flush=True)
  shiftkey={s['shift_code']:i+1 for i,s in enumerate(shifts)}
  rows=[]
  for r in daily.itertuples(index=False):
   day=pd.Timestamp(r.attendance_date); ek=empkey(r.emp_id,day)
   if ek: rows.append((r.emp_id,int(day.strftime('%Y%m%d')),ek,shiftkey.get(r.shift_code),r.status,r.check_in or None,r.check_out or None,float(r.worked_hours),int(r.late_minutes),int(r.early_departure_minutes),float(r.computed_overtime_hours)))
  print('attendance fact rows prepared',len(rows),flush=True)
  con.executemany('INSERT INTO fact_attendance_daily(emp_id,date_key,employee_key,shift_key,status,check_in,check_out,worked_hours,late_minutes,early_departure_minutes,computed_overtime_hours) VALUES(?,?,?,?,?,?,?,?,?,?,?)',rows)
  leave_rows=[]
  for r in leaves.itertuples(index=False):
   if r.leave_date:
    ek=empkey(r.emp_id,pd.Timestamp(r.leave_date))
    if ek is None: raise ValueError(f'No employee SCD version for leave day {r.emp_id} {r.leave_date}')
    leave_rows.append((r.emp_id,ek,int(r.leave_date.replace('-','')),r.leave_type,r.request_id))
  con.executemany('INSERT INTO fact_leave_day(emp_id,employee_key,date_key,leave_type,request_id) VALUES(?,?,?,?,?)',leave_rows)
  overtime_rows=[]
  for r in ot.itertuples(index=False):
   if r.ot_date and r.status.strip().lower()=='approved':
    ek=empkey(r.emp_id,pd.Timestamp(r.ot_date))
    if ek is None: raise ValueError(f'No employee SCD version for overtime date {r.emp_id} {r.ot_date}')
    overtime_rows.append((r.emp_id,ek,int(r.ot_date.replace('-','')),float(r.approved_hours or 0),r.status))
  con.executemany('INSERT INTO fact_overtime_approved(emp_id,employee_key,date_key,approved_hours,request_status) VALUES(?,?,?,?,?)',overtime_rows)
  hgroups={eid:g.sort_values('effective_from') for eid,g in hist.groupby('emp_id')}; hist_intervals={eid:[(r.effective_from,r.effective_to,r.dept_id) for r in g.itertuples(index=False)] for eid,g in hgroups.items()}; p_rows=[]
  def dept_at(eid,asof):
   for hs,he,hd in hist_intervals.get(eid,[]):
    if hs<=asof and (pd.isna(he) or he>=asof): return hd
    if hs>asof: break
   return ''
  for r in pay.itertuples(index=False):
   month=f'{r.payroll_month}-01'; month_end=pd.Timestamp(month)+pd.offsets.MonthEnd(0); ee=emp_lookup.get(r.emp_id,{}); sep=ee.get('separation_date'); asof=min(month_end,sep) if pd.notna(sep) else month_end; deptid=dept_at(r.emp_id,asof)
   employee_key=empkey(r.emp_id,asof)
   if employee_key is None: raise ValueError(f'No employee SCD version for payroll month {r.emp_id} {month}')
   department_key=deptkey.get(deptid)
   if department_key is None: raise ValueError(f'No department for payroll month {r.emp_id} {month}')
   p_rows.append((r.emp_id,employee_key,month,department_key,r.component,r.component_type,float(r.units) if str(r.units).strip() not in ('','nan') else None,float(r.amount or 0)))
  con.executemany('INSERT INTO fact_payroll_line(emp_id,employee_key,month_start,department_key,pay_component,component_type,units,amount) VALUES(?,?,?,?,?,?,?,?)',p_rows)
  print('payroll rows prepared',len(p_rows),flush=True)
  # Separation and leave entitlement helper tables
  for e in emp.itertuples(index=False):
   con.execute('INSERT INTO staging_employee_entitlement VALUES(?,?)',(e.emp_id,int(e.annual_leave_entitlement or 0)))
   if pd.notna(e.separation_date):
    sep=e.separation_date; month=sep.strftime('%Y-%m-01'); dep=''; hg=hgroups.get(e.emp_id)
    if hg is not None:
     q=hg[(hg.effective_from<=sep)&((hg.effective_to.isna())|(hg.effective_to>=sep))]
     if len(q): dep=q.iloc[-1].dept_id
    dname=next((x.dept_name for x in depts.itertuples(index=False) if x.dept_id==dep),'Unknown')
    con.execute('INSERT INTO staging_separations VALUES(?,?,?,?)',(e.emp_id,dname,month,sep.strftime('%Y-%m-%d')))
  # Monthly headcount snapshots using active employment dates; department is resolved through history for each employee/date.
  # Build per-employee interval lists once and perform lightweight date lookups.
  hist_intervals={}
  for eid,g in hist.sort_values(['emp_id','effective_from']).groupby('emp_id'):
   hist_intervals[eid]=[(r.effective_from,r.effective_to,r.dept_id) for r in g.itertuples(index=False)]
  emp_rows=list(emp.itertuples(index=False))
  for m in pd.date_range('2026-04-01','2026-09-01',freq='MS'):
   for label,asof in [('opening',m-pd.Timedelta(days=1)),('closing',m+pd.offsets.MonthEnd(0))]:
    cnt={}
    for e in emp_rows:
     if pd.isna(e.hire_date) or e.hire_date>asof or (pd.notna(e.separation_date) and e.separation_date<=asof): continue
     dep=''
     for hs,he,hd in hist_intervals.get(e.emp_id,[]):
      if hs<=asof and (pd.isna(he) or he>=asof): dep=hd
      elif hs>asof: break
     cnt[dep]=cnt.get(dep,0)+1
    if label=='opening': opening_counts=cnt
    else:
     for dept in depts.itertuples(index=False):
      opening=opening_counts.get(dept.dept_id,0); closing=cnt.get(dept.dept_id,0)
      if opening or closing: con.execute('INSERT INTO staging_monthly_headcount VALUES(?,?,?,?)',(m.strftime('%Y-%m-%d'),dept.dept_name,opening,closing))
  print('headcount done',flush=True)
  # Reconciliation helper uses HOURS for a valid like-for-like comparison.
  att_agg=pd.read_sql_query("SELECT substr(dt.full_date,1,7) month,d.department_name,SUM(a.computed_overtime_hours) computed_hours FROM fact_attendance_daily a JOIN dim_date dt ON dt.date_key=a.date_key JOIN dim_employee e ON e.employee_key=a.employee_key JOIN dim_department d ON d.department_key=e.department_key GROUP BY month,d.department_name",con)
  approved_agg=pd.read_sql_query("SELECT substr(dt.full_date,1,7) month,d.department_name,SUM(o.approved_hours) approved_hours FROM fact_overtime_approved o JOIN dim_date dt ON dt.date_key=o.date_key JOIN dim_employee e ON e.emp_id=o.emp_id JOIN dim_department d ON d.department_key=e.department_key GROUP BY month,d.department_name",con)
  paid_agg=pd.read_sql_query("SELECT substr(p.month_start,1,7) month,d.department_name,SUM(p.units) paid_hours FROM fact_payroll_line p JOIN dim_department d ON d.department_key=p.department_key WHERE upper(p.pay_component)='OVERTIME' GROUP BY month,d.department_name",con)
  rec=att_agg.merge(approved_agg,on=['month','department_name'],how='outer').merge(paid_agg,on=['month','department_name'],how='outer').fillna(0)
  con.executemany('INSERT INTO staging_overtime_reconciliation VALUES(?,?,?,?,?,?,?)',[(r.month,r.department_name,float(r.computed_hours),float(r.paid_hours),float(r.computed_hours),float(r.approved_hours),float(r.paid_hours)) for r in rec.itertuples(index=False)])
  checks=[('attendance_nonnegative_hours','fact_attendance_daily',con.execute('SELECT count(*) FROM fact_attendance_daily WHERE worked_hours<0 OR computed_overtime_hours<0').fetchone()[0]),('duplicate_employee_date','fact_attendance_daily',con.execute('SELECT count(*) FROM (SELECT emp_id,date_key,count(*) n FROM fact_attendance_daily GROUP BY emp_id,date_key HAVING n>1)').fetchone()[0]),('payroll_nonnegative_amount','fact_payroll_line',con.execute('SELECT count(*) FROM fact_payroll_line WHERE amount<0').fetchone()[0])]
  con.executemany('INSERT INTO dq_results(check_name,table_name,failed_rows,status,details) VALUES(?,?,?,?,?)',[(n,t,f,'PASS' if f==0 else 'FAIL','Automated post-build validation') for n,t,f in checks])
  print('Warehouse built:',len(rows),'attendance facts,',len(p_rows),'payroll lines; DQ',checks)
if __name__=='__main__': main()
