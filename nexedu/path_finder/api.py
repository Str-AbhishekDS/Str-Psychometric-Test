# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt
#
# nexedu/path_finder/api/path_enrollment.py
# ─────────────────────────────────────────────────────────────────────────────
# All whitelisted APIs consumed by:
#   - student_path_enrollment.js
#   - path_progress_log.js
#   - career_path.js
#   - Any UI widget showing fit scores / path suggestions
# ─────────────────────────────────────────────────────────────────────────────

import frappe
from frappe.utils import now_datetime

from nexedu.path_finder.utils.milestone_engine import (
    build_milestone_rows_from_path,
    calculate_fit_score,
    get_top_path_suggestions,
    level_rank,
)


# ══════════════════════════════════════════════════════════════════════════════
# 1. CHECK PREREQUISITE SKILLS
#    Used by: student_path_enrollment.js, career_path.js live check
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def check_prerequisite_skills(student, career_path):
    """
    Compares the student's skills against:
        (a) Career Path → prerequisite_skills table
        (b) Career Path → path_milestone table (skills)

    Returns:
        status              : "clear" | "gap"
        readiness_percent   : float
        matched             : int   (count of fully matched skills)
        total_prerequisites : int
        matched_skills      : list  ← NEW (was missing in old code)
        partial_skills      : list
        missing_skills      : list

    Each item in the lists:
        { skill, required_level, current_level, is_prereq, recommended_path }
    """
    score_data = calculate_fit_score(student, career_path)



    total = score_data["total_skills"]
    matched = score_data["matched_count"]
    readiness = score_data["fit_score"]
    status = "clear" if (score_data["partial_count"] + score_data["missing_count"]) == 0 else "gap"

    return {
        "status"             : status,
        "readiness_percent"  : readiness,
        "matched"            : matched,
        "total_prerequisites": total,
        "matched_skills"     : score_data["matched_skills"],
        "partial_skills"     : score_data["partial_skills"],
        "missing_skills"     : score_data["missing_skills"],
    }





# ══════════════════════════════════════════════════════════════════════════════
# 2. ENROLL STUDENT
#    Used by: student_path_enrollment.js _do_enroll()
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def enroll_student(student, career_path, force_enroll=0, prereq_paths="[]"):
    """
    Creates a Student Path Enrollment document.
    The controller's after_insert will call build_milestone_rows_from_path
    (which auto-prepends prerequisite skills as milestone rows).

    prereq_paths is accepted but ignored here — the engine handles prereqs
    by reading the Career Path's prerequisite_skills table directly.

    Returns: { status: "success", enrollment: <name> }
    """
    import json

    # Prevent duplicate active enrollment
    existing = frappe.db.exists(
        "Student Path Enrollment",
        {"student": student, "career_path": career_path, "status": "Active"},
    )
    if existing:
        return {"status": "already_enrolled", "enrollment": existing}

    doc = frappe.get_doc({
        "doctype"    : "Student Path Enrollment",
        "student"    : student,
        "career_path": career_path,
        "status"     : "Active",
        "enrolled_at": now_datetime(),
        "current_milestone_order": 1,
        "force_enroll": int(force_enroll),
        "triggered_from": "API",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "success", "enrollment": doc.name}


# ══════════════════════════════════════════════════════════════════════════════
# 3. GET MILESTONE OVERVIEW
#    Used by: student_path_enrollment.js board + dialog
#             path_progress_log.js "View All Milestones" dialog
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_milestone_overview(enrollment):
    """
    Returns the full milestone list for the Journey board.

    milestone_idx = row.idx  (Frappe child-table autoincrement — replaces `order`)

    Also returns:
        total_count       : int  (prereq + path milestones)
        completed_count   : int
        prereq_count      : int
        prereq_completed  : int
        path_count        : int
        path_completed    : int
        completion_percent: float
        status_counts     : dict
    """
    doc = frappe.get_doc("Student Path Enrollment", enrollment)

    rows = sorted(doc.milestone_progress, key=lambda r: r.idx)

    status_counts   = {}
    milestones_out  = []
    prereq_count    = 0
    prereq_completed = 0
    path_count      = 0
    path_completed  = 0

    for row in rows:
        status = row.status or "Not Started"
        status_counts[status] = status_counts.get(status, 0) + 1

        is_prereq = bool(getattr(row, "is_prereq", 0))
        if is_prereq:
            prereq_count += 1
            if status in ("Completed", "Skipped"):
                prereq_completed += 1
        else:
            path_count += 1
            if status in ("Completed", "Skipped"):
                path_completed += 1

        milestones_out.append({
            "row_name"        : row.name,
            "milestone_title" : row.milestone_title,
            "milestone_type"  : row.milestone_type,
            "milestone_idx"   : row.idx,
            "skill"           : getattr(row, "skill", None),
            "required_skill_level": getattr(row, "required_skill_level", None),
            "status"          : status,
            "score"           : row.score,
            "started_on"      : str(row.started_on)   if getattr(row, "started_on", None)   else None,
            "completed_on"    : str(row.completed_at) if getattr(row, "completed_at", None) else None,
            "is_current"      : row.idx == (doc.current_milestone_order or 1),
            "is_prereq"       : is_prereq,
            "is_lock"         : bool(getattr(row, "is_lock", 0)),
            "is_skippable"    : not bool(getattr(row, "is_mandatory", 1)),
            "is_auto_skipped" : bool(getattr(row, "is_auto_skipped", 0)),
            # "topic"           : getattr(row, "topic", None),
            # "subtopic"        : getattr(row, "subtopic", None),
            "category"        : getattr(row, "category", None),
        })

    total_count     = prereq_count + path_count
    completed_count = prereq_completed + path_completed
    pct             = round((completed_count / total_count) * 100, 1) if total_count else 0

    return {
        "milestones"        : milestones_out,
        "completion_percent": doc.completion_percent or pct,
        "status_counts"     : status_counts,
        "total_count"       : total_count,
        "completed_count"   : completed_count,
        "prereq_count"      : prereq_count,
        "prereq_completed"  : prereq_completed,
        "path_count"        : path_count,
        "path_completed"    : path_completed,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 4. SKIP MILESTONE
#    Used by: student_path_enrollment.js board skip buttons
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def skip_milestone(enrollment, row_name):
    """
    Marks a specific milestone_progress row as Skipped
    and advances the enrollment to the next milestone.
    Only non-mandatory milestones can be skipped.
    """
    doc = frappe.get_doc("Student Path Enrollment", enrollment)

    target_row = None
    for row in doc.milestone_progress:
        if row.name == row_name:
            target_row = row
            break

    if not target_row:
        frappe.throw(f"Milestone row {row_name} not found in enrollment {enrollment}.")

    if target_row.is_mandatory:
        frappe.throw(f"Milestone '{target_row.milestone_title}' is mandatory and cannot be skipped.")

    target_row.status       = "Skipped"
    target_row.completed_at = now_datetime()

    # Advance to next milestone
    _advance_enrollment(doc, target_row.idx)

    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"success": True}


def _advance_enrollment(doc, completed_idx):
    """
    After a row is completed/skipped, find the next non-completed row
    and set it as In Progress. Updates current_milestone_order.
    """
    rows_sorted = sorted(doc.milestone_progress, key=lambda r: r.idx)
    set_next    = False

    for row in rows_sorted:
        if row.idx <= completed_idx:
            continue
        if row.status not in ("Completed", "Skipped"):
            row.status                    = "In Progress"
            doc.current_milestone_order   = row.idx
            set_next = True
            break

    if not set_next:
        doc.status = "Completed"

    doc._compute_completion_percent()


# ══════════════════════════════════════════════════════════════════════════════
# 5. GET ENROLLMENT FOR STUDENT + PATH
#    Used by: career_path.js to check if already enrolled
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_enrollment_for_student_path(student, career_path):
    """
    Returns the active enrollment name if student is already enrolled,
    else None.
    """
    result = frappe.db.get_value(
        "Student Path Enrollment",
        {"student": student, "career_path": career_path, "status": "Active"},
        "name",
    )
    return result or None


# ══════════════════════════════════════════════════════════════════════════════
# 6. GET MILESTONE COUNT SUMMARY
#    Used by: student_path_enrollment.js header display
#    Shows: "4 prereqs + 11 milestones = 15 total | X completed"
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_milestone_count_summary(enrollment):
    """
    Returns a summary dict for the count bar shown on enrollment form:
        {
            prereq_count      : 4,
            prereq_completed  : 2,
            path_count        : 11,
            path_completed    : 3,
            total_count       : 15,
            completed_count   : 5,
            completion_percent: 33.3,
            label             : "4 Prereqs + 11 Milestones = 15 Total | 5 Completed"
        }
    """
    overview = get_milestone_overview(enrollment)

    label = (
        f"{overview['prereq_count']} Prereqs"
        f" + {overview['path_count']} Milestones"
        f" = {overview['total_count']} Total"
        f" | {overview['completed_count']} Completed"
    )
    return {**overview, "label": label}


# ══════════════════════════════════════════════════════════════════════════════
# 7. GET PATH SUGGESTIONS (Fit Score based)
#    Used by: path suggestion widget / career_path page
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_path_suggestions(student, limit=5):
    """
    Returns top N career paths ranked by fit score for the given student.
    Excludes paths the student is already actively enrolled in.

    Returns list of:
        {
            career_path, path_name, target_role, difficulty_level,
            fit_score, matched_count, partial_count, missing_count,
            total_skills, estimated_duration, average_salary,
            success_stories,
            skill_tags: [{ skill, status: matched|partial|missing }]
        }
    """
    suggestions = get_top_path_suggestions(student, int(limit))

    # Get already-enrolled paths to exclude
    enrolled = frappe.get_all(
        "Student Path Enrollment",
        filters={"student": student, "status": "Active"},
        pluck="career_path",
    )
    enrolled_set = set(enrolled)

    result = []
    for s in suggestions:
        if s["career_path"] in enrolled_set:
            continue

        # Build flat skill_tags for UI chips
        skill_tags = []
        for sk in s.get("matched_skills", []):
            skill_tags.append({"skill": sk["skill"], "status": "matched"})
        for sk in s.get("partial_skills", []):
            skill_tags.append({"skill": sk["skill"], "status": "partial"})
        for sk in s.get("missing_skills", []):
            skill_tags.append({"skill": sk["skill"], "status": "missing"})

        result.append({
            "career_path"       : s["career_path"],
            "path_name"         : s["path_name"],
            "target_role"       : s["target_role"],
            "difficulty_level"  : s["difficulty_level"],
            "fit_score"         : s["fit_score"],
            "matched_count"     : s["matched_count"],
            "partial_count"     : s["partial_count"],
            "missing_count"     : s["missing_count"],
            "total_skills"      : s["total_skills"],
            "estimated_duration": s["estimated_duration"],
            "average_salary"    : s["average_salary"],
            "success_stories"   : s["success_stories"],
            "skill_tags"        : skill_tags[:8],  # cap for display
        })

    return result[:int(limit)]


# 8. GET ENROLLMENT MILESTONES FOR SELECT
#    Used by: path_progress_log.js milestone dropdown
#
#    Returns the milestone_progress child rows of an enrollment so the
#    Path Progress Log form can show them as a selectable list.
#    Each row is identified by its child table `name` (stored in PPL.milestone)
#    and displayed as "idx — title" in the dropdown.
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_enrollment_milestones_for_select(enrollment):
    """
    Returns all milestone_progress rows from a Student Path Enrollment,
    sorted by idx, formatted for the Path Progress Log milestone dropdown.

    Each item:
        {
            row_name       : str   ← child row `name`, stored as PPL.milestone
            milestone_idx  : int   ← sequence position (Frappe child idx)
            milestone_title: str
            milestone_type : str
            status         : str
            skill          : str | None
            required_skill_level: str | None
            is_prereq      : bool
            is_mandatory   : bool
            score          : float | None
            completed_at   : str | None
        }
    """
    doc  = frappe.get_doc("Student Path Enrollment", enrollment)
    rows = sorted(doc.milestone_progress, key=lambda r: r.idx)

    result = []
    for row in rows:
        result.append({
            "row_name"            : row.name,
            "milestone_idx"       : row.idx,
            "milestone_title"     : row.milestone_title or "",
            "milestone_type"      : getattr(row, "milestone_type", None),
            "status"              : row.status or "Not Started",
            "skill"               : getattr(row, "skill", None),
            "required_skill_level": getattr(row, "required_skill_level", None),
            "is_prereq"           : bool(getattr(row, "is_prereq", 0)),
            "is_mandatory"        : bool(getattr(row, "is_mandatory", 1)),
            "score"               : getattr(row, "score", None),
            "completed_at"        : str(row.completed_at) if getattr(row, "completed_at", None) else None,
        })
    return result


# ══════════════════════════════════════════════════════════════════════════════
# 9. COMPLETE MILESTONE (called from Path Progress Log on_update)
#    Internal use — not directly whitelisted; called from PPL controller
# ══════════════════════════════════════════════════════════════════════════════

def complete_milestone_in_enrollment(enrollment_name, milestone_row_name, score=None, ai_feedback=None):
    """
    Marks a milestone_progress row as Completed in the enrollment,
    advances the current pointer, and recomputes completion_percent.

    Called by PathProgressLog.on_update() after a log is saved.
    """
    doc = frappe.get_doc("Student Path Enrollment", enrollment_name)

    target_row = None
    for row in doc.milestone_progress:
        if row.name == milestone_row_name:
            target_row = row
            break

    if not target_row:
        # Fallback: match by source_milestone field
        source_milestone = frappe.db.get_value(
            "Path Progress Log", {"enrollment": enrollment_name, "name": milestone_row_name}, "milestone"
        )
        if source_milestone:
            for row in doc.milestone_progress:
                if getattr(row, "source_milestone", None) == source_milestone:
                    target_row = row
                    break

    if not target_row:
        frappe.log_error(
            f"Could not find milestone row {milestone_row_name} in enrollment {enrollment_name}",
            "PathFinder: complete_milestone_in_enrollment"
        )
        return

    target_row.status       = "Completed"
    target_row.completed_at = now_datetime()
    if score is not None:
        target_row.score = score
    if ai_feedback:
        target_row.ai_feedback = ai_feedback

    _advance_enrollment(doc, target_row.idx)
    doc.save(ignore_permissions=True)
    frappe.db.commit()