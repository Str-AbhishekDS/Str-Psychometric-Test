import frappe
from frappe import _
from nexedu.path_finder.api.path_enrollment import (
    check_prerequisite_skills
)


# def create_ai_enrollment(student, best_path):
#     doc = frappe.get_doc({
#         "doctype": "Student Path Enrollment",
#         "student": student,
#         "career_path": best_path,
#         "ai_recommended": 1
#     })
#     doc.insert(ignore_permissions=True)
#     return doc.name


@frappe.whitelist()
def get_top_path_suggestions(student, limit=5):

    enrolled_paths = frappe.get_all(
        "Student Path Enrollment",
        filters={
            "student": student,
            "status": ["!=", "Abandoned"]
        },
        pluck="career_path"
    )

    career_paths = frappe.get_all(
        "Career Path",
        filters={"is_active": 1},
        fields=[
            "name",
            "path_name",
            "target_role"
        ]
    )

    suggestions = []

    for path in career_paths:

        if path.name in enrolled_paths:
            continue

        result = check_prerequisite_skills(
            student,
            path.name
        )

        total = result.get("total_prerequisites", 0)
        matched = len(result.get("matched_skills", []))
        partial = len(result.get("partial_skills", []))
        missing = len(result.get("missing_skills", []))

        fit_score = round(
            (
                matched +
                (partial * 0.5)
            ) / total * 100,
            2
        ) if total else 100

        skill_tags = []

        for s in result.get("matched_skills", []):
            skill_tags.append({
                "skill": s,
                "status": "matched"
            })

        for s in result.get("partial_skills", []):
            skill_tags.append({
                "skill": s["skill"],
                "status": "partial"
            })

        for s in result.get("missing_skills", []):
            skill_tags.append({
                "skill": s["skill"],
                "status": "missing"
            })

        suggestions.append({
            "career_path": path.name,
            "path_name": path.path_name,
            "target_role": path.target_role,
            "fit_score": fit_score,
            "matched_count": matched,
            "missing_count": missing,
            "missing_skills": result.get("missing_skills", []),
            "skill_tags": skill_tags
        })

    suggestions.sort(
        key=lambda x: x["fit_score"],
        reverse=True
    )

    return suggestions[:limit]


@frappe.whitelist()
def get_best_path(student):

    paths = get_top_path_suggestions(student, 1)

    return paths[0] if paths else {}


@frappe.whitelist()
def get_recommended_paths(student):

    paths = get_top_path_suggestions(student, 6)

    return paths[1:6]


@frappe.whitelist()
def get_path_details(career_path):

    doc = frappe.get_doc(
        "Career Path",
        career_path
    )

    return {
        "path_name": doc.path_name,
        "difficulty_level": doc.difficulty_level,
        "estimated_duration":
            doc.estimated_duration_months,
        "average_salary":
            doc.average_salary_lpa
    }


@frappe.whitelist()
def get_path_dashboard(student):

    suggestions = get_top_path_suggestions(
        student,
        6
    )

    return {
        "best_path":
            suggestions[0]
            if suggestions else {},

        "recommended_paths":
            suggestions[1:6],

        "ai_suggestion":
            get_ai_path_suggestion(student)
    }


@frappe.whitelist()
def get_ai_path_suggestion(student):

    top = get_top_path_suggestions(student, 1)

    if not top:
        return {}

    best = top[0]

    missing = best.get("missing_skills", [])

    next_skill = (
        missing[0]["skill"]
        if missing else None
    )

    return {
        "career_path": best["career_path"],
        "path_name": best["path_name"],
        "suggested_skill": next_skill,
        "message":
            f"Based on your profile, "
            f"add {next_skill} "
            f"to improve your fit score."
    }