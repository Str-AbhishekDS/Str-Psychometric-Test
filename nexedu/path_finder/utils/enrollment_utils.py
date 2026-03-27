import frappe
from frappe import _
from pathfinder.utils.milestone_engine import recalculate_all_milestones


@frappe.whitelist()
def enroll_in_prerequisite_path(career_path, student, triggered_from_enrollment=None):
    """
    Called from skill gap popup button.
    Creates Student Enrollment for the prerequisite path.
    Does NOT redirect — returns status to client.
    """
    # Check if already enrolled
    existing = frappe.db.exists("Student Enrollment", {
        "student": student,
        "career_path": career_path,
        "docstatus": ["!=", 2]
    })
    if existing:
        return {
            "status": "already_enrolled",
            "enrollment": existing,
            "message": _("Already enrolled in this path.")
        }

    # Create enrollment
    doc = frappe.new_doc("Student Enrollment")
    doc.student          = student
    doc.career_path      = career_path
    doc.enrollment_date  = frappe.utils.today()
    doc.is_prerequisite  = 1
    doc.triggered_from   = triggered_from_enrollment

    # Populate milestones from Career Path
    path_doc = frappe.get_doc("Career Path", career_path)
    for m in path_doc.milestones:
        doc.append("milestone_progress", {
            "milestone":       m.name,
            "milestone_title": m.milestone_title,
            "milestone_order": m.order,
            "milestone_type":  m.milestone_type,
            "linked_skill":    m.linked_skill,
            "is_skippable":    m.is_skippable,
            "assessment":      m.assessment,
            "pass_percentage": m.pass_percentage or 50,
            "status":          "Not Started",
            "is_locked":       1
        })

    doc.insert(ignore_permissions=True)

    # Run auto-skip + lock logic
    recalculate_all_milestones(doc)
    doc.save(ignore_permissions=True)

    return {
        "status":     "enrolled",
        "enrollment": doc.name,
        "message":    _(f"Successfully enrolled in {path_doc.path_title}.")
    }


@frappe.whitelist()
def get_path_preview(career_path):
    """
    Returns lightweight path info for the skill gap popup card.
    Student sees this BEFORE deciding to enroll.
    """
    doc = frappe.get_doc("Career Path", career_path)

    skills_covered = list({
        m.linked_skill for m in doc.milestones if m.linked_skill
    })
    skill_names = []
    for s in skills_covered[:4]:
        name = frappe.db.get_value("Skill", s, "skill_name")
        if name:
            skill_names.append(name)

    return {
        "title":           doc.path_title,
        "description":     doc.description or "",
        "milestone_count": len(doc.milestones),
        "skills_covered":  skill_names,
        "duration":        doc.estimated_duration or "—"
    }


@frappe.whitelist()
def check_skill_gap(career_path, student):
    """
    Returns which prerequisite skills the student is missing
    and the learning path for each missing skill.
    Called before showing enrollment dialog.
    """
    path_doc     = frappe.get_doc("Career Path", career_path)
    prereq_skills = [row.skill for row in path_doc.prerequisite_skills]

    if not prereq_skills:
        return {"has_gap": False, "match_percent": 100, "missing": []}

    student_skills = frappe.get_all(
        "Student Skill",
        filters={"parent": student},
        pluck="skill"
    )

    missing = []
    for skill in prereq_skills:
        if skill not in student_skills:
            learning_path = frappe.db.get_value("Skill", skill, "learning_path")
            path_title    = ""
            if learning_path:
                path_title = frappe.db.get_value("Career Path", learning_path, "path_title")
            missing.append({
                "skill":        skill,
                "skill_name":   frappe.db.get_value("Skill", skill, "skill_name"),
                "learning_path": learning_path,
                "path_title":   path_title or "No path available"
            })

    matched       = len(prereq_skills) - len(missing)
    match_percent = round((matched / len(prereq_skills)) * 100)

    return {
        "has_gap":       len(missing) > 0,
        "match_percent": match_percent,
        "matched":       matched,
        "total":         len(prereq_skills),
        "missing":       missing
    }