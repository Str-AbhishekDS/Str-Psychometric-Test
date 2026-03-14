# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt
from nexedu.utils.skill_ledger import create_skill_ledger
import frappe
from frappe.model.document import Document


class SkillEndorsement(Document):

    def after_insert(self):
        self.update_endorsement_count()
        
        create_skill_ledger(
            student_skill=self.student_skill,
            event_type="Endorsement Added",
            reference_doctype="Skill Endorsement",
            reference_name=self.name
        )

    def on_update(self):
        self.update_endorsement_count()

    def update_endorsement_count(self):

        if not self.student_skill:
            return

        # Count endorsements for the skill
        count = frappe.db.count(
            "Skill Endorsement",
            {
                "student_skill": self.student_skill
            }
        )

        # Get the Student Skill record
        student_skill = frappe.get_doc("Student Skill", self.student_skill)

        # Update endorsement count
        student_skill.endorsement_count = count

        # Save the document
        student_skill.save(ignore_permissions=True)