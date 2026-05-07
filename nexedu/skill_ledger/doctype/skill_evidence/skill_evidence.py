"""
DocType: Skill Evidence
Purpose: A single piece of evidence (course, project, cert, etc.) that backs
         a Student Skill entry. On verification, the parent ledger is updated.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import today, now_datetime


class SkillEvidence(Document):
    def _update_counts(self):
        if not self.student_skill:
            return

        evidence_count = frappe.db.count(
            "Skill Evidence",
            {"student_skill": self.student_skill}
        )

        endorsement_count = frappe.db.count(
            "Skill Endorsement",
            {"student_skill": self.student_skill}
        )

        frappe.db.set_value(
            "Student Skill",
            self.student_skill,
            {
                "evidence_count": evidence_count,
                "endorsement_count": endorsement_count
            }
        )

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def before_save(self):
        if not self.evidence_date:
            self.evidence_date = today()

    # def on_submit(self):
    #     # Evidence submitted → set status to Pending if not already set
    #     if not self.verification_status:
    #         self.verification_status = "Pending"
    #         self.save(ignore_permissions=True)

    def after_insert(self):
        self._update_counts()                     # ✅ direct DB update
        frappe.db.commit()                        # ✅ ensure DB sync
        self._create_ledger_event("Evidence Added")

    def on_update(self):
        self.sync_status_to_parent()

        # Only act when status changes
        if not self.has_value_changed("verification_status"):
            return

        if self.verification_status == "Verified":
            self._update_last_demonstrated()

        # ✅ Update existing ledger entry instead of creating new one
        ledger_name = frappe.db.get_value(
            "Student Skill Ledger",
            {
                "reference_doctype": "Skill Evidence",
                "reference_name": self.name
            },
            "name"
        )

        if ledger_name:
            frappe.db.set_value(
                "Student Skill Ledger",
                ledger_name,
                {
                    "status": self.verification_status,
                    "event_type": "Verification",
                    "event_time": now_datetime()
                }
            )
    
    def sync_status_to_parent(self):
        if not self.student_skill:
            return

        # Get new status from Skill Evidence
        new_status = self.verification_status

        # -------------------------------
        # Update Student Skill (Doc A)
        # -------------------------------
        frappe.db.set_value(
            "Student Skill",
            self.student_skill,
            "status",
            new_status
        )

        # -------------------------------
        # Update Skill Ledger (Doc C)
        # -------------------------------
        ledger = frappe.db.get_value(
            "Student Skill Ledger",
            {"student_skill": self.student_skill},
            "name"
        )

        if ledger:
            frappe.db.set_value(
                "Student Skill Ledger",
                ledger,
                "status",
                new_status
            )
        
        
        # # When verification status changes to Verified/Rejected, refresh parent
        # if self.has_value_changed("verification_status"):
        #     self._create_ledger_event("Verification")
        #     self._refresh_parent()
        #     if self.verification_status == "Verified":
        #         self._update_last_demonstrated()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _refresh_parent(self):
        if self.student_skill:
            parent = frappe.get_doc("Student Skill", self.student_skill)
            parent.refresh_counts()

    def _update_last_demonstrated(self):
        frappe.db.set_value(
            "Student Skill",
            self.student_skill,
            "last_demonstrated",
            self.evidence_date,
        )

    def _create_ledger_event(self, event_type: str):
        if not self.student_skill:
            return
        ss = frappe.db.sql("""
            SELECT student, skill, current_level, evidence_count, endorsement_count
            FROM `tabStudent Skill`
            WHERE name = %s
        """, (self.student_skill,), as_dict=True)[0]
        if not ss:
            return
        frappe.get_doc(
            {
                "doctype": "Student Skill Ledger",
                "student": ss.student,
                "student_skill": self.student_skill,
                "skill": ss.skill,
                "skill_level": ss.current_level,
                "event_type": event_type,
                "evidence_count": ss.evidence_count,
                "endorsement_count": ss.endorsement_count,
                "event_time": now_datetime(),
                "status": self.verification_status,
                "reference_doctype": "Skill Evidence",
                "reference_name": self.name,
                "comment": self.description or "",
            }
        ).insert(ignore_permissions=True)


# ------------------------------------------------------------------
# Whitelisted API
# ------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def add_evidence(
    student_skill: str,
    evidence_type: str,
    evidence_date: str,
    description: str = "",
    reference_doctype: str = "",
    reference_name: str = "",
    document_url: str = "",
) -> str:
    """
    Creates a new Skill Evidence record.
    Returns the name of the created document.
    """
    doc = frappe.get_doc(
        {
            "doctype": "Skill Evidence",
            "student_skill": student_skill,
            "evidence_type": evidence_type,
            "evidence_date": evidence_date,
            "description": description,
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "document_url": document_url,
            "verification_status": "Pending",
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name


@frappe.whitelist(allow_guest=True)
def verify_evidence(evidence_name: str, status: str, remarks: str = ""):
    _check_verifier_role()

    doc = frappe.get_doc("Skill Evidence", evidence_name)
    doc.verification_status = status
    doc.verified_by = frappe.session.user
    doc.remarks = remarks
    doc.save(ignore_permissions=True)

    return {
        "status": "success",
        "message": f"Evidence {status.lower()} successfully",
        "evidence": {
            "name": doc.name,
            "verification_status": doc.verification_status,
            "verified_by": doc.verified_by
        }
    }


@frappe.whitelist(allow_guest=True)
def get_evidence_for_skill(student_skill: str) -> list:
    """Returns all evidence records for a given Student Skill."""
    return frappe.get_all(
        "Skill Evidence",
        filters={"student_skill": student_skill},
        fields=[
            "name", "evidence_type", "evidence_date", "verification_status",
            "verified_by", "description", "document_url", "reference_doctype",
            "reference_name",
        ],
        order_by="evidence_date desc",
    )


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _check_verifier_role():
    roles = frappe.get_roles(frappe.session.user)
    if "Skill Verifier" not in roles and "System Manager" not in roles:
        frappe.throw(
            "You do not have permission to verify evidence. "
            "Required role: Skill Verifier",
            frappe.PermissionError,
        )