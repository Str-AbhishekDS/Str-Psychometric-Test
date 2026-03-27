import frappe
from frappe import _

from nexedu.path_finder.utils.milestone_engine import recalculate_all_milestones


# 🔹 SKILL GAP
@frappe.whitelist()
def get_skill_gap(student, career_path):

    if not student or not career_path:
        frappe.throw(_("Student and Career Path are required"))

    required_skills = frappe.get_all(
        "Path Milestone",
        filters={"career_path": career_path},
        pluck="linked_skill"
    )

    required_skills = list(set([s for s in required_skills if s]))

    student_skills = frappe.get_all(
        "Student Skill",
        filters={"parent": student},
        pluck="skill"
    )

    student_skills = list(set(student_skills))

    missing = list(set(required_skills) - set(student_skills))

    total = len(required_skills)

    match_percent = ((total - len(missing)) / total * 100) if total else 0

    return {
        "missing_skills": missing,
        "match_percent": round(match_percent, 2)
    }


# 🔹 ENROLL WITH PREREQUISITES
@frappe.whitelist()
def enroll_with_prerequisites(student, career_path):

    if not student or not career_path:
        frappe.throw(_("Student and Career Path are required"))

    # 🔹 Skill Gap
    gap = get_skill_gap(student, career_path)
    missing_skills = gap.get("missing_skills", [])

    # 🔹 Get prerequisite paths
    prereq_paths = []
    for skill in missing_skills:
        path = frappe.db.get_value("Skill", skill, "mapped_career_path")
        if path:
            prereq_paths.append(path)
        else:
            frappe.logger().warning(f"No path mapped for skill: {skill}")

    prereq_paths = list(set(prereq_paths))

    try:
        # 🔹 Create Enrollment
        enrollment = frappe.new_doc("Student Path Enrollment")
        enrollment.student = student
        enrollment.career_path = career_path

        enrollment.insert(ignore_permissions=True)

        # 🔹 Build Milestones
        build_combined_milestones(enrollment, prereq_paths)

        # 🔹 Run Engine
        recalculate_all_milestones(enrollment)

        enrollment.save(ignore_permissions=True)

        frappe.db.commit()

        return {
            "status": "success",
            "enrollment": enrollment.name
        }

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Enrollment Failed")
        frappe.throw(_("Enrollment failed. Please try again."))


# 🔹 BUILD COMBINED MILESTONES
def build_combined_milestones(enrollment, prereq_paths):

    def add_milestones(path_name, is_prerequisite):

        milestones = frappe.get_all(
            "Path Milestone",
            filters={"career_path": path_name},
            fields=[
                "name",
                "milestone_title",
                "order",
                "milestone_type",
                "linked_skill",
                "is_skippable",
                "assessment",
                "pass_percentage"
            ],
            order_by="order asc"
        )

        for m in milestones:

            # 🔴 Prevent duplicate skill
            exists = any(
                row.linked_skill == m.linked_skill
                for row in enrollment.milestone_progress
            )

            if exists:
                continue

            enrollment.append("milestone_progress", {
                "milestone": m.name,
                "milestone_title": m.milestone_title,
                "milestone_order": m.order,
                "milestone_type": m.milestone_type,
                "linked_skill": m.linked_skill,
                "is_prerequisite": is_prerequisite,
                "is_skippable": m.is_skippable,
                "assessment": m.assessment,
                "pass_percentage": m.pass_percentage or 50,
                "status": "Not Started",
                "is_locked": 1
            })

    # 🔹 Add prerequisite first
    for path in prereq_paths:
        add_milestones(path, True)

    # 🔹 Add main path
    add_milestones(enrollment.career_path, False)