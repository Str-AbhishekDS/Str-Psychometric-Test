import frappe

def create_skill_ledger(student_skill, event_type, status=None, reference_doctype=None, reference_name=None):

    skill_doc = frappe.get_doc("Student Skill", student_skill)

    ledger = frappe.get_doc({
        "doctype": "Student Skill Ledger",
        "student": skill_doc.student,
        "student_skill": skill_doc.name,
        "skill": skill_doc.skill,
        "skill_level": skill_doc.current_level,
        "status": status,
        "evidence_count": skill_doc.evidence_count,
        "endorsement_count": skill_doc.endorsement_count,
        "event_type": event_type,
        "reference_doctype": reference_doctype,
        "reference_name": reference_name,
        "event_time": frappe.utils.now()
    })

    ledger.insert(ignore_permissions=True)