# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import today, now_datetime


class PathProgressLog(Document):
    """
    Path Progress Log — separate doctype for milestone-level logging.

    Lifecycle
    ─────────
    validate:
        1. fetch_milestone_order  — sync self.order from Path Milestone
        2. prevent_duplicate_entry — one log per milestone per enrollment
        3. enforce_sequential_progress — cannot skip ahead in order

    on_update:
        4. update_enrollment_progress — SQL-update the enrollment row
        5. create_student_skill — add skill to student's ledger
    """

    def validate(self):
        self.fetch_milestone_order()
        self.prevent_duplicate_entry()
        self.enforce_sequential_progress()

    def on_update(self):
        self.update_enrollment_progress()
        self.create_student_skill()

    # ══════════════════════════════════════════════════════════════════════════
    # 1. FETCH MILESTONE ORDER
    # ══════════════════════════════════════════════════════════════════════════

    def fetch_milestone_order(self):
        """
        Pulls the order value from Path Milestone and writes it to self.order.
        Also verifies the milestone belongs to the selected career_path.
        """
        if not self.milestone:
            return

        milestone_order = frappe.db.get_value(
            "Path Milestone",
            {"name": self.milestone, "parent": self.career_path},
            "order",
        )

        if milestone_order is not None:
            self.order = int(milestone_order)
        else:
            frappe.throw(
                f"Milestone <b>{self.milestone}</b> does not belong to "
                f"Career Path <b>{self.career_path}</b>."
            )

    # ══════════════════════════════════════════════════════════════════════════
    # 2. PREVENT DUPLICATE MILESTONE ENTRY
    # ══════════════════════════════════════════════════════════════════════════

    def prevent_duplicate_entry(self):
        if not self.enrollment or not self.milestone:
            return

        duplicate = frappe.db.exists(
            "Path Progress Log",
            {
                "enrollment": self.enrollment,
                "milestone":  self.milestone,
                "name":       ["!=", self.name],
            },
        )

        if duplicate:
            frappe.throw(
                f"Milestone <b>{self.milestone}</b> is already logged "
                f"for this enrollment. Each milestone can only be logged once."
            )

    # ══════════════════════════════════════════════════════════════════════════
    # 3. ENFORCE SEQUENTIAL PROGRESS
    # ══════════════════════════════════════════════════════════════════════════

    def enforce_sequential_progress(self):
        if not self.enrollment or not self.order:
            return

        # If milestone hasn't changed on an existing record, skip re-validation
        if not self.is_new():
            original_milestone = frappe.db.get_value(
                "Path Progress Log", self.name, "milestone"
            )
            if original_milestone == self.milestone:
                return

        current_milestone_order = (
            frappe.db.get_value(
                "Student Path Enrollment",
                self.enrollment,
                "current_milestone_order",
            )
            or 1
        )

        if int(self.order) != int(current_milestone_order):
            frappe.throw(
                f"Cannot log Milestone Order <b>{self.order}</b>. "
                f"Please complete Milestone Order <b>{current_milestone_order}</b> first."
            )

    # ══════════════════════════════════════════════════════════════════════════
    # 4. UPDATE ENROLLMENT PROGRESS
    # ══════════════════════════════════════════════════════════════════════════

    def update_enrollment_progress(self):
        if not self.enrollment:
            return

        total = frappe.db.count("Path Milestone", {"parent": self.career_path})
        if not total:
            return

        current_order = int(self.order)
        percent       = round((current_order / total) * 100, 2)
        next_order    = current_order + 1
        status        = "Completed" if current_order >= total else "Active"

        # Fetch previous status BEFORE updating (for success stories trigger)
        previous_status = frappe.db.get_value(
            "Student Path Enrollment",
            self.enrollment,
            "status",
            cache=False,
        )

        frappe.db.sql(
            """
            UPDATE `tabStudent Path Enrollment`
            SET
                current_milestone_order = %s,
                completion_percent      = %s,
                status                  = %s,
                modified                = NOW(),
                modified_by             = %s
            WHERE name = %s
            """,
            (next_order, percent, status, frappe.session.user, self.enrollment),
        )

        frappe.db.commit()
        frappe.clear_cache(doctype="Student Path Enrollment")

        # Trigger success story count if path just completed
        if status == "Completed" and previous_status != "Completed":
            self._increment_career_path_success_stories()

        frappe.msgprint(
            f"Progress → Milestone {current_order}/{total} "
            f"| {percent}% | Next order: {next_order}",
            indicator="green",
            alert=True,
        )

    def _increment_career_path_success_stories(self):
        frappe.db.sql(
            """
            UPDATE `tabCareer Path`
            SET success_stories = IFNULL(success_stories, 0) + 1
            WHERE name = %s
            """,
            self.career_path,
        )
        frappe.db.commit()
        frappe.msgprint(
            f"🎉 Path '<b>{self.career_path}</b>' completed! "
            "Success stories updated.",
            indicator="green",
            alert=True,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # 5. CREATE STUDENT SKILL FROM MILESTONE
    # ══════════════════════════════════════════════════════════════════════════

    def create_student_skill(self):
        if not self.enrollment or not self.milestone:
            return

        enrollment = frappe.get_doc("Student Path Enrollment", self.enrollment)
        milestone  = frappe.get_doc("Path Milestone", self.milestone)

        skill = milestone.get("skill")
        if not skill:
            return

        already_exists = frappe.db.exists(
            "Student Skill",
            {"student": enrollment.student, "skill": skill},
        )
        if already_exists:
            return

        frappe.get_doc(
            {
                "doctype":       "Student Skill",
                "student":       enrollment.student,
                "skill":         skill,
                "self_declared": 0,
                "current_level": "Beginner",
                "is_public":     1,
            }
        ).insert(ignore_permissions=True)

        frappe.db.commit()

        frappe.msgprint(
            f"Skill '<b>{skill}</b>' added to Skill Ledger.",
            indicator="blue",
            alert=True,
        )