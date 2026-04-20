"""
DocType: Skill Endorsement
Purpose: An endorsement from a Mentor, Industry professional, Professor, or Peer
         for a student's skill at a specific level.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class SkillEndorsement(Document):
    
    
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

    def before_insert(self):
        if not self.endorsed_at:
            self.endorsed_at = now_datetime()
        self._prevent_duplicate()

    def after_insert(self):
        self._update_counts()        # ✅ update first
        frappe.db.commit()           # ✅ force DB write
        self._create_ledger_event()  # ✅ now correct values

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _prevent_duplicate(self):
        """One endorser can only endorse the same student skill once."""
        exists = frappe.db.exists(
            "Skill Endorsement",
            {
                "student_skill": self.student_skill,
                "endorsed_by": self.endorsed_by,
            },
        )
        if exists:
            frappe.throw(
                f"{self.endorsed_by} has already endorsed this skill.",
                frappe.DuplicateEntryError,
            )

    def _refresh_parent(self):
        if self.student_skill:
            parent = frappe.get_doc("Student Skill", self.student_skill)
            parent.refresh_counts()

    def _create_ledger_event(self):
        ss = frappe.db.get_value(
            "Student Skill",
            self.student_skill,
            ["student", "skill", "evidence_count", "endorsement_count"],
            as_dict=True,
        )
        if not ss:
            return
        frappe.get_doc(
            {
                "doctype": "Student Skill Ledger",
                "student": ss.student,
                "student_skill": self.student_skill,
                "skill": ss.skill,
                "skill_level": self.endorsed_level,
                "event_type": "Endorsement Added",
                "evidence_count": ss.evidence_count,
                "endorsement_count": ss.endorsement_count,
                "event_time": self.endorsed_at,
                "reference_doctype": "Skill Endorsement",
                "reference_name": self.name,
                "comment": self.comment or "",
            }
        ).insert(ignore_permissions=True)


# ------------------------------------------------------------------
# Whitelisted API
# ------------------------------------------------------------------

@frappe.whitelist()
def add_endorsement(
    student_skill: str,
    endorsed_level: str,
    endorser_role: str,
    endorser_company: str = "",
    comment: str = "",
) -> str:
    """
    Creates a new Skill Endorsement for the currently logged-in user.
    Returns the name of the created document.
    """
    doc = frappe.get_doc(
        {
            "doctype": "Skill Endorsement",
            "student_skill": student_skill,
            "endorsed_level": endorsed_level,
            "endorsed_by": frappe.session.user,
            "endorser_role": endorser_role,
            "endorser_company": endorser_company,
            "endorsed_at": now_datetime(),
            "comment": comment,
        }
    )
    doc.insert()
    return doc.name


@frappe.whitelist()
def get_endorsements_for_skill(student_skill: str) -> list:
    """Returns all endorsements for a given Student Skill."""
    return frappe.get_all(
        "Skill Endorsement",
        filters={"student_skill": student_skill},
        fields=[
            "name", "endorsed_level", "endorsed_by", "endorser_role",
            "endorser_company", "endorsed_at", "comment",
        ],
        order_by="endorsed_at desc",
    )