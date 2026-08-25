# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class EducationalSkillRequirement(Document):
    def autoname(self):
        parts = []
        if self.stream:
            parts.append(self.stream)
        if self.course:
            parts.append(self.course)
        if self.department:
            parts.append(self.department)
        
        if parts:
            self.name = " - ".join(parts)
        else:
            self.name = frappe.generate_hash(length=10)

    def validate(self):
        # Prevent duplicate combinations of stream, course, department
        duplicate = frappe.db.exists(
            "Educational Skill Requirement",
            {
                "stream": self.stream or "",
                "course": self.course or "",
                "department": self.department or "",
                "name": ["!=", self.name]
            }
        )
        if duplicate:
            frappe.throw(
                "An Educational Skill Requirement already exists for this combination of Stream, Course, and Department."
            )
