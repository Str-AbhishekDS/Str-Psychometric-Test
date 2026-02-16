# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class StrPsychometricTest(Document):
    def validate(self):
        self.validate_questions_subject()

    def validate_questions_subject(self):
        if not self.subject:
            frappe.throw("Please select Subject")

        for row in self.questions:
            question_subject = frappe.db.get_value(
                "Question",
                row.question,
                "subject"
            )

            if question_subject != self.subject:
                frappe.throw(
                    f"Question {row.question} does not belong to Subject {self.subject}"
                )
	
    def validate_duplicate_subjects(self):
        seen = []
        for row in self.subjects:
            if row.subject in seen:
                frappe.throw(f"Duplicate Subject not allowed: {row.subject}")
            seen.append(row.subject)
