"""Basic profiling helper for CSV files; run with: python ingestion/profile_sources.py"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"

def main():
    paths = sorted(RAW_DIR.glob("*.csv"))
    if not paths:
        print("No CSV files found in data/raw/")
        return
    for path in paths:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        print(f"\n=== {path.name} ===")
        print("Rows:", len(df), "Columns:", len(df.columns))
        print("Columns:", list(df.columns))
        print("Blank values by column:")
        print((df == "").sum().sort_values(ascending=False).to_string())
        for col in df.columns:
            counts = df[col].value_counts(dropna=False).head(8)
            if len(counts) <= 8:
                print(f"\n{col} top values:\n{counts.to_string()}")

if __name__ == "__main__":
    main()
