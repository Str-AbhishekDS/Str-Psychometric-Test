# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FeedbackForm(Document):
	def validate(self):

		if self.is_active:

			forms = frappe.get_all(
				"Feedback Form",
				filters={
					"module_type": self.module_type,
					"name": ["!=", self.name]
				},
				fields=["name"]
			)

			for form in forms:
				frappe.db.set_value("Feedback Form", form.name, "is_active", 0)