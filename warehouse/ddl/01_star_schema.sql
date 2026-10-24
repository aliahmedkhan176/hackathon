-- SQLite-compatible warehouse starter schema.
-- Adjust data types/columns after checking the actual data dictionary.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS dim_department (
  department_key INTEGER PRIMARY KEY,
  department_id TEXT NOT NULL UNIQUE,
  department_name TEXT NOT NULL,
  plant_name TEXT NOT NULL,
  cost_center TEXT
);

CREATE TABLE IF NOT EXISTS dim_shift (
  shift_key INTEGER PRIMARY KEY,
  shift_id TEXT NOT NULL UNIQUE,
  shift_name TEXT NOT NULL,
  start_time TEXT NOT NULL,
  end_time TEXT NOT NULL,
  crosses_midnight INTEGER NOT NULL DEFAULT 0 CHECK (crosses_midnight IN (0,1)),
  grace_minutes INTEGER NOT NULL CHECK (grace_minutes >= 0)
);

CREATE TABLE IF NOT EXISTS dim_date (
  date_key INTEGER PRIMARY KEY,
  full_date TEXT NOT NULL UNIQUE,
  year INTEGER NOT NULL,
  month INTEGER NOT NULL,
  day INTEGER NOT NULL,
  month_start TEXT NOT NULL,
  month_end TEXT NOT NULL,
  is_sunday INTEGER NOT NULL DEFAULT 0 CHECK (is_sunday IN (0,1)),
  is_holiday INTEGER NOT NULL DEFAULT 0 CHECK (is_holiday IN (0,1))
);

-- SCD Type 2: each version of an employee has a validity interval.
CREATE TABLE IF NOT EXISTS dim_employee (
  employee_key INTEGER PRIMARY KEY,
  emp_id TEXT NOT NULL,
  employee_name TEXT NOT NULL,
  department_key INTEGER NOT NULL,
  job_title TEXT,
  grade TEXT,
  employment_status TEXT,
  valid_from TEXT NOT NULL,
  valid_to TEXT NOT NULL,
  is_current INTEGER NOT NULL DEFAULT 0 CHECK (is_current IN (0,1)),
  annual_leave_entitlement_days INTEGER NOT NULL CHECK (annual_leave_entitlement_days >= 0),
  hire_date TEXT,
  separation_date TEXT,
  UNIQUE (emp_id, valid_from),
  FOREIGN KEY (department_key) REFERENCES dim_department(department_key),
  CHECK (valid_from <= valid_to)
);
CREATE INDEX IF NOT EXISTS ix_dim_employee_asof ON dim_employee(emp_id, valid_from, valid_to);

CREATE TABLE IF NOT EXISTS fact_attendance_daily (
  attendance_key INTEGER PRIMARY KEY,
  emp_id TEXT NOT NULL,
  date_key INTEGER NOT NULL,
  employee_key INTEGER NOT NULL,
  shift_key INTEGER,
  status TEXT NOT NULL CHECK (status IN ('Present','Absent','On Leave','Holiday','Weekly Off','Missing Punch')),
  check_in TEXT,
  check_out TEXT,
  worked_hours REAL NOT NULL CHECK (worked_hours >= 0),
  late_minutes INTEGER NOT NULL DEFAULT 0 CHECK (late_minutes >= 0),
  early_departure_minutes INTEGER NOT NULL DEFAULT 0 CHECK (early_departure_minutes >= 0),
  computed_overtime_hours REAL NOT NULL DEFAULT 0 CHECK (computed_overtime_hours >= 0),
  FOREIGN KEY (date_key) REFERENCES dim_date(date_key),
  FOREIGN KEY (employee_key) REFERENCES dim_employee(employee_key),
  FOREIGN KEY (shift_key) REFERENCES dim_shift(shift_key),
  UNIQUE (emp_id, date_key)
);

CREATE TABLE IF NOT EXISTS fact_leave_day (
  leave_day_key INTEGER PRIMARY KEY,
  emp_id TEXT NOT NULL,
  employee_key INTEGER NOT NULL,
  date_key INTEGER NOT NULL,
  leave_type TEXT NOT NULL,
  request_id TEXT,
  FOREIGN KEY (employee_key) REFERENCES dim_employee(employee_key),
  FOREIGN KEY (date_key) REFERENCES dim_date(date_key)
);

CREATE TABLE IF NOT EXISTS fact_overtime_approved (
  overtime_key INTEGER PRIMARY KEY,
  emp_id TEXT NOT NULL,
  employee_key INTEGER NOT NULL,
  date_key INTEGER NOT NULL,
  approved_hours REAL NOT NULL DEFAULT 0 CHECK (approved_hours >= 0),
  request_status TEXT,
  FOREIGN KEY (employee_key) REFERENCES dim_employee(employee_key),
  FOREIGN KEY (date_key) REFERENCES dim_date(date_key)
);

CREATE TABLE IF NOT EXISTS fact_payroll_line (
  payroll_line_key INTEGER PRIMARY KEY,
  emp_id TEXT NOT NULL,
  employee_key INTEGER NOT NULL,
  month_start TEXT NOT NULL,
  department_key INTEGER NOT NULL,
  pay_component TEXT NOT NULL,
  component_type TEXT NOT NULL,
  units REAL,
  amount REAL NOT NULL DEFAULT 0 CHECK (amount >= 0),
  FOREIGN KEY (employee_key) REFERENCES dim_employee(employee_key),
  FOREIGN KEY (department_key) REFERENCES dim_department(department_key)
);

CREATE TABLE IF NOT EXISTS dq_results (
  dq_id INTEGER PRIMARY KEY,
  check_name TEXT NOT NULL,
  table_name TEXT NOT NULL,
  failed_rows INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('PASS','FAIL','INFO')),
  details TEXT,
  checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
