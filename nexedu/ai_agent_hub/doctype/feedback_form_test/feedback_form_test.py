# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FeedbackFormTest(Document):
    def on_submit(self):

        module_type = frappe.db.get_value("Feedback Form", self.feedback_form, "module_type")

        doc = frappe.new_doc("Feedback Response")
        doc.feedback_test = self.name
        doc.feedback_form = self.feedback_form
        doc.user = frappe.session.user
        doc.submitted_date = self.date
        doc.module_type = module_type

        for response in self.feedback_answer:

            doc.append("feedback_answers", {
                "question" : response.question,
                "answer": response.answer
            })

        doc.insert(ignore_permissions=True)
        doc.submit()

        