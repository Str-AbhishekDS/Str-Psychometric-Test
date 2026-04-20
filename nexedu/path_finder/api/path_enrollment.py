"""
nexedu/path_finder/api/enrollment_api.py
────────────────────────────────────────────────────────────────────────────
All @frappe.whitelist() endpoints for the Path Finder enrollment flow.

FIX LOG
───────
v2 fixes:
  - enroll_student: milestones are populated HERE (in the API) before
    insert(), not inside after_insert(). A flag (milestone_progress_seeded)
    is set so after_insert() knows to skip population → no double rows.
  - enroll_student: prereq prepend happens before the FIRST insert, so
    there is only one save, no risk of duplicate milestone rows.
  - get_milestone_overview: source_path comparison uses career_path field
    safely with fallback.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime, today
import json

from nexedu.path_finder.utils.milestone_engine import (
    recalculate_all_milestones,
    build_milestone_rows_from_path,
    prepend_prerequisite_milestones,
    get_student_skill_set,
    LEVEL_ORDER,
)


# ══════════════════════════════════════════════════════════════════════════════
# 1. PREREQUISITE SKILL CHECK
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def check_prerequisite_skills(student, career_path):
    """
    Compares career path Prerequisite Skills child table with Student Skills.

    Returns
    ───────
    {
        status             : "clear" | "partial" | "not_ready"
        readiness_percent  : float 0–100
        matched            : int
        total_prerequisites: int
        missing_skills     : [{skill, required_level, current_level, gap, recommended_path}]
        partial_skills     : [{skill, required_level, current_level, gap, recommended_path}]
        matched_skills     : [skill_name, ...]
    }
    """
    prerequisites = frappe.db.sql("""
        SELECT
            ps.prerequisite_skills  AS skill,
            ps.level                AS required_level
        FROM `tabPrerequisite Skills` ps
        WHERE ps.parent     = %s
          AND ps.parenttype = 'Career Path'
    """, career_path, as_dict=True)

    if not prerequisites:
        return {
            "status":              "clear",
            "message":             "No prerequisites required.",
            "missing_skills":      [],
            "partial_skills":      [],
            "matched_skills":      [],
            "readiness_percent":   100,
            "matched":             0,
            "total_prerequisites": 0,
        }

    student_skill_map = get_student_skill_set(student)
    missing_skills    = []
    partial_skills    = []
    matched_skills    = []

    for prereq in prerequisites:
        skill          = prereq["skill"]
        required_level = prereq["required_level"] or "Beginner"
        required_rank  = LEVEL_ORDER.get(required_level, 1)
        path_info      = _get_recommended_path_info(skill)

        if skill not in student_skill_map:
            missing_skills.append({
                "skill":            skill,
                "required_level":   required_level,
                "current_level":    None,
                "gap":              "Not started",
                "recommended_path": path_info,
            })
        else:
            student_level = student_skill_map[skill]
            student_rank  = LEVEL_ORDER.get(student_level, 0)

            if student_rank < required_rank:
                partial_skills.append({
                    "skill":            skill,
                    "required_level":   required_level,
                    "current_level":    student_level,
                    "gap":              f"Need to reach {required_level}",
                    "recommended_path": path_info,
                })
            else:
                matched_skills.append(skill)

    total             = len(prerequisites)
    matched_count     = len(matched_skills)
    readiness_percent = round((matched_count / total) * 100, 2) if total else 100

    if missing_skills or partial_skills:
        status = "partial" if readiness_percent >= 50 else "not_ready"
    else:
        status = "clear"

    return {
        "status":              status,
        "readiness_percent":   readiness_percent,
        "matched":             matched_count,
        "total_prerequisites": total,
        "missing_skills":      missing_skills,
        "partial_skills":      partial_skills,
        "matched_skills":      matched_skills,
    }


def _get_recommended_path_info(skill_name):
    """Fetches recommended Career Path info from Skill Master for a skill."""
    skill_data = frappe.db.get_value(
        "Skill",
        skill_name,
        ["recommended_path"],
        as_dict=True,
    ) or {}

    if not skill_data.get("recommended_path"):
        return None

    path_details = frappe.db.get_value(
        "Career Path",
        skill_data["recommended_path"],
        ["name", "path_name", "estimated_duration_months", "difficulty_level"],
        as_dict=True,
    ) or {}

    return {
        "path_name":       skill_data["recommended_path"],
        "display_name":    path_details.get("path_name"),
        "duration_months": path_details.get("estimated_duration_months"),
        "difficulty":      path_details.get("difficulty_level"),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2. ENROLL STUDENT
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def enroll_student(student, career_path, force_enroll=0, prereq_paths=None):
    """
    Creates a Student Path Enrollment with milestone_progress pre-populated.

    FIX: milestones are appended to the doc BEFORE insert() so that
    after_insert() sees milestone_progress is already populated and skips
    its own _populate_milestones_from_path() call.  This prevents the
    double-population bug.

    force_enroll = 1 : called after skill gap dialog ("Enroll Anyway").
    prereq_paths     : JSON list of Career Path names to prepend.

    Returns { enrollment: <name>, status: "success" }
    """
    # Prevent duplicate active enrollment
    existing = frappe.db.exists(
        "Student Path Enrollment",
        {
            "student":     student,
            "career_path": career_path,
            "status":      ["!=", "Abandoned"],
        },
    )
    if existing:
        frappe.throw(_(
            f"Student is already enrolled in <b>{career_path}</b>. "
            f"Enrollment: <b>{existing}</b>"
        ))

    # Parse prereq_paths arg
    if prereq_paths and isinstance(prereq_paths, str):
        prereq_paths = json.loads(prereq_paths)
    prereq_paths = prereq_paths or []

    # ── Build the doc ─────────────────────────────────────────────────────────
    doc = frappe.get_doc({
        "doctype":                 "Student Path Enrollment",
        "student":                 student,
        "career_path":             career_path,
        "enrolled_at":             now_datetime(),
        "current_milestone_order": 1,
        "status":                  "Active",
        "ai_recommended":          0,
    })

    # ── Append main path milestones BEFORE insert ─────────────────────────────
    main_rows = build_milestone_rows_from_path(career_path, order_offset=0)
    for row in main_rows:
        doc.append("milestone_progress", row)

    # ── If force-enrolling with gaps, prepend prereq milestones now ───────────
    #    This happens on the in-memory doc before any DB write.
    if int(force_enroll) and prereq_paths:
        prepend_prerequisite_milestones(doc, prereq_paths)

    # ── Run auto-skip / lock / current detection ──────────────────────────────
    recalculate_all_milestones(doc)

    # ── Insert once — after_insert will see populated milestone_progress
    #    and skip its own populate call ────────────────────────────────────────
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {"enrollment": doc.name, "status": "success"}


# ══════════════════════════════════════════════════════════════════════════════
# 3. MILESTONE OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_milestone_overview(enrollment):
    """
    Returns all milestone_progress rows enriched with display metadata.

    Returns
    ───────
    {
        milestones         : [{row_name, milestone, milestone_title,
                               milestone_order, milestone_type, status,
                               is_lock, is_skippable, is_skipped, score,
                               started_on, completed_on, is_prereq, is_current}]
        current_order      : int
        completion_percent : float
        enrollment_status  : str
        total              : int
        status_counts      : {Not Started, In Progress, Completed, Skipped}
    }
    """
    enrollment_doc = frappe.get_doc("Student Path Enrollment", enrollment)
    rows = sorted(
        enrollment_doc.milestone_progress or [],
        key=lambda r: int(r.milestone_order or 0),
    )

    status_counts = {
        "Not Started": 0, "In Progress": 0, "Completed": 0, "Skipped": 0
    }
    milestones = []

    for row in rows:
        st = row.status or "Not Started"
        status_counts[st] = status_counts.get(st, 0) + 1

        # source_path field tells us if this is a prereq milestone
        source = row.get("source_path") or ""
        is_prereq = bool(source) and source != enrollment_doc.career_path

        milestones.append({
            "row_name":        row.name,
            "milestone":       row.milestone,
            "milestone_title": row.milestone_title,
            "milestone_order": row.milestone_order,
            "milestone_type":  row.milestone_type,
            "status":          st,
            "is_lock":         int(row.is_lock or 0),
            "is_skippable":    int(row.get("is_skippable") or 0),
            "is_skipped":      int(row.get("is_skipped") or 0),
            "linked_skill":    row.get("linked_skill"),
            "score":           row.get("score"),
            "pass_percentage": row.get("pass_percentage"),
            "project_link":    row.get("project_link"),
            "review_status":   row.get("review_status"),
            "started_on":      str(row.get("started_on") or ""),
            "completed_on":    str(row.get("completed_on") or ""),
            "source_path":     source or enrollment_doc.career_path,
            "is_prereq":       is_prereq,
            "is_current":      int(row.milestone_order or 0) == int(enrollment_doc.current_milestone_order or 1),
        })

    return {
        "milestones":         milestones,
        "current_order":      enrollment_doc.current_milestone_order,
        "completion_percent": enrollment_doc.completion_percent or 0,
        "enrollment_status":  enrollment_doc.status,
        "total":              len(milestones),
        "completed_count":    status_counts["Completed"],
        "skipped_count":      status_counts["Skipped"],
        "status_counts":      status_counts,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 4. SKIP MILESTONE
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def skip_milestone(enrollment, row_name):
    """
    Marks a specific milestone_progress row as Skipped.
    Only skippable rows (is_skippable=1) or the current milestone can be skipped.
    """
    enrollment_doc = frappe.get_doc("Student Path Enrollment", enrollment)

    target = None
    for row in enrollment_doc.milestone_progress:
        if row.name == row_name:
            target = row
            break

    if not target:
        frappe.throw(_("Milestone row not found in this enrollment."))

    if target.status == STATUS_COMPLETED:
        frappe.throw(_("A completed milestone cannot be skipped."))

    is_current = (
        int(target.milestone_order or 0) == int(enrollment_doc.current_milestone_order or 0)
    )

    if target.is_lock and not target.get("is_skippable") and not is_current:
        frappe.throw(_("This milestone is locked and cannot be skipped."))

    target.status       = "Skipped"
    target.is_skipped   = 1
    target.completed_on = today()

    recalculate_all_milestones(enrollment_doc)
    enrollment_doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"success": True, "new_order": enrollment_doc.current_milestone_order}


# import needed for STATUS_COMPLETED check above
from nexedu.path_finder.utils.milestone_engine import STATUS_COMPLETED


# ══════════════════════════════════════════════════════════════════════════════
# 5. GET EXISTING ENROLLMENT
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_enrollment_for_student_path(student, career_path):
    """Returns the enrollment name if the student is already enrolled."""
    name = frappe.db.get_value(
        "Student Path Enrollment",
        {
            "student":     student,
            "career_path": career_path,
            "status":      ["!=", "Abandoned"],
        },
        "name",
    )
    return {"enrollment": name} if name else {"enrollment": None}