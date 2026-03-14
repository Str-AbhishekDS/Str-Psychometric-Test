# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt
from nexedu.utils.skill_ledger import create_skill_ledger

import frappe
from frappe.model.document import Document
import hashlib
import json


class StudentSkill(Document):

    def before_save(self):
        self.generate_ledger_hash()

    def generate_ledger_hash(self):

        evidence = frappe.get_all(
            "Skill Evidence",
            filters={"student_skill": self.name},
            fields=["name", "evidence_date", "verification_status"],
            order_by="evidence_date asc"
        )

        data = frappe.as_json(evidence)

        self.ledger_hash = hashlib.sha256(data.encode()).hexdigest()

    def after_insert(self):

        create_skill_ledger(
            student_skill=self.name,
            event_type="Self Declared"
        )
        
    # def on_update(self):

    #     if self.has_value_changed("current_level"):

    #         create_skill_ledger(
    #             student_skill=self.name,
    #             event_type="Skill Level Updated"
    #         )