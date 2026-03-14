# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt
from nexedu.utils.skill_ledger import create_skill_ledger
import frappe
from frappe.model.document import Document


class SkillEvidence(Document):

    def after_insert(self):
        self.update_student_skill()
        
        create_skill_ledger(
            student_skill=self.student_skill,
            event_type="Evidence Added",
            status=self.verification_status,
            reference_doctype="Skill Evidence",
            reference_name=self.name
        )


    def on_update(self):
        self.update_student_skill()

        if self.has_value_changed("verification_status") and self.verification_status in ["Verified", "Rejected"]:

            create_skill_ledger(
                student_skill=self.student_skill,
                event_type="Verification",
                status=self.verification_status,
                reference_doctype="Skill Evidence",
                reference_name=self.name
            )

    def update_student_skill(self):

        if not self.student_skill:
            return

        # Get Student Skill document
        student_skill = frappe.get_doc("Student Skill", self.student_skill)

        # Count verified evidence
        count = frappe.db.count(
            "Skill Evidence",
            {
                "student_skill": self.student_skill,
                "verification_status": "Verified"
            }
        )

        # Update fields
        student_skill.evidence_count = count

        if self.evidence_date:
            student_skill.last_demonstrated = self.evidence_date

        # Save changes
        student_skill.save(ignore_permissions=True)
        
   

        