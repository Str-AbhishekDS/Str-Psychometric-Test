# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt
#
# nexedu/path_finder/doctype/student_path_enrollment/student_path_enrollment.py
# ─────────────────────────────────────────────────────────────────────────────

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from nexedu.path_finder.utils.milestone_engine import (
    build_milestone_rows_from_path,
    recalculate_all_milestones,
    update_milestone_status,
)


class StudentPathEnrollment(Document):

    # ══════════════════════════════════════════════════════════════════════════
    # LIFECYCLE HOOKS
    # ══════════════════════════════════════════════════════════════════════════

    def before_insert(self):
        self.enrolled_at             = now_datetime()
        # self.current_milestone_order = 1
        if self.status != "Generating":
            self.status              = "Active"

    def after_insert(self):
        """
        On first insert:
        1. Build milestone_progress rows:
           - Section A: Prerequisite Skills (from career_path.prerequisite_skills table)
             → auto-complete rows where student already has the verified skill
           - Section B: Path Milestones (from career_path.path_milestone table)
             → auto-complete rows where student already has the verified skill
        2. Recalculate statuses (find first non-completed → In Progress)
        3. Compute initial completion_percent and skill_match_percent
        4. Save updated document

        The combined count (prereq rows + path milestone rows) is the total
        shown in the UI as "4 Prereqs + 11 Milestones = 15 Total".
        """
        if self.status == "Generating":
            return

        if not self.milestone_progress:
            self._populate_milestones_from_path()

        recalculate_all_milestones(self)
        self._compute_completion_percent()
        self._compute_skill_match_percent()
        self.save(ignore_permissions=True)

    def before_save(self):
        """
        On every save: enforce per-row rules, recompute percent.
        """
        if self.status == "Active":
            other_active = frappe.get_all(
                "Student Path Enrollment",
                filters={
                    "student": self.student,
                    "status": "Active",
                    "name": ["!=", self.name or ""]
                },
                fields=["name"]
            )
            for other in other_active:
                frappe.db.set_value("Student Path Enrollment", other.name, "status", "Paused")
                frappe.clear_document_cache("Student Path Enrollment", other.name)

        if self.status == "Generating" or not self.milestone_progress:
            return

        for row in self.milestone_progress:
            update_milestone_status(row, self)

        self._compute_completion_percent()

    def on_update(self):
        self._check_and_update_success_stories()

    def validate(self):
        # Enforce milestone skill uniqueness to prevent duplication
        seen_skills = set()
        for row in self.milestone_progress:
            if row.skill:
                skill_key = row.skill.lower().strip()
                if skill_key in seen_skills:
                    frappe.throw(
                        f"Duplicate milestone skill '<b>{row.skill}</b>' found in progress. "
                        f"Each skill must have exactly one milestone per enrollment path."
                    )
                seen_skills.add(skill_key)

        for row in self.milestone_progress:
            if getattr(row, "is_lock", 0) and row.has_value_changed("status"):
                frappe.throw(
                    f"Milestone <b>{row.milestone_title}</b> is locked and cannot be changed."
                )

    # ══════════════════════════════════════════════════════════════════════════
    # PUBLIC
    # ══════════════════════════════════════════════════════════════════════════

    def _compute_completion_percent(self):
        """
        completion_percent = completed_mandatory / total_mandatory * 100

        Both prereq skill rows AND path milestone rows count toward the total.
        A prereq row that was auto-skipped (student already has skill) is
        already set to status="Completed" by build_milestone_rows_from_path,
        so it counts as done automatically.
        """
        mandatory = [
            r for r in self.milestone_progress
            if getattr(r, "is_mandatory", 1) != 0
        ]
        if not mandatory:
            self.completion_percent = 0.0
            return

        done = sum(1 for r in mandatory if r.status in ("Completed", "Skipped"))
        self.completion_percent = round((done / len(mandatory)) * 100, 2)

        if self.completion_percent >= 100:
            self.status = "Completed"

    def _compute_skill_match_percent(self):
        """
        skill_match_percent = how many skills in this path the student already has
        (regardless of completion). Saved as a field on the enrollment for quick display.
        """
        from nexedu.path_finder.utils.milestone_engine import calculate_fit_score
        score_data = calculate_fit_score(self.student, self.career_path)
        self.skill_match_percent = score_data["fit_score"]

    # ══════════════════════════════════════════════════════════════════════════
    # PRIVATE HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _populate_milestones_from_path(self):
        """
        Calls milestone_engine.build_milestone_rows_from_path which returns:
            [prereq_skill_rows..., path_milestone_rows...]

        Frappe assigns idx sequentially as rows are appended.
        We do NOT set an `order` field — idx IS the order.
        """
        rows = build_milestone_rows_from_path(
            career_path=self.career_path,
            student=self.student,
        )
        for row_data in rows:
            self.append("milestone_progress", row_data)

        # Populate milestone checklist points from template
        self.milestone_points = []
        path_milestones = frappe.get_all(
            "Path Milestone",
            filters={"parent": self.career_path, "parentfield": "path_milestone"},
            fields=["milestone_title", "milestone_points"]
        )
        pm_map = {pm.milestone_title: pm.milestone_points for pm in path_milestones if pm.milestone_points}

        for row in self.milestone_progress:
            pm_points_text = pm_map.get(row.milestone_title)
            if not pm_points_text:
                continue

            points = [p.strip() for p in pm_points_text.split("\n") if p.strip()]
            point_status = "Completed" if row.status == "Completed" else "Not Started"
            for p in points:
                self.append("milestone_points", {
                    "milestone_title": row.milestone_title,
                    "point_title": p,
                    "status": point_status
                })

    def _check_and_update_success_stories(self):
        previous_status = frappe.db.get_value(
            "Student Path Enrollment", self.name, "status", cache=False,
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
            f"🎉 Path '<b>{self.career_path}</b>' completed! Success stories updated.",
            indicator="green",
            alert=True,
        )