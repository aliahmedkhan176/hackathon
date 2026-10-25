"""Rebuild the PeopleOps HR pipeline and publish its verified deliverables."""
from pathlib import Path
import shutil
import subprocess
import sys

from ingestion.load_raw import main as load_main
from quality.run_checks import main as quality_main
from transform.stage2_clean import main as stage2_main
from attendance.build_attendance import main as attendance_main
from warehouse.build_warehouse import main as warehouse_main
from analytics.run_analytics import main as analytics_main
from web.build_dashboard import main as dashboard_main

ROOT = Path(__file__).resolve().parent
DELIVERABLES = ROOT.parent / "deliverables"


def run_script(path: Path) -> None:
    subprocess.run([sys.executable, str(path)], check=True, cwd=ROOT)


def run_powershell_script(path: Path) -> None:
    if sys.platform != "win32":
        raise RuntimeError("Exporting the required submission PDF needs Windows PowerPoint.")
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(path),
        ],
        check=True,
        cwd=ROOT,
    )


def main() -> None:
    print("\n[1/11] Loading untouched raw source files")
    load_main()
    print("\n[2/11] Checking raw ingestion metadata")
    quality_main(final=False)
    print("\n[3/11] Cleaning and staging data")
    stage2_main()
    print("\n[4/11] Reconstructing attendance and overtime")
    attendance_main()
    print("\n[5/11] Building the constrained SQLite warehouse")
    warehouse_main()
    print("\n[6/11] Running full reconciliation and warehouse quality checks")
    quality_main(final=True)
    print("\n[7/11] Executing the ten SQL questions")
    analytics_main()
    print("\n[8/11] Building the recruitment funnel bonus output")
    run_script(ROOT / "analytics" / "build_recruitment_funnel.py")
    print("\n[9/11] Rebuilding dashboard, findings and six-slide presentation")
    dashboard_main()
    run_script(ROOT / "presentation" / "build_findings.py")
    run_script(ROOT / "presentation" / "build_deck.py")
    run_powershell_script(ROOT / "presentation" / "export_pdf.ps1")

    DELIVERABLES.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "web" / "dashboard.html", DELIVERABLES / "PeopleOps_HR_Dashboard.html")
    shutil.copy2(
        ROOT / "presentation" / "PeopleOps_HR_Pipeline_Results.pptx",
        DELIVERABLES / "PeopleOps_HR_Pipeline_Results.pptx",
    )
    shutil.copy2(
        ROOT / "presentation" / "slides.pdf",
        DELIVERABLES / "PeopleOps_HR_Pipeline_Results.pdf",
    )
    print(f"\n[10/11] Published verified files to {DELIVERABLES}")
    print("\n[11/11] Running project acceptance tests")
    run_script(ROOT / "tests" / "validate_project.py")
    print("\nCOMPLETE: pipeline, data-quality checks, analytics, dashboard and presentation rebuilt.")


if __name__ == "__main__":
    main()
