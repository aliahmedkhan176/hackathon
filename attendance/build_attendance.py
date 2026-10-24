"""Vectorized attendance reconstruction using the case-study rules."""
from pathlib import Path
import json, sqlite3
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]; ST=ROOT/'results/staging'; OUT=ROOT/'results/attendance'; OUT.mkdir(parents=True,exist_ok=True); DB=ROOT/'indus_weave.db'
START=pd.Timestamp('2026-04-01'); END=pd.Timestamp('2026-09-30')
def csv(name): return pd.read_csv(ST/f'{name}.csv',keep_default_na=False)
def main():
 emp=csv('employees_clean'); hist=csv('employment_history_clean'); depts=csv('departments_clean'); roster=csv('shift_roster_clean'); punches=csv('biometric_punches_mapped_deduped'); hol=csv('holidays_clean'); leaves=csv('approved_leave_days')
 for c in ['hire_date','separation_date']: emp[c]=pd.to_datetime(emp[c],errors='coerce')
 for c in ['effective_from','effective_to']: hist[c]=pd.to_datetime(hist[c],errors='coerce')
 roster['week_start']=pd.to_datetime(roster.week_start,errors='coerce'); punches['punch_time']=pd.to_datetime(punches.punch_time,errors='coerce'); hol['holiday_date']=pd.to_datetime(hol.holiday_date,errors='coerce'); leaves['leave_date']=pd.to_datetime(leaves.leave_date,errors='coerce')
 shifts=json.loads((ROOT/'data/raw/shifts.json').read_text())['shifts']; shift_df=pd.DataFrame(shifts); shift_df['start_min']=shift_df.start_time.map(lambda x:int(x[:2])*60+int(x[3:])); shift_df['end_min']=shift_df.end_time.map(lambda x:int(x[:2])*60+int(x[3:])); shift_df['crosses_midnight']=shift_df.crosses_midnight.astype(bool); shift_df['grace_minutes']=shift_df.grace_minutes.astype(int)
 plant_codes={'Head Office':'HO','Korangi Plant':'KOR','SITE Plant':'SITE','Faisalabad Plant':'FSD'}
 # Weekly roster schedule for all relevant Mondays. Missing weeks inherit the last known roster code.
 mondays=pd.date_range(START-pd.Timedelta(days=START.weekday()),END+pd.Timedelta(days=7),freq='7D')
 week_grid=emp[['emp_id','plant']].merge(pd.DataFrame({'week_start':mondays}),how='cross').sort_values(['emp_id','week_start'])
 week_grid=week_grid.merge(roster[['emp_id','week_start','shift_code']],on=['emp_id','week_start'],how='left')
 week_grid['shift_code']=week_grid.groupby('emp_id',sort=False).shift_code.ffill()
 week_grid['shift_code']=week_grid.shift_code.fillna(week_grid.plant.map(lambda p:'GEN' if p=='Head Office' else 'DAY'))
 week_map=week_grid[['emp_id','week_start','shift_code']]
 # Employee-day grid, restricted to dates employed in the six-month period.
 calendar=pd.DataFrame({'attendance_date':pd.date_range(START,END,freq='D')})
 grid=emp[['emp_id','plant','department','hire_date','separation_date']].merge(calendar,how='cross')
 grid=grid[(grid.hire_date.notna())&(grid.hire_date<=grid.attendance_date)&(grid.separation_date.isna()|(grid.separation_date>=grid.attendance_date))].copy()
 grid['week_start']=grid.attendance_date-pd.to_timedelta(grid.attendance_date.dt.weekday,unit='D')
 grid=grid.merge(week_map[['emp_id','week_start','shift_code']],on=['emp_id','week_start'],how='left')
 grid=grid.merge(shift_df[['shift_code','start_min','end_min','crosses_midnight','grace_minutes']],on='shift_code',how='left')
 grid['shift_start']=grid.attendance_date+pd.to_timedelta(grid.start_min,unit='m')
 grid['shift_end']=grid.attendance_date+pd.to_timedelta(grid.end_min,unit='m')+pd.to_timedelta(grid.crosses_midnight.astype(int),unit='D')
 # Plant holiday scope. ALL holidays apply to every plant; named scopes map to the plant codes above.
 hol['scope']=hol.scope.astype(str).str.upper(); grid['plant_code']=grid.plant.map(plant_codes).fillna('')
 holiday_all=set(hol.loc[hol.scope=='ALL','holiday_date'].dropna())
 holiday_specific=set(zip(hol.loc[hol.scope!='ALL','holiday_date'],hol.loc[hol.scope!='ALL','scope']))
 grid['is_holiday']=grid.apply(lambda r:(r.attendance_date in holiday_all) or ((r.attendance_date,r.plant_code) in holiday_specific),axis=1)
 grid['is_sunday']=grid.attendance_date.dt.weekday.eq(6)
 leave_keys=leaves[['emp_id','leave_date']].drop_duplicates().rename(columns={'leave_date':'attendance_date'}); leave_keys['has_leave']=1
 grid=grid.merge(leave_keys,on=['emp_id','attendance_date'],how='left'); grid['has_leave']=grid.has_leave.fillna(0).astype(bool)
 # Attribute punches to the shift-start date. Before 06:00 belongs to the previous day when that day was NIGHT shift.
 punches=punches[punches.punch_time.notna()].copy(); punches['calendar_date']=punches.punch_time.dt.normalize(); punches['previous_date']=punches.calendar_date-pd.Timedelta(days=1); punches['previous_week']=punches.previous_date-pd.to_timedelta(punches.previous_date.dt.weekday,unit='D')
 punch_sched=punches[['emp_id','previous_week']].drop_duplicates().merge(week_map[['emp_id','week_start','shift_code']],left_on=['emp_id','previous_week'],right_on=['emp_id','week_start'],how='left')
 punches=punches.merge(punch_sched[['emp_id','previous_week','shift_code']].rename(columns={'shift_code':'previous_shift'}),on=['emp_id','previous_week'],how='left')
 early=punches.punch_time.dt.hour.lt(6)&punches.previous_shift.eq('NIGHT'); punches['shift_date']=punches.calendar_date; punches.loc[early,'shift_date']=punches.loc[early,'previous_date']
 punches=punches.sort_values(['emp_id','shift_date','punch_time','punch_id'])
 pgroup=punches.groupby(['emp_id','shift_date'],as_index=False).agg(punch_count=('punch_id','size'),check_in=('punch_time','first'),last_punch=('punch_time','last'))
 grid=grid.merge(pgroup,left_on=['emp_id','attendance_date'],right_on=['emp_id','shift_date'],how='left'); grid['punch_count']=grid.punch_count.fillna(0).astype(int)
 grid['check_in']=grid.check_in.where(grid.punch_count>=1,pd.NaT); grid['check_out']=grid.last_punch.where(grid.punch_count>=2,pd.NaT)
 # Status priority: Sunday no punches > holiday no punches > approved leave > punch-count statuses > absent.
 grid['status']='Absent'; grid.loc[grid.punch_count.eq(1),'status']='Missing Punch'; grid.loc[grid.punch_count.ge(2),'status']='Present'
 grid.loc[grid.has_leave,'status']='On Leave'; grid.loc[grid.is_holiday & grid.punch_count.eq(0),'status']='Holiday'; grid.loc[grid.is_sunday & grid.punch_count.eq(0),'status']='Weekly Off'
 # Overnight check-out should be later than check-in even if the timestamp is on the next calendar date.
 bad=grid.check_out.notna()&grid.check_in.notna()&(grid.check_out<grid.check_in); grid.loc[bad,'check_out']=grid.loc[bad,'check_out']+pd.Timedelta(days=1)
 grid['worked_hours']=((grid.check_out-grid.check_in).dt.total_seconds()/3600).clip(lower=0).fillna(0)
 is_present=grid.status.eq('Present'); working=is_present&~grid.is_sunday&~grid.is_holiday
 grid['late_minutes']=0; grid.loc[working,'late_minutes']=((grid.loc[working,'check_in']-grid.loc[working,'shift_start']).dt.total_seconds()/60-grid.loc[working,'grace_minutes']).clip(lower=0).fillna(0).astype(int)
 grid['early_departure_minutes']=0; grid.loc[working,'early_departure_minutes']=((grid.loc[working,'shift_end']-grid.loc[working,'check_out']).dt.total_seconds()/60-grid.loc[working,'grace_minutes']).clip(lower=0).fillna(0).astype(int)
 grid['computed_overtime_hours']=0.0
 overtime_work=is_present&(grid.is_sunday|grid.is_holiday); overtime_regular=is_present&~grid.is_sunday&~grid.is_holiday
 grid.loc[overtime_work,'computed_overtime_hours']=(grid.loc[overtime_work,'worked_hours'].mul(60).floordiv(30).div(2)).round(2)
 after_end=((grid.check_out-grid.shift_end).dt.total_seconds()/60).clip(lower=0).fillna(0)
 grid.loc[overtime_regular,'computed_overtime_hours']=(after_end.loc[overtime_regular].floordiv(30).div(2)).round(2)
 # Effective-dated department attribution: as-of join to employment history.
 hist2=hist.sort_values(['effective_from','emp_id']).copy(); left=grid[['emp_id','attendance_date']].sort_values(['attendance_date','emp_id']); right=hist2.sort_values(['effective_from','emp_id'])
 try:
  matched=pd.merge_asof(left,right,left_on='attendance_date',right_on='effective_from',by='emp_id',direction='backward')
  matched=matched[(matched.effective_to.isna())|(matched.attendance_date<=matched.effective_to)]
  dept_by_date=matched[['emp_id','attendance_date','dept_id']]
  grid=grid.merge(dept_by_date,on=['emp_id','attendance_date'],how='left')
 except (ValueError,KeyError):
  grid['dept_id']=''
 dept_lookup={r.dept_id:(r.dept_name,r.plant) for r in depts.itertuples(index=False)}
 grid['department_name']=grid.dept_id.map(lambda x:dept_lookup.get(x,('', ''))[0]).replace('',pd.NA).fillna(grid.department)
 grid['plant']=grid.dept_id.map(lambda x:dept_lookup.get(x,('', ''))[1]).replace('',pd.NA).fillna(grid.plant)
 # Keep the dataset's stable schema and readable timestamps.
 for c in ['attendance_date','shift_start','shift_end','check_in','check_out']:
  grid[c]=pd.to_datetime(grid[c],errors='coerce')
 def stamp(series): return series.dt.strftime('%Y-%m-%d %H:%M:%S').fillna('')
 df=pd.DataFrame({'emp_id':grid.emp_id,'attendance_date':grid.attendance_date.dt.strftime('%Y-%m-%d'),'plant':grid.plant,'dept_id':grid.dept_id.fillna(''),'department_name':grid.department_name,'shift_code':grid.shift_code,'shift_start':stamp(grid.shift_start),'shift_end':stamp(grid.shift_end),'status':grid.status,'check_in':stamp(grid.check_in),'check_out':stamp(grid.check_out),'worked_hours':grid.worked_hours.round(2),'late_minutes':grid.late_minutes.astype(int),'early_departure_minutes':grid.early_departure_minutes.astype(int),'computed_overtime_hours':grid.computed_overtime_hours.round(2),'is_sunday':grid.is_sunday.astype(int),'is_holiday':grid.is_holiday.astype(int)})
 df.to_csv(OUT/'attendance_daily.csv',index=False)
 df['month']=df.attendance_date.str[:7]
 monthly=df.groupby(['month','plant','department_name'],as_index=False).agg(employee_days=('emp_id','size'),present_days=('status',lambda s:(s=='Present').sum()),absent_days=('status',lambda s:(s=='Absent').sum()),missing_punch_days=('status',lambda s:(s=='Missing Punch').sum()),on_leave_days=('status',lambda s:(s=='On Leave').sum()),late_days=('late_minutes',lambda s:(s>0).sum()),late_minutes=('late_minutes','sum'),early_departure_days=('early_departure_minutes',lambda s:(s>0).sum()),computed_overtime_hours=('computed_overtime_hours','sum'))
 monthly['scheduled_workdays']=monthly.present_days+monthly.absent_days+monthly.missing_punch_days; monthly['absenteeism_pct']=(100*monthly.absent_days/monthly.scheduled_workdays.replace(0,pd.NA)).round(2); monthly.to_csv(OUT/'attendance_monthly.csv',index=False)
 with sqlite3.connect(DB) as con: df.to_sql('attendance_daily_stage',con,if_exists='replace',index=False); monthly.to_sql('attendance_monthly_stage',con,if_exists='replace',index=False)
 print('Attendance rows',len(df),'statuses',df.status.value_counts().to_dict(),'monthly rows',len(monthly))
if __name__=='__main__': main()
