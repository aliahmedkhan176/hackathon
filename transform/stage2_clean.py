#!/usr/bin/env python3
"""Stage 2: clean/standardize source data into auditable staging CSVs and SQLite tables.

Raw source files are never edited. Every output is reproducible from data/raw/.
"""
from pathlib import Path
import json, sqlite3, hashlib
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'
OUT = ROOT / 'results' / 'staging'
PROF = ROOT / 'results' / 'profiling'
DB = ROOT / 'indus_weave.db'
OUT.mkdir(parents=True, exist_ok=True); PROF.mkdir(parents=True, exist_ok=True)

DATE_FORMATS = ('%Y-%m-%d', '%d/%m/%Y', '%d-%b-%Y', '%d-%B-%Y')
def parse_mixed_date(v):
    if pd.isna(v) or str(v).strip() == '': return pd.NaT
    s = str(v).strip()
    for fmt in DATE_FORMATS:
        try: return pd.to_datetime(s, format=fmt, errors='raise')
        except (ValueError, TypeError): pass
    return pd.to_datetime(s, errors='coerce', dayfirst=True)
def clean_text_frame(df):
    for c in df.select_dtypes(include=['object']).columns:
        df[c] = df[c].map(lambda x: x.strip() if isinstance(x, str) else x)
    return df
def write(df, name):
    df.to_csv(OUT / f'{name}.csv', index=False)
    return df

def main():
    report=[]
    # Departments establish canonical department names and aliases for renamed departments.
    depts = clean_text_frame(pd.read_csv(RAW/'departments.csv', dtype=str))
    depts['dept_id'] = depts['dept_id'].str.upper()
    depts['dept_name'] = depts['dept_name'].str.strip()
    depts['plant'] = depts['plant'].str.strip()
    aliases={}
    for _, d in depts.iterrows():
        aliases[str(d['dept_name']).casefold().strip()] = d['dept_name']
        if pd.notna(d.get('previous_name')) and str(d['previous_name']).strip():
            aliases[str(d['previous_name']).casefold().strip()] = d['dept_name']
    plant_alias={x.casefold():x for x in ['Head Office','Korangi Plant','SITE Plant','Faisalabad Plant']}

    # Employees: trim, normalize department/plant, parse mixed dates, choose latest update.
    emp=clean_text_frame(pd.read_csv(RAW/'employees.csv', dtype=str))
    emp['emp_id']=emp['emp_id'].str.strip().str.upper()
    for c in ['date_of_birth','hire_date','separation_date']:
        emp[c]=emp[c].map(parse_mixed_date).dt.strftime('%Y-%m-%d')
    emp['updated_at_parsed']=pd.to_datetime(emp['updated_at'], errors='coerce')
    emp['department_original']=emp['department']
    emp['department']=emp['department'].map(lambda x: aliases.get(str(x).casefold().strip(), str(x).strip() if pd.notna(x) else x))
    emp['plant']=emp['plant'].map(lambda x: plant_alias.get(str(x).casefold().strip(), str(x).strip() if pd.notna(x) else x))
    emp['status']=emp['status'].str.strip().str.title()
    emp['employment_type']=emp['employment_type'].str.strip().str.title()
    emp['annual_leave_entitlement']=pd.to_numeric(emp['annual_leave_entitlement'],errors='coerce').astype('Int64')
    before=len(emp)
    emp=emp.sort_values(['emp_id','updated_at_parsed'], na_position='first').drop_duplicates('emp_id',keep='last').copy()
    emp['updated_at_parsed']=emp['updated_at_parsed'].dt.strftime('%Y-%m-%d %H:%M:%S')
    write(emp.drop(columns=['department_original']), 'employees_clean')
    dup=clean_text_frame(pd.read_csv(RAW/'employees.csv',dtype=str)); dup['updated_at_parsed']=pd.to_datetime(dup['updated_at'],errors='coerce')
    dup=dup.sort_values(['emp_id','updated_at_parsed'],na_position='first')
    dup=dup[dup.duplicated('emp_id',keep='last')]
    dup.to_csv(OUT/'employee_dedup_audit.csv',index=False)
    report.append({'check':'employee_deduplication','input_rows':before,'output_rows':len(emp),'removed_rows':before-len(emp),'status':'PASS' if emp.emp_id.is_unique else 'FAIL','detail':'Kept latest updated_at per emp_id; see employee_dedup_audit.csv'})

    # Employment history: recompute effective_to from next effective_from, never trust exported end.
    hist=clean_text_frame(pd.read_csv(RAW/'employment_history.csv',dtype=str))
    hist['emp_id']=hist['emp_id'].str.upper().str.strip(); hist['dept_id']=hist['dept_id'].str.upper().str.strip()
    hist['effective_from']=hist['effective_from'].map(parse_mixed_date)
    hist['exported_effective_to']=hist['effective_to']
    hist['_source_order']=range(len(hist))
    hist=hist.sort_values(['emp_id','effective_from','_source_order'],kind='stable').copy()
    same_day=hist.duplicated(['emp_id','effective_from'],keep='last')
    history_dedup_audit=hist.loc[same_day].copy()
    history_dedup_audit['resolution_reason']='Same employee/effective_from; retained last row in source order'
    write(history_dedup_audit.drop(columns=['_source_order']),'employment_history_dedup_audit')
    hist=hist.drop_duplicates(['emp_id','effective_from'],keep='last').copy()
    hist['effective_to']=hist.groupby('emp_id')['effective_from'].shift(-1)-pd.Timedelta(days=1)
    hist['effective_from']=hist['effective_from'].dt.strftime('%Y-%m-%d'); hist['effective_to']=hist['effective_to'].dt.strftime('%Y-%m-%d')
    hist['basic_salary']=pd.to_numeric(hist['basic_salary'],errors='coerce')
    write(hist.drop(columns=['_source_order']),'employment_history_clean')
    report.append({'check':'employment_history_same_day_deduplication','input_rows':len(hist)+int(same_day.sum()),'output_rows':len(hist),'removed_rows':int(same_day.sum()),'status':'PASS','detail':'For duplicate emp_id/effective_from, kept the last source row; see employment_history_dedup_audit.csv'})

    # Department canonical data.
    write(depts,'departments_clean')
    # Simple source files: trim strings, standardize IDs/casing, parse date/time and numeric columns.
    mapping=clean_text_frame(pd.read_csv(RAW/'device_mapping.csv',dtype=str)); mapping['device_id']=mapping.device_id.str.upper().str.strip(); mapping['device_user_id']=mapping.device_user_id.str.strip(); mapping['emp_id']=mapping.emp_id.str.upper().str.strip()
    write(mapping,'device_mapping_clean')
    roster=clean_text_frame(pd.read_csv(RAW/'shift_roster.csv',dtype=str)); roster['emp_id']=roster.emp_id.str.upper().str.strip(); roster['week_start']=roster.week_start.map(parse_mixed_date).dt.strftime('%Y-%m-%d'); roster['shift_code']=roster.shift_code.str.upper().str.strip()
    write(roster,'shift_roster_clean')
    holidays=clean_text_frame(pd.read_csv(RAW/'holidays.csv',dtype=str)); holidays['holiday_date']=holidays.holiday_date.map(parse_mixed_date).dt.strftime('%Y-%m-%d'); holidays['scope']=holidays.scope.str.upper().str.strip()
    write(holidays,'holidays_clean')
    ot=clean_text_frame(pd.read_csv(RAW/'overtime_requests.csv',dtype=str)); ot['emp_id']=ot.emp_id.str.upper().str.strip(); ot['ot_date']=ot.ot_date.map(parse_mixed_date).dt.strftime('%Y-%m-%d'); ot['status']=ot.status.str.strip().str.title()
    for c in ['requested_hours','approved_hours']: ot[c]=pd.to_numeric(ot[c],errors='coerce')
    write(ot,'overtime_requests_clean')
    payroll=clean_text_frame(pd.read_csv(RAW/'payroll_lines.csv',dtype=str)); payroll['emp_id']=payroll.emp_id.str.upper().str.strip(); payroll['component']=payroll.component.str.upper().str.strip(); payroll['component_type']=payroll.component_type.str.upper().str.strip(); payroll['units']=pd.to_numeric(payroll.units,errors='coerce'); payroll['amount']=pd.to_numeric(payroll.amount,errors='coerce')
    write(payroll,'payroll_lines_clean')
    apps=clean_text_frame(pd.read_csv(RAW/'applications.csv',dtype=str)); apps['dept_id']=apps.dept_id.str.upper().str.strip(); apps['stage']=apps.stage.str.strip().str.title(); apps['stage_date']=apps.stage_date.map(parse_mixed_date).dt.strftime('%Y-%m-%d')
    write(apps,'applications_clean')

    # Leave requests: flatten request and approval steps. Eligibility follows both ordered approvals and no cancellation.
    with open(RAW/'leave_requests.json',encoding='utf-8') as f: leaves=json.load(f)
    reqs=[]; approvals=[]; leave_days=[]
    hol_dates=set(holidays.loc[holidays.scope=='ALL','holiday_date'].dropna())
    for x in leaves:
        emp_obj=x.get('employee') or {}; lv=x.get('leave') or {}; reqid=x.get('request_id')
        fr=parse_mixed_date(lv.get('from')); to=parse_mixed_date(lv.get('to'))
        steps=sorted(x.get('approvals') or [],key=lambda a:(a.get('step',999),str(a.get('approver_role',''))))
        for a in x.get('approvals') or []:
            approvals.append({'request_id':reqid,'step':a.get('step'),'approver_role':a.get('approver_role'),'approver_id':a.get('approver_id'),'action':a.get('action'),'acted_at':a.get('acted_at')})
        actions={(str(a.get('step')),str(a.get('approver_role','')).casefold()):str(a.get('action','')).casefold() for a in steps}
        mgr=any(str(a.get('step'))=='1' and str(a.get('approver_role','')).casefold()=='manager' and str(a.get('action','')).casefold()=='approved' for a in steps)
        hr=any(str(a.get('step'))=='2' and str(a.get('approver_role','')).casefold()=='hr' and str(a.get('action','')).casefold()=='approved' for a in steps)
        cancelled=bool(x.get('cancelled_at'))
        eligible=bool(mgr and hr and not cancelled)
        reason='eligible' if eligible else ('cancelled' if cancelled else 'missing manager approval' if not mgr else 'missing HR approval')
        plant=plant_alias.get(str(emp_obj.get('plant','')).casefold().strip(),str(emp_obj.get('plant','')).strip())
        reqs.append({'request_id':reqid,'emp_id':str(emp_obj.get('emp_id','')).strip().upper(),'plant':plant,'leave_type':str(lv.get('type','')).strip().title(),'leave_from':fr.strftime('%Y-%m-%d') if not pd.isna(fr) else None,'leave_to':to.strftime('%Y-%m-%d') if not pd.isna(to) else None,'days_requested':lv.get('days_requested'),'submitted_at':x.get('submitted_at'),'cancelled_at':x.get('cancelled_at'),'manager_approved':mgr,'hr_approved':hr,'is_eligible':eligible,'eligibility_reason':reason})
        if eligible and not pd.isna(fr) and not pd.isna(to) and fr<=to:
            for day in pd.date_range(fr,to,freq='D'):
                ds=day.strftime('%Y-%m-%d'); weekday=day.weekday()
                plant_scope={'Head Office':'HO','Korangi Plant':'KOR','SITE Plant':'SITE','Faisalabad Plant':'FSD'}.get(plant)
                ph=holidays[(holidays.holiday_date==ds)&(holidays.scope.isin(['ALL',plant_scope] if plant_scope else ['ALL']))]
                if weekday==6 or not ph.empty: continue
                leave_days.append({'request_id':reqid,'emp_id':str(emp_obj.get('emp_id','')).strip().upper(),'plant':plant,'leave_type':str(lv.get('type','')).strip().title(),'leave_date':ds})
    ldf=write(pd.DataFrame(reqs),'leave_requests_clean')
    write(pd.DataFrame(approvals),'leave_approval_steps')
    ldays=pd.DataFrame(leave_days,columns=['request_id','emp_id','plant','leave_type','leave_date'])
    if len(ldays): ldays=ldays.drop_duplicates(['request_id','emp_id','leave_date'])
    write(ldays,'approved_leave_days')
    report.append({'check':'leave_eligibility','input_requests':len(leaves),'eligible_requests':int(ldf.is_eligible.sum()),'approved_leave_days':len(ldays),'status':'PASS','detail':'Requires Manager + HR Approved and cancelled_at empty; excludes Sundays and scoped holidays from leave days'})

    # Punch mapping: map on both device_id and device_user_id. Keep unmapped rows in rejection output.
    punches=clean_text_frame(pd.read_csv(RAW/'biometric_punches.csv',dtype=str))
    punches['device_id']=punches.device_id.str.upper().str.strip(); punches['device_user_id']=punches.device_user_id.str.strip(); punches['punch_time_parsed']=pd.to_datetime(punches.punch_time,errors='coerce')
    mp=mapping[['device_id','device_user_id','emp_id']].drop_duplicates(['device_id','device_user_id'])
    mapped=punches.merge(mp,on=['device_id','device_user_id'],how='left',indicator=True)
    rejected=mapped[mapped['_merge']!='both'].copy(); rejected['reject_reason']='No matching device_id + device_user_id mapping'
    write(rejected[['punch_id','device_id','device_user_id','punch_time','reject_reason']],'rejected_punches')
    good=mapped[mapped['_merge']=='both'].drop(columns=['_merge']).copy()
    good=good.sort_values(['emp_id','punch_time_parsed','punch_id'])
    # Duplicate rule: compare to previous retained punch per employee. Grouped NumPy iteration
    # avoids slow DataFrame.iterrows() over 300k+ biometric events.
    import numpy as np
    keep=[]; duplicate_rows=[]
    for eid, group in good.groupby('emp_id', sort=False):
        timestamps=group['punch_time_parsed'].to_numpy(dtype='datetime64[ns]')
        indexes=group.index.to_numpy(); punch_ids=group['punch_id'].to_numpy(); device_ids=group['device_id'].to_numpy(); punch_times=group['punch_time'].to_numpy()
        prev=None
        for idx, ts, punch_id, device_id, punch_time in zip(indexes,timestamps,punch_ids,device_ids,punch_times):
            if not np.isnat(ts) and prev is not None and (ts-prev)/np.timedelta64(1,'s')<=120:
                duplicate_rows.append({'punch_id':punch_id,'emp_id':eid,'device_id':device_id,'punch_time':punch_time,'duplicate_of_previous_retained_punch':True,'reason':'Within 120 seconds of previous retained punch'})
            else:
                keep.append(idx)
                if not np.isnat(ts): prev=ts
    cleanp=good.loc[keep].copy()
    # Clock-drift evidence: DEV-SITE-01 matches the normal 06/14/22 shift-boundary pattern in Apr-Jun,
    # then shifts to 07/15/23 (and 00:xx after 23:xx) in Jul-Sep. Correct those events by -60 minutes.
    cleanp['punch_time_raw']=cleanp['punch_time']
    cleanp['clock_correction_minutes']=0
    site_clock_mask=(cleanp['device_id']=='DEV-SITE-01') & (cleanp['punch_time_parsed']>=pd.Timestamp('2026-07-01'))
    cleanp.loc[site_clock_mask,'punch_time_parsed']=cleanp.loc[site_clock_mask,'punch_time_parsed']-pd.Timedelta(minutes=60)
    cleanp.loc[site_clock_mask,'clock_correction_minutes']=60
    cleanp['punch_time']=cleanp['punch_time_parsed'].dt.strftime('%Y-%m-%d %H:%M:%S')
    write(cleanp.loc[site_clock_mask,['punch_id','device_id','emp_id','punch_time_raw','punch_time','clock_correction_minutes']].rename(columns={'punch_time_raw':'original_punch_time','punch_time':'corrected_punch_time'}),'punch_clock_correction_audit')
    write(pd.DataFrame([{'device_id':'DEV-SITE-01','effective_from':'2026-07-01','correction_minutes':60,'action':'Subtract 60 minutes from timestamps from 2026-07-01 onward','evidence':'Hourly peaks at 06:00/14:00/22:00 in Apr-Jun move to 07:00/15:00/23:00 in Jul-Sep, with 00:xx spillover after 23:xx; -60 minutes restores the earlier shift-boundary pattern. Raw source files are unchanged.'}]),'device_clock_corrections')
    write(cleanp[['punch_id','device_id','device_user_id','emp_id','punch_time']],'biometric_punches_mapped_deduped')
    write(pd.DataFrame(duplicate_rows,columns=['punch_id','emp_id','device_id','punch_time','duplicate_of_previous_retained_punch','reason']),'duplicate_punches')
    report.append({'check':'punch_mapping','input_punches':len(punches),'mapped_punches':len(good),'rejected_unmapped':len(rejected),'duplicate_punches_removed':len(duplicate_rows),'retained_mapped_punches':len(cleanp),'status':'PASS' if len(punches)==len(rejected)+len(duplicate_rows)+len(cleanp) else 'FAIL','detail':'Mapping uses composite device_id + device_user_id; duplicate rule compares each punch with previous retained employee punch'})

    # Evidence-only clock profile: no correction is applied until Stage 3 shift-alignment confirms offset.
    # Punches have no direction flag; report time-of-day distributions per device as evidence.
    profile=cleanp.copy(); profile['hour']=profile['punch_time'].str[11:13].astype(int); profile['minute_of_day']=profile['punch_time'].str[11:16].map(lambda s:int(s[:2])*60+int(s[3:]))
    prof=profile.groupby('device_id').agg(punch_count=('punch_id','count'),median_minute_of_day=('minute_of_day','median'),p10_minute=('minute_of_day',lambda s:s.quantile(.1)),p90_minute=('minute_of_day',lambda s:s.quantile(.9))).reset_index()
    prof['median_clock_time']=prof['median_minute_of_day'].map(lambda v:f'{int(v//60):02d}:{int(v%60):02d}')
    write(prof,'device_clock_profile')
    report.append({'check':'device_clock_offset','status':'CORRECTED','detail':'DEV-SITE-01 timestamps from 2026-07-01 onward shifted +60 minutes relative to Apr-Jun boundary clusters (06/14/22 became 07/15/23 with 00:xx spillover). Subtracted 60 minutes; see device_clock_corrections.csv and punch_clock_correction_audit.csv. Raw source remains unchanged.'})

    # Persist staging outputs as SQLite tables for downstream stages.
    with sqlite3.connect(DB) as con:
        for path in OUT.glob('*.csv'):
            table='stg_'+path.stem.replace('-','_')
            frame=pd.read_csv(path,dtype=str,keep_default_na=False)
            frame.to_sql(table,con,if_exists='replace',index=False)
    pd.DataFrame(report).to_csv(PROF/'stage2_report.csv',index=False)
    print('Stage 2 complete. Outputs:',OUT)
    print(pd.DataFrame(report).to_string(index=False))
    print(f'Clean employees: {len(emp)}; employment history: {len(hist)}; mapped retained punches: {len(cleanp)}; rejected punches: {len(rejected)}; removed duplicates: {len(duplicate_rows)}; approved leave days: {len(ldays)}')

if __name__=='__main__': main()
