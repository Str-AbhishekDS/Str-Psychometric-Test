# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class Assessment(Document):

    def validate(self):
        self.validate_dates()
        self.calculate_total_marks()

    def validate_dates(self):
        if self.valid_from and self.valid_to:
            if self.valid_from >= self.valid_to:
                frappe.throw("Valid To must be after Valid From")

    def calculate_total_marks(self):
        total = 0
        for row in self.assessment_question:
            total += row.marks or 0
        self.total_marks = total