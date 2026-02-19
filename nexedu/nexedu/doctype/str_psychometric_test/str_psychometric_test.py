# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class StrPsychometricTest(Document):
    def validate(self):
        self.validate_questions_subject()

    def validate_questions_subject(self):

        if not self.psychometric_test_subject:
            frappe.throw("Please add at least one Subject")

        selected_subjects = [
            d.subject for d in self.psychometric_test_subject
        ]

        for row in self.str_psychometric_test_question:
            if row.psychometric_test_subject not in selected_subjects:
                frappe.throw(
                    f"Question '{row.question}' does not belong to selected subjects."
                )

	
    def validate_duplicate_subjects(self):
        seen = []
        for row in self.subjects:
            if row.subject in seen:
                frappe.throw(f"Duplicate Subject not allowed: {row.subject}")
            seen.append(row.subject)
