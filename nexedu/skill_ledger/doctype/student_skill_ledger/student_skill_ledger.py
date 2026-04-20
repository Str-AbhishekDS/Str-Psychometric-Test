# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


"""
DocType: Skill Ledger Event
Purpose: Append-only audit log. Every change to a Student Skill is recorded
         here as an immutable event. No update/delete hooks are defined
         intentionally — this is a write-once log.
"""

# import frappe
# from frappe.model.document import Document

# class SkillLedgerEvent(Document):
class StudentSkillLedger(Document):
    def before_insert(self):
        self.flags.ignore_validate_update_after_submit = True

    def before_save(self):
        if not self.is_new():
            frappe.throw(
                "Skill Ledger Events are immutable and cannot be modified.",
                frappe.PermissionError,
            )

    def on_trash(self):
        frappe.throw(
            "Skill Ledger Events cannot be deleted.",
            frappe.PermissionError,
        )

# ------------------------------------------------------------------
# Whitelisted API
# ------------------------------------------------------------------

@frappe.whitelist()
def get_timeline(student: str, skill: str = "") -> list:
    """
    Returns the full audit timeline for a student, optionally filtered
    by a specific skill.

    Args:
        student: Student document name.
        skill:   (Optional) Skill document name to narrow results.

    Returns:
        List of event dicts ordered by event_time descending.
    """
    filters = {"student": student}
    if skill:
        filters["skill"] = skill

    return frappe.get_all(
        "Student Skill Ledger",
        filters=filters,
        fields=[
            "name", "skill", "skill_level", "event_type", "status",
            "evidence_count", "endorsement_count", "event_time",
            "reference_doctype", "reference_name", "comment",
        ],
        order_by="event_time desc",
        limit=200,
    )


@frappe.whitelist()
def get_day_streak(student: str) -> int:
    """
    Calculates the current consecutive-day activity streak for a student
    based on Skill Ledger Events.

    Returns the number of consecutive days (ending today) that had at
    least one ledger event.
    """
    from frappe.utils import getdate, today as frappe_today, add_days

    events = frappe.get_all(
        "Student Skill Ledger",
        filters={"student": student},
        fields=["event_time"],
        order_by="event_time desc",
        limit=365,
    )

    if not events:
        return 0

    # Collect unique dates
    event_dates = sorted(
        {getdate(e["event_time"]) for e in events}, reverse=True
    )

    current = getdate(frappe_today())
    streak = 0

    for d in event_dates:
        if d == current:
            streak += 1
            current = add_days(current, -1)
        elif d < current:
            break  # gap found

    return streak

import frappe
from frappe import _


# ---------------------------------------------------------------------------
# Public API endpoint
# Usage:
#   GET /api/method/your_app.api.student_skill_report.get_student_skills
#   Params: student (required), skill, skill_level, status, event_type,
#           page (default 1), page_size (default 50)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_student_skills(
    student=None,
    skill=None,
    skill_level=None,
    status=None,
    event_type=None,
    page=1,
    page_size=50,
):
    """
    Returns a paginated list of Student Skill records with ledger events
    and computed verification status.

    Raises PermissionError if the current user cannot read Student Skill.
    Raises ValidationError if `student` is not provided.
    """

    # ── Permission check ──────────────────────────────────────────────────
    if not frappe.has_permission("Student Skill", "read"):
        frappe.throw(_("Not permitted to read Student Skill"), frappe.PermissionError)

    # ── Input validation ──────────────────────────────────────────────────
    if not student:
        frappe.throw(_("student is a required parameter"), frappe.ValidationError)

    try:
        page = max(1, int(page))
        page_size = min(max(1, int(page_size)), 200)   # hard cap at 200
    except (ValueError, TypeError):
        frappe.throw(_("page and page_size must be integers"), frappe.ValidationError)

    offset = (page - 1) * page_size

    # ── Build WHERE conditions ─────────────────────────────────────────────
    conditions = ""
    values = {"student": student}

    if skill:
        conditions += " AND ss.skill = %(skill)s"
        values["skill"] = skill

    if skill_level:
        conditions += " AND ss.current_level = %(skill_level)s"
        values["skill_level"] = skill_level

    if status:
        conditions += " AND ss.status = %(status)s"
        values["status"] = status

    event_condition = ""
    if event_type:
        event_condition = " AND sle.event_type = %(event_type)s"
        values["event_type"] = event_type

    # ── Verification status via correlated subquery (MariaDB-safe) ─────────
    # Using a subquery instead of MAX(...) OVER (PARTITION BY) so the query
    # works on MariaDB < 10.2 as well as MySQL 8+.
    verification_subquery = """
        (
            SELECT
                CASE
                    WHEN SUM(CASE WHEN v.status = 'Verified'  THEN 1 ELSE 0 END) > 0 THEN 'Verified'
                    WHEN SUM(CASE WHEN v.status = 'Rejected'  THEN 1 ELSE 0 END) > 0 THEN 'Rejected'
                    ELSE NULL
                END
            FROM `tabStudent Skill Ledger` v
            WHERE v.student_skill = ss.name
              AND v.event_type = 'Verification'
        )
    """

    # ── Count query (for pagination metadata) ─────────────────────────────
    count_sql = f"""
        SELECT COUNT(*) AS total
        FROM `tabStudent Skill` ss
        LEFT JOIN `tabStudent Skill Ledger` sle
            ON sle.student_skill = ss.name
        WHERE ss.student = %(student)s
            {conditions}
            {event_condition}
    """
    count_result = frappe.db.sql(count_sql, values, as_dict=True)
    total_records = count_result[0].get("total", 0) if count_result else 0

    # ── Main data query ────────────────────────────────────────────────────
    values["limit"] = page_size
    values["offset"] = offset

    data_sql = f"""
        SELECT
            ss.name            AS student_skill,
            ss.student,
            ss.skill,
            ss.current_level   AS skill_level,
            ss.status,

            CASE
                WHEN sle.event_type = 'Verification' THEN NULL
                ELSE sle.event_type
            END                AS event_type,

            sle.event_time,
            sle.status         AS ledger_status,

            {verification_subquery} AS verification_status

        FROM `tabStudent Skill` ss
        LEFT JOIN `tabStudent Skill Ledger` sle
            ON sle.student_skill = ss.name

        WHERE ss.student = %(student)s
            {conditions}
            {event_condition}

        ORDER BY sle.event_time DESC
        LIMIT %(limit)s OFFSET %(offset)s
    """

    rows = frappe.db.sql(data_sql, values, as_dict=True)

    # ── Post-process: default verification_status to "Pending" ────────────
    for row in rows:
        if not row.get("verification_status"):
            row["verification_status"] = "Pending"

    # ── Return structured response ─────────────────────────────────────────
    return {
        "data": rows,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_records": total_records,
            "total_pages": -(-total_records // page_size),   # ceiling division
        },
    }


# ---------------------------------------------------------------------------
# Convenience endpoint: fetch a single student skill with its full ledger
# Usage:
#   GET /api/method/your_app.api.student_skill_report.get_skill_detail
#   Params: student_skill (required)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_skill_detail(student_skill=None):
    """
    Returns a single Student Skill document plus all its ledger entries,
    ordered newest-first.
    """
    if not student_skill:
        frappe.throw(_("student_skill is required"), frappe.ValidationError)

    if not frappe.has_permission("Student Skill", "read", doc=student_skill):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    skill_doc = frappe.get_doc("Student Skill", student_skill)

    ledger = frappe.db.get_all(
        "Student Skill Ledger",
        filters={"student_skill": student_skill},
        fields=["name", "event_type", "event_time", "status"],
        order_by="event_time desc",
    )

    # Compute verification status from ledger
    verification_status = "Pending"
    for entry in ledger:
        if entry.get("event_type") == "Verification":
            if entry.get("status") == "Verified":
                verification_status = "Verified"
                break
            elif entry.get("status") == "Rejected":
                verification_status = "Rejected"

    return {
        "student_skill": skill_doc.as_dict(),
        "ledger": ledger,
        "verification_status": verification_status,
    }