# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt

# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt
#
# nexedu/path_finder/doctype/career_path/career_path.py
# ─────────────────────────────────────────────────────────────────────────────
# CHANGES:
#   - before_save: removed `row.order = i` assignment
#     Frappe assigns idx automatically on child table save.
#     We no longer maintain a custom `order` field.
#   - career_path field on each milestone row is still set (useful for queries)
# ─────────────────────────────────────────────────────────────────────────────

import frappe
from frappe.model.document import Document


class CareerPath(Document):

    def before_save(self):
        """
        Set career_path backlink on each path_milestone row.
        idx is managed by Frappe — do NOT set row.order manually.
        """
        for row in self.path_milestone:
            row.career_path = self.name
            # DO NOT set row.order — Frappe handles idx automatically

    def validate(self):
        self._validate_prerequisite_skills()
        self._validate_milestone_skills()

    def _validate_prerequisite_skills(self):
        """Ensure no duplicate skill entries in prerequisite_skills table."""
        seen = set()
        for row in self.prerequisite_skills:
            if not row.skill:
                continue
            if row.skill in seen:
                frappe.throw(
                    f"Duplicate prerequisite skill: <b>{row.skill}</b>. "
                    "Each skill should appear only once in prerequisites."
                )
            seen.add(row.skill)

    def _validate_milestone_skills(self):
        """Warn (not throw) if a milestone has no skill linked."""
        # Just a soft check — milestones without skills are allowed
        # (e.g., project submission milestones)
        pass