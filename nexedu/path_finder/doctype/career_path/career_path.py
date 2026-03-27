# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CareerPath(Document):
    def before_save(self):
        for row in self.path_milestone:
            row.career_path = self.name
        for i, row in enumerate(self.path_milestone, start=1):
            row.order = i

