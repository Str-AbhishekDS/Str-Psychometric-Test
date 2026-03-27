# Copyright (c) 2026, Stride nex
import frappe
from frappe.model.document import Document

from nexedu.path_finder.utils.milestone_engine import recalculate_all_milestones


class AssessmentSubmission(Document):

    def on_submit(self):
        """
        When assessment is submitted:
        → Update all related enrollments
        → Recalculate full milestone engine
        """

        enrollments = frappe.get_all(
            "Student Path Enrollment",   # ✅ USE YOUR FINAL DOCTYPE NAME
            filters={
                "student": self.student,
                "docstatus": ["!=", 2]
            },
            pluck="name"
        )

        for enr_name in enrollments:
            doc = frappe.get_doc("Student Path Enrollment", enr_name)

            # 🔥 ONE SINGLE CALL (handles everything)
            recalculate_all_milestones(doc)

            doc.save(ignore_permissions=True)