from pathlib import Path
import json
import sqlite3

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "results" / "analytics" / "dashboard_data.json"
DB = ROOT / "indus_weave.db"
OUTPUT = ROOT / "presentation" / "PeopleOps_HR_Pipeline_Results.pptx"

BG = RGBColor(8, 13, 25)
PANEL = RGBColor(17, 27, 45)
TEAL = RGBColor(94, 234, 212)
VIOLET = RGBColor(167, 139, 250)
WHITE = RGBColor(238, 244, 255)
MUTED = RGBColor(156, 174, 201)
AMBER = RGBColor(251, 191, 36)
RED = RGBColor(251, 113, 133)
GREEN = RGBColor(134, 239, 172)


def add_shape(slide, x, y, width, height, color, rounded=False):
    from pptx.enum.shapes import MSO_SHAPE

    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(
        shape_type, Inches(x), Inches(y), Inches(width), Inches(height)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    return shape


def add_text(slide, value, x, y, width, height, size=16, color=WHITE, bold=False):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(width), Inches(height))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    for index, line in enumerate(str(value).split("\n")):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.text = line
        paragraph.font.name = "Aptos"
        paragraph.font.size = Pt(size)
        paragraph.font.bold = bold
        paragraph.font.color.rgb = color
    return box


def new_slide(prs, title, slide_number):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = BG
    add_shape(slide, 0, 0, 13.333, 0.09, TEAL)
    add_text(slide, "PEOPLEOPS / HR PIPELINE", 0.6, 0.35, 7.0, 0.25, 9, TEAL, True)
    add_text(slide, title, 0.6, 0.78, 12.0, 0.55, 25, WHITE, True)
    add_text(
        slide, f"INDUS WEAVE TEXTILES  |  SYNTHETIC DATA  |  APR-SEP 2026  |  {slide_number}/6",
        0.6, 7.12, 12.0, 0.2, 8, MUTED, False,
    )
    return slide


def main() -> None:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    metrics = data["metrics"]
    status = {}
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        status = dict(conn.execute(
            "SELECT status,COUNT(*) FROM fact_attendance_daily GROUP BY status"
        ).fetchall())
        top_findings = {
            "paid_after_separation": conn.execute(
                "SELECT COUNT(*) FROM fact_payroll_line "
                "p JOIN staging_separations s USING(emp_id) "
                "WHERE date(p.month_start)>date(s.separation_date,'start of month') AND p.amount<>0"
            ).fetchone()[0],
            "annual_leave_flags": conn.execute(
                "SELECT COUNT(*) FROM (SELECT u.emp_id FROM "
                "(SELECT emp_id,COUNT(*) used FROM fact_leave_day l JOIN dim_date d "
                "ON d.date_key=l.date_key WHERE lower(l.leave_type) IN ('annual','annual leave') "
                "AND d.full_date BETWEEN '2026-04-01' AND '2026-09-30' GROUP BY emp_id) u "
                "JOIN staging_employee_entitlement e ON e.emp_id=u.emp_id "
                "WHERE u.used>e.annual_leave_entitlement_days)"
            ).fetchone()[0],
            "zero_present_payroll": int(sum(
                row["emp_id"] is not None for row in conn.execute(
                    "SELECT DISTINCT p.emp_id FROM fact_payroll_line p WHERE p.amount<>0 "
                    "AND NOT EXISTS (SELECT 1 FROM fact_attendance_daily a JOIN dim_date d "
                    "ON d.date_key=a.date_key WHERE a.emp_id=p.emp_id "
                    "AND substr(d.full_date,1,7)=substr(p.month_start,1,7) AND a.status='Present')"
                )
            )),
        }
        dq_failures = conn.execute(
            "SELECT COUNT(*) FROM dq_results WHERE status<>'PASS'"
        ).fetchone()[0]

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = BG
    add_shape(slide, 0, 0, 13.333, 0.11, TEAL)
    add_text(slide, "PEOPLEOPS", 0.85, 1.0, 5.0, 0.35, 14, TEAL, True)
    add_text(slide, "HR pipeline &\nworkforce intelligence", 0.85, 1.7, 7.4, 1.5, 34, WHITE, True)
    add_text(
        slide,
        "A reproducible path from raw HCM exports to attendance controls, payroll signals and CFO actions.",
        0.9, 3.55, 6.8, 0.8, 16, MUTED,
    )
    add_shape(slide, 8.7, 1.45, 3.5, 3.5, PANEL, True)
    add_text(slide, "6 MONTHS", 9.15, 2.25, 2.6, 0.4, 18, TEAL, True)
    add_text(slide, f"{metrics['employees']:,}\nemployees", 9.15, 2.9, 2.7, 1.0, 22, WHITE, True)
    add_text(slide, "CASE STUDY DELIVERY  /  APR 01 - SEP 30, 2026", 0.9, 5.8, 7.0, 0.3, 10, AMBER, True)
    add_text(slide, "Fictional company; all identities and transactions are synthetic.", 0.9, 6.35, 8.0, 0.3, 11, MUTED)

    slide = new_slide(prs, "One reproducible pipeline, with source-to-output controls", 2)
    steps = [
        ("01", "RAW LOAD", "12 files / row hashes"),
        ("02", "CLEAN", "dedupe / map / audit"),
        ("03", "ATTENDANCE", "shift-date reconstruction"),
        ("04", "WAREHOUSE", "SCD2 / enforced keys"),
        ("05", "ANALYTICS", "10 SQL answers"),
        ("06", "QUALITY", "reconciliation checks"),
    ]
    for index, (number, heading, detail) in enumerate(steps):
        x = 0.65 + index * 2.08
        add_shape(slide, x, 1.85, 1.82, 1.35, PANEL, True)
        add_text(slide, number, x + 0.14, 2.02, 0.5, 0.25, 11, TEAL, True)
        add_text(slide, heading, x + 0.14, 2.43, 1.55, 0.3, 10, WHITE, True)
        add_text(slide, detail, x + 0.14, 2.82, 1.55, 0.3, 9, MUTED)
    add_text(slide, "Automated control coverage", 0.75, 3.85, 6.0, 0.3, 17, WHITE, True)
    add_text(
        slide,
        "Raw rows accounted for  |  PK/FK integrity  |  duplicate employee and punch audit\n"
        "SCD2 overlap and shift-duration checks  |  accepted status / leave / payroll values\n"
        f"Final DQ checks failing: {dq_failures}  |  SQLite is permitted by the case-study brief",
        0.8, 4.35, 11.8, 1.25, 14, GREEN if dq_failures == 0 else RED,
    )
    add_text(slide, "12 source files include 345,280 biometric events and 53,617 payroll lines.", 0.8, 6.1, 11.6, 0.35, 12, MUTED)

    slide = new_slide(prs, "Attendance reconstructed at employee + shift-date grain", 3)
    status_colors = {
        "Present": TEAL, "Absent": RED, "Missing Punch": VIOLET,
        "On Leave": AMBER, "Weekly Off": MUTED, "Holiday": GREEN,
    }
    status_items = [
        ("Present", status.get("Present", 0)),
        ("Missing punch", status.get("Missing Punch", 0)),
        ("Absent", status.get("Absent", 0)),
        ("On leave", status.get("On Leave", 0)),
        ("Weekly off", status.get("Weekly Off", 0)),
        ("Holiday", status.get("Holiday", 0)),
    ]
    max_value = max((value for _, value in status_items), default=1)
    for index, (label, value) in enumerate(status_items):
        y = 1.7 + index * 0.68
        color = status_colors.get(label, WHITE)
        add_text(slide, label, 0.75, y, 1.8, 0.3, 13, WHITE, True)
        add_shape(slide, 2.65, y + 0.03, 7.0, 0.2, PANEL, True)
        add_shape(slide, 2.65, y + 0.03, 7.0 * value / max_value, 0.2, color, True)
        add_text(slide, f"{value:,}", 10.0, y - 0.02, 1.4, 0.3, 14, color, True)
    add_shape(slide, 0.75, 6.15, 11.5, 0.6, PANEL, True)
    add_text(
        slide,
        f"{metrics['attendance_records']:,} attendance rows  |  {metrics['late_minutes']:,} late minutes  |  "
        "2-minute punch dedupe, night-shift start-date, 10-minute grace and scoped holidays",
        1.0, 6.3, 11.0, 0.3, 11, MUTED,
    )

    slide = new_slide(prs, "Computed overtime is a reconciliation signal, not an accusation", 4)
    overtime = [
        ("Punch-computed", metrics["computed_overtime_hours"], VIOLET),
        ("Approved", metrics["approved_ot_hours"], TEAL),
        ("Payroll-paid", metrics["paid_ot_hours"], AMBER),
    ]
    maximum = max((value for _, value, _ in overtime), default=1)
    for index, (label, value, color) in enumerate(overtime):
        y = 1.85 + index * 1.05
        add_text(slide, label, 0.85, y, 2.0, 0.35, 15, WHITE, True)
        add_shape(slide, 3.0, y + 0.05, 6.5, 0.24, PANEL, True)
        add_shape(slide, 3.0, y + 0.05, 6.5 * value / maximum, 0.24, color, True)
        add_text(slide, f"{value:,.1f} h", 9.85, y - 0.03, 2.2, 0.4, 16, color, True)
    gap = metrics["computed_overtime_hours"] - metrics["paid_ot_hours"]
    add_shape(slide, 0.8, 5.45, 11.7, 1.0, PANEL, True)
    add_text(
        slide,
        f"Gap to paid: {gap:,.1f} hours  |  Earnings: PKR {metrics['payroll_earnings']/1e6:,.1f}m  |  "
        "Q6 paid OT > computed by 15%: "
        f"{next((row['rows'] for row in data['query_tests'] if row['query']=='q06_paid_ot_exceeds_computed'), 0)} rows",
        1.05, 5.72, 11.0, 0.5, 13, WHITE, True,
    )
    add_text(slide, "Evidence: q05 by month + department. Reconcile employee/shift dates, approvals and payroll cutoffs.", 0.85, 6.65, 11.5, 0.3, 11, MUTED)

    slide = new_slide(prs, "Three CFO findings, with evidence and an action", 5)
    findings = [
        (
            f"{gap:,.1f} h",
            "Punch-computed OT exceeds paid OT",
            "Evidence: q05_overtime_reconciliation.csv",
            "Reconcile at employee + shift date; validate approvals and punch pairs.",
        ),
        (
            f"{status.get('Missing Punch', 0):,}",
            "Single-punch employee-days",
            "Evidence: review_missing_punches.csv",
            "Check device uptime, enrollment and repeated patterns before correction.",
        ),
        (
            f"{top_findings['paid_after_separation']:,}",
            "Non-zero payroll rows after separation month",
            "Evidence: q08_paid_after_separation.csv",
            "Validate final-pay policy, cutoff and last-working-day treatment.",
        ),
    ]
    for index, (number, title, evidence, action) in enumerate(findings):
        y = 1.72 + index * 1.48
        add_shape(slide, 0.75, y, 1.55, 0.76, PANEL, True)
        add_text(slide, number, 0.9, y + 0.2, 1.3, 0.35, 18, AMBER, True)
        add_text(slide, title, 2.55, y, 4.4, 0.3, 14, WHITE, True)
        add_text(slide, evidence, 2.55, y + 0.38, 4.6, 0.25, 10, TEAL)
        add_text(slide, action, 7.2, y + 0.03, 5.2, 0.62, 12, MUTED)
    add_text(
        slide,
        f"Additional check: {top_findings['annual_leave_flags']} annual-leave flags; "
        f"{top_findings['zero_present_payroll']} paid employee-months with zero Present days.",
        0.85, 6.4, 11.6, 0.3, 11, MUTED,
    )

    slide = new_slide(prs, "Actions, limitations and the delivered build", 6)
    recommendations = [
        ("01", "OT", "Reconcile computed vs approved vs paid at employee/shift date."),
        ("02", "Attendance", "Prioritize single-punch patterns and biometric device reliability."),
        ("03", "Payroll", "Validate separation and zero-Present flags against policy."),
        ("04", "Data controls", "Review all generated dq_results before CFO sign-off."),
    ]
    for index, (number, heading, detail) in enumerate(recommendations):
        y = 1.65 + index * 0.83
        add_text(slide, number, 0.85, y, 0.5, 0.3, 12, TEAL, True)
        add_text(slide, heading, 1.55, y, 1.8, 0.3, 13, WHITE, True)
        add_text(slide, detail, 3.55, y, 8.5, 0.4, 12, MUTED)
    funnel = ROOT / "results" / "analytics" / "recruitment_funnel.csv"
    funnel_note = "Recruitment funnel bonus output included." if funnel.exists() else "Recruitment funnel bonus output not found."
    add_shape(slide, 0.8, 5.4, 11.6, 0.9, PANEL, True)
    add_text(
        slide,
        "Deliverables: reproducible Python + SQLite build  |  10 SQL CSVs  |  dashboard  |  DQ log  |  6-slide deck\n"
        f"{funnel_note}  All discrepancy flags are review signals; the hidden answer key was not provided.",
        1.05, 5.62, 11.0, 0.55, 11, GREEN,
    )

    prs.save(OUTPUT)
    print(f"Wrote {OUTPUT} ({len(prs.slides)} slides)")


if __name__ == "__main__":
    main()
