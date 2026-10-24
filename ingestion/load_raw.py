from pathlib import Path
import csv, hashlib, json, sqlite3
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "indus_weave.db"
LOG_DIR = ROOT / "logs"

def table_name(filename: str) -> str:
    stem = Path(filename).stem.lower()
    return "".join(ch if ch.isalnum() else "_" for ch in stem)

def row_hash(row: dict) -> str:
    payload = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def read_records(path: Path):
    if path.suffix.lower() == ".csv":
        # Read every input value as text; preserve source column names.
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return [], []
            headers = reader.fieldnames
            rows = []
            for row in reader:
                rows.append({str(k): ("" if v is None else str(v)) for k, v in row.items()})
            return headers, rows
    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8-sig") as f:
            data = json.load(f)
        # Keep nested JSON intact as a JSON string; flattening belongs in staging.
        if isinstance(data, list):
            return ["_json_record"], [{"_json_record": json.dumps(x, ensure_ascii=False)} for x in data]
        return ["_json_record"], [{"_json_record": json.dumps(data, ensure_ascii=False)}]
    return [], []

def main():
    LOG_DIR.mkdir(exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in RAW_DIR.iterdir() if p.suffix.lower() in {".csv", ".json"})
    report = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        for path in files:
            headers, rows = read_records(path)
            table = table_name(path.name)
            if not headers:
                report.append({"source_file": path.name, "table_name": f"raw_{table}",
                               "source_rows": 0, "new_rows": 0, "table_rows": 0, "status": "empty/no header"})
                continue
            raw_table = f"raw_{table}"
            cols = [f'"{h.replace(chr(34), chr(34)*2)}" TEXT' for h in headers]
            conn.execute(f'CREATE TABLE IF NOT EXISTS "{raw_table}" ({", ".join(cols)}, '
                         '"_source_file" TEXT NOT NULL, "_loaded_at" TEXT NOT NULL, '
                         '"_row_hash" TEXT NOT NULL, UNIQUE("_source_file", "_row_hash"))')
            # Existing tables can be re-used. Verify source columns are compatible.
            existing = {r[1] for r in conn.execute(f'PRAGMA table_info("{raw_table}")')}
            missing = [h for h in headers if h not in existing]
            if missing:
                raise RuntimeError(f"{raw_table}: schema changed; missing columns {missing}. "
                                   "Keep raw source versions separate or review schema manually.")
            new_rows = 0
            loaded_at = datetime.now(timezone.utc).isoformat()
            insert_cols = headers + ["_source_file", "_loaded_at", "_row_hash"]
            quoted_cols = ", ".join('"' + c.replace('"', '""') + '"' for c in insert_cols)
            placeholders = ", ".join("?" for _ in insert_cols)
            for row in rows:
                digest = row_hash(row)
                values = [row.get(h, "") for h in headers] + [path.name, loaded_at, digest]
                cur = conn.execute(
                    f'INSERT OR IGNORE INTO "{raw_table}" ({quoted_cols}) VALUES ({placeholders})',
                    values
                )
                new_rows += cur.rowcount
            table_rows = conn.execute(f'SELECT COUNT(*) FROM "{raw_table}"').fetchone()[0]
            report.append({"source_file": path.name, "table_name": raw_table,
                           "source_rows": len(rows), "new_rows": new_rows,
                           "table_rows": table_rows, "status": "loaded"})
        conn.commit()
    import pandas as pd
    pd.DataFrame(report, columns=["source_file","table_name","source_rows","new_rows","table_rows","status"]).to_csv(
        LOG_DIR / "load_counts.csv", index=False
    )
    if not files:
        print(f"No CSV/JSON inputs found in {RAW_DIR}")
    else:
        print(f"Loaded {len(files)} file(s) into {DB_PATH}")
        for r in report:
            print(f"{r['source_file']}: source={r['source_rows']}, new={r['new_rows']}, table={r['table_rows']}")

if __name__ == "__main__":
    main()
