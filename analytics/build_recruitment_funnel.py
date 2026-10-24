"""Build the optional recruitment funnel bonus output from staged applications."""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results" / "staging" / "applications_clean.csv"
OUTPUT = ROOT / "results" / "analytics" / "recruitment_funnel.csv"
MAIN_STAGES = ["Applied", "Screened", "Interviewed", "Offered", "Hired"]


def main() -> None:
    applications = pd.read_csv(SOURCE, dtype=str, keep_default_na=False)
    applications["stage_date"] = pd.to_datetime(applications["stage_date"], errors="coerce")
    applications["stage"] = applications["stage"].str.strip().str.title()
    applications = applications.dropna(subset=["stage_date"])
    applications = applications.sort_values(["application_id", "stage_date"])
    applications = applications.drop_duplicates(["application_id", "stage"], keep="first")

    stages = applications.pivot(index="application_id", columns="stage", values="stage_date")
    rows = []
    for position, stage in enumerate(MAIN_STAGES):
        application_count = int(stages[stage].notna().sum()) if stage in stages else 0
        next_stage = MAIN_STAGES[position + 1] if position + 1 < len(MAIN_STAGES) else None
        next_count = int(stages[next_stage].notna().sum()) if next_stage in stages else None
        transition_days = (
            (stages.loc[stages[stage].notna() & stages[next_stage].notna(), next_stage]
             - stages.loc[stages[stage].notna() & stages[next_stage].notna(), stage]).dt.days
            if next_stage and stage in stages and next_stage in stages else pd.Series(dtype=float)
        )
        rows.append({
            "stage": stage,
            "applications_reaching_stage": application_count,
            "next_stage": next_stage or "",
            "applications_reaching_next_stage": next_count,
            "conversion_to_next_pct": (
                round(next_count * 100 / application_count, 2)
                if next_count is not None and application_count else None
            ),
            "median_days_to_next_stage": (
                round(float(transition_days.median()), 1) if not transition_days.empty else None
            ),
        })

    for terminal_stage in ["Rejected", "Offer Declined"]:
        count = int(stages[terminal_stage].notna().sum()) if terminal_stage in stages else 0
        rows.append({
            "stage": terminal_stage,
            "applications_reaching_stage": count,
            "next_stage": "",
            "applications_reaching_next_stage": None,
            "conversion_to_next_pct": None,
            "median_days_to_next_stage": None,
        })

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUTPUT, index=False)
    print(pd.DataFrame(rows).to_string(index=False))
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
