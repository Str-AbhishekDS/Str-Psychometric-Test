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
        "Skill Ledger Event",
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
        "Skill Ledger Event",
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