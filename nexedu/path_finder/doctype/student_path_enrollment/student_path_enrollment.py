# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, today

from nexedu.path_finder.utils.milestone_engine import (
    recalculate_all_milestones,
    update_milestone_status,
    build_milestone_rows_from_path,
)


class StudentPathEnrollment(Document):

    # ══════════════════════════════════════════════════════════════════════════
    # LIFECYCLE HOOKS
    # ══════════════════════════════════════════════════════════════════════════

    def before_insert(self):
        self.enrolled_at              = now_datetime()
        self.current_milestone_order  = 1
        self.status                   = "Active"

    def after_insert(self):
        """
        Populate milestone_progress from Career Path milestones (if empty),
        then run full recalculation (auto-skip, unlock, set In Progress).
        """
        if not self.milestone_progress:
            self._populate_milestones_from_path()

        recalculate_all_milestones(self)
        self.save(ignore_permissions=True)

    def before_save(self):
        """
        Runs on every save. Enforces per-row completion rules.
        Skips recalculation here — that's triggered by explicit actions.
        """
        if not self.milestone_progress:
            return

        for row in self.milestone_progress:
            update_milestone_status(row, self)

        self._compute_completion_percent()

    def on_update(self):
        self._check_and_update_success_stories()

    def validate(self):
        for row in self.milestone_progress:
            # Guard locked rows
            if row.is_lock:
                if row.has_value_changed("status"):
                    frappe.throw(
                        f"Milestone <b>{row.milestone_title}</b> is locked "
                        "and cannot be changed."
                    )

    # ══════════════════════════════════════════════════════════════════════════
    # PRIVATE HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _populate_milestones_from_path(self):
        """
        Reads milestones from Career Path and creates milestone_progress rows.
        Uses build_milestone_rows_from_path from the engine so logic is DRY.
        """
        rows = build_milestone_rows_from_path(self.career_path, order_offset=0)
        for row_data in rows:
            self.append("milestone_progress", row_data)

    def _compute_completion_percent(self):
        """
        Computes completion_percent from milestone_progress rows.
        Only mandatory milestones count toward completion.
        """
        mandatory = [
            r for r in self.milestone_progress
            if r.get("is_mandatory") != 0  # default is mandatory
        ]
        if not mandatory:
            self.completion_percent = 0.0
            return

        done = sum(
            1 for r in mandatory
            if r.status in ("Completed", "Skipped")
        )
        self.completion_percent = round((done / len(mandatory)) * 100, 2)

        if self.completion_percent >= 100:
            self.status = "Completed"

    def _check_and_update_success_stories(self):
        """
        Increments success_stories on Career Path when enrollment
        transitions to Completed for the first time.
        Uses cache=False to get the real DB value before this save.
        """
        previous_status = frappe.db.get_value(
            "Student Path Enrollment",
            self.name,
            "status",
            cache=False,
        )

        if self.status == "Completed" and previous_status != "Completed":
            self._increment_success_stories()

    def _increment_success_stories(self):
        frappe.db.sql("""
            UPDATE `tabCareer Path`
            SET success_stories = IFNULL(success_stories, 0) + 1
            WHERE name = %s
        """, self.career_path)

        frappe.db.commit()

        frappe.msgprint(
            f"🎉 Path '<b>{self.career_path}</b>' completed! "
            "Success stories updated.",
            indicator="green",
            alert=True,
        )