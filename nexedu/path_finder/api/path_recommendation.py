import frappe

def create_ai_enrollment(student, best_path):
    doc = frappe.get_doc({
        "doctype": "Student Path Enrollment",
        "student": student,
        "career_path": best_path,
        "ai_recommended": 1
    })
    doc.insert(ignore_permissions=True)
    return doc.name