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
from frappe.utils import getdate, add_days, formatdate, today

from frappe.utils.pdf import get_pdf


from nexedu.path_finder.utils.milestone_engine import (
    build_milestone_rows_from_path,
    calculate_fit_score,
    get_top_path_suggestions,
    level_rank,
)

"""
career_path_api.py

Add this file to your app, e.g.:
    your_app/your_app/api/career_path.py

Endpoints exposed:
    GET /api/method/your_app.api.career_path.get_student_career_path
    GET /api/method/your_app.api.career_path.get_career_path_html   (preview in browser)
    GET /api/method/your_app.api.career_path.get_career_path_pdf    (download as PDF)

Template expected at:
    your_app/your_app/templates/career_path_pdf.html
(i.e. inside your app's `templates` folder, so frappe.render_template can find it
by the "app_name/templates/xxx.html" convention)
"""

# ---------------------------------------------------------------
# Top skill gaps for a college
# ---------------------------------------------------------------
@frappe.whitelist(allow_guest=True)
def get_top_skill_gaps(college):
    if not college:
        frappe.throw("college is required")

    if not frappe.db.exists("College", college):
        frappe.throw(f"College '{college}' not found")

    results = frappe.db.sql(
        """
        SELECT
            smp.linked_skill AS skill,
            sk.skill_name AS skill_name,
            COUNT(*) AS gap_count
        FROM `tabStudent Milestone Progress` smp
        INNER JOIN `tabStudent Path Enrollment` spe
            ON smp.parent = spe.name
        INNER JOIN `tabStudent` s
            ON spe.student = s.name
        LEFT JOIN `tabSkill` sk
            ON smp.linked_skill = sk.name
        WHERE
            s.college = %(college)s
            AND smp.is_skippable = 0
            AND smp.status != 'Completed'
            AND smp.linked_skill IS NOT NULL
            AND smp.linked_skill != ''
        GROUP BY smp.linked_skill
        ORDER BY gap_count DESC
        LIMIT 10
        """,
        {"college": college},
        as_dict=True,
    )

    return {
        "college": college,
        "top_skill_gaps": results,
    }
# @frappe.whitelist()
# def get_student_career_path(student):
#     """
#     Returns:
#     - Active career path details if student has an active enrollment.
#     - Generating status if AI generation is in progress.
#     - Failed status if AI generation failed (Paused, no milestones).
#     - Best suggested career path otherwise.
#     """
#     active_enrollment = frappe.db.exists(
#         "Student Path Enrollment",
#         {"student": student, "status": "Active"}
#     )
#     if active_enrollment:
#         return {"type": "active_plan", "data": get_active_plan(student)}

#     generating_enrollment = frappe.db.exists(
#         "Student Path Enrollment",
#         {"student": student, "status": "Generating"}
#     )
#     if generating_enrollment:
#         career_path = frappe.db.get_value(
#             "Student Path Enrollment", generating_enrollment, "career_path"
#         )
#         return {"type": "generating", "career_path": career_path}

#     # Check for failed AI generation (Paused status with no milestones generated)
#     paused_failed_enrollment = frappe.db.exists(
#         "Student Path Enrollment",
#         {"student": student, "status": "Paused"}
#     )
#     if paused_failed_enrollment:
#         enr_doc = frappe.get_doc("Student Path Enrollment", paused_failed_enrollment)
#         if not enr_doc.milestone_progress:
#             return {
#                 "type": "failed",
#                 "career_path": enr_doc.career_path,
#                 "enrollment": enr_doc.name,
#             }

#     return {"type": "recommended_path", "data": get_best_path(student)}


# ---------------------------------------------------------------------------
# Context builder shared by both the HTML preview and the PDF download
# ---------------------------------------------------------------------------

def _build_pdf_context(student):
    """
    Fetches the career path result and flattens it into a single context
    dict that the Jinja template can consume directly, regardless of which
    of the four "type" branches was returned.
    """
    result = get_student_career_path(student)

    student_doc = frappe.get_doc("Student", student)
    student_name = getattr(student_doc, "student_name", None) or student_doc.name

    context = {
        "student_id": student_doc.name,
        "student_name": student_name,
        "generated_on": frappe.utils.now_datetime().strftime("%d %b %Y, %I:%M %p"),
        "type": result.get("type"),
        "career_path": None,
        "data": None,
        "enrollment": None,
    }

    if result["type"] == "active_plan":
        context["data"] = result.get("data") or {}
        context["career_path"] = context["data"].get("career_path")

    elif result["type"] == "generating":
        context["career_path"] = result.get("career_path")

    elif result["type"] == "failed":
        context["career_path"] = result.get("career_path")
        context["enrollment"] = result.get("enrollment")

    elif result["type"] == "recommended_path":
        context["data"] = result.get("data") or {}
        context["career_path"] = context["data"].get("career_path")

    return context


# ---------------------------------------------------------------------------
# HTML preview endpoint (renders in the browser, also useful for Ctrl+P -> PDF)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_career_path_html(student):
    """
    GET /api/method/your_app.api.career_path.get_career_path_html?student=STU-0001

    Renders the same template used for the PDF, but returns it as a normal
    HTML page so it can be embedded in an iframe or opened directly for
    on-screen preview before downloading.
    """
    context = _build_pdf_context(student)
    
    html = frappe.render_template(
        "nexedu/templates/path_finder.html", context
    )
    frappe.response["type"] = "page"
    frappe.response["page"] = html


# ---------------------------------------------------------------------------
# PDF download endpoint
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def get_career_path_pdf(student):
 
    context = _build_pdf_context(student)
    
    html = frappe.render_template(
        "nexedu/templates/path_finder.html", context
    )
    frappe.logger().info(f"HTML length: {len(html)}")
    pdf_content = get_pdf(html, {...})
    frappe.logger().info(f"PDF length: {len(pdf_content) if pdf_content else 'None'}")

    pdf_content = get_pdf(html, {"orientation": "Portrait", "page-size": "A4"})

    frappe.local.response.filename = f"career_path_{student}.pdf"
    frappe.local.response.filecontent = pdf_content
    frappe.local.response.type = "pdf"


# ---------------------------------------------------------------------------
# Placeholders — replace with your real implementations
# ---------------------------------------------------------------------------

def get_active_plan(student):
    """
    Example shape expected by the template:
    {
        "career_path": "Data Science Track",
        "progress_percent": 42,
        "start_date": "2026-04-01",
        "milestones": [
            {"title": "Python Basics", "status": "Completed", "target_date": "2026-04-15", "description": "..."},
            {"title": "Statistics Foundations", "status": "In Progress", "target_date": "2026-05-01", "description": "..."},
        ],
    }
    """
    raise NotImplementedError


def get_best_path(student):
    """
    Example shape expected by the template:
    {
        "career_path": "UX Design Track",
        "match_score": 87,
        "description": "Recommended based on your interests and aptitude scores.",
        "milestones": [
            {"title": "Design Fundamentals", "description": "..."},
            {"title": "Portfolio Project", "description": "..."},
        ],
    }
    """
    raise NotImplementedError
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
def enroll_student(student, career_path, force_enroll=0, prereq_paths="[]", path_generation_mode=None, roadmap_source=None):
    """
    Creates a Student Path Enrollment document.
    Delegates to nexedu.path_finder.api.path_enrollment.enroll_student.
    """
    from nexedu.path_finder.api.path_enrollment import enroll_student as enroll_student_core
    return enroll_student_core(
        student=student,
        career_path=career_path,
        force_enroll=force_enroll,
        path_generation_mode=path_generation_mode,
        roadmap_source=roadmap_source,
    )


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
    
    
@frappe.whitelist(allow_guest=True)
def get_student_career_path(student):
    """
    Returns:
    - Active career path details if student has an active enrollment.
    - Best suggested career path if no active enrollment exists.
    """

    active_enrollment = frappe.db.exists(
        "Student Path Enrollment",
        {
            "student": student,
            "status": "Active"
        }
    )

    if active_enrollment:
        return {
            "type": "active_plan",
            "data": get_active_plan(student)
        }

    generating_enrollment = frappe.db.exists(
        "Student Path Enrollment",
        {
            "student": student,
            "status": "Generating"
        }
    )

    if generating_enrollment:
        career_path = frappe.db.get_value("Student Path Enrollment", generating_enrollment, "career_path")
        return {
            "type": "generating",
            "career_path": career_path
        }

    # Check for failed AI generation (Paused status with no milestones generated)
    paused_failed_enrollment = frappe.db.exists(
        "Student Path Enrollment",
        {
            "student": student,
            "status": "Paused"
        }
    )
    if paused_failed_enrollment:
        enr_doc = frappe.get_doc("Student Path Enrollment", paused_failed_enrollment)
        if not enr_doc.milestone_progress:
            return {
                "type": "failed",
                "career_path": enr_doc.career_path,
                "enrollment": enr_doc.name
            }

    return {
        "type": "recommended_path",
        "data": get_best_path(student)
    }


@frappe.whitelist()
def get_best_path(student):
    paths = get_top_path_suggestions(student, 1)
    if not paths:
        return {}

    best = paths[0]
    career_path = best["career_path"]

    # Prerequisite skills for this path
    prereq_skills = frappe.get_all(
        "Prerequisite Skills",
        filters={"parent": career_path, "parentfield": "prerequisite_skills"},
        fields=["prerequisite_skills", "level", "idx"],
        order_by="idx asc",
    )

    # Path milestones for this path
    path_milestones = frappe.get_all(
        "Path Milestone",
        filters={"parent": career_path, "parentfield": "path_milestone"},
        fields=[
            "name", "milestone_title", "milestone_type", "skill",
            "category", "topic", "subtopic", "required_skill_level",
            "is_mandatory", "duration_days", "linked_resource",
            "linked_resource_type", "pass_percentage", "assessment", "idx",
            "milestone_points",
        ],
        order_by="idx asc",
    )

    for m in path_milestones:
        m["points"] = [p.strip() for p in (m.get("milestone_points") or "").split("\n") if p.strip()]

    best["prerequisite_skills"] = prereq_skills
    best["milestones"] = path_milestones

    return best



@frappe.whitelist()
def get_ai_path_suggestion(student):
    top = get_top_path_suggestions(student, 1)
    if not top:
        return {}

    best = top[0]

    missing = best.get("missing_skills", [])
    next_skill = missing[0]["skill"] if missing else None

    return {
        "career_path": best["career_path"],
        "path_name": best["path_name"],
        "suggested_skill": next_skill,
        "message": f"Based on your profile, add {next_skill} to improve your fit score."
    }

@frappe.whitelist()
def get_recommended_paths(student):
    paths = get_top_path_suggestions(student, 6)

    if len(paths) <= 1:
        return []

    summary_fields = [
        "career_path", "path_name", "target_role", "difficulty_level",
        "fit_score", "matched_count", "partial_count", "missing_count",
        "total_skills", "estimated_duration", "average_salary",
    ]

    return [
        {k: p[k] for k in summary_fields}
        for p in paths[1:6]
    ]
    
    
@frappe.whitelist()
def get_active_plan(student):
    enrollment_name = frappe.db.get_value(
        "Student Path Enrollment",
        filters={"student": student, "status": "Active"},
        fieldname="name",
        order_by="creation desc",
    )
    if not enrollment_name:
        return {"has_active_plan": False, "message": "No active enrollment found."}

    enrollment = frappe.get_doc("Student Path Enrollment", enrollment_name)
    activation_date = getdate(enrollment.get("activation_date") or enrollment.get("creation"))

    # Fallback ordering: use milestone_order if set, else the child row's own idx
    rows = sorted(
        enrollment.milestone_progress,
        key=lambda r: r.milestone_order if r.milestone_order else r.idx
    )

    # Pull ALL Path Milestone rows for this career path once — covers
    # both linked (by name) and unlinked (by title) matching
    path_milestones = frappe.get_all(
        "Path Milestone",
        filters={"parent": enrollment.career_path, "parentfield": "path_milestone"},
        fields=["name", "milestone_title", "duration_days"],
    )
    duration_by_name  = {m.name: (m.duration_days or 0) for m in path_milestones}
    duration_by_title = {m.milestone_title: (m.duration_days or 0) for m in path_milestones}

    def get_duration(row):
        if getattr(row, "duration_days", 0):
            return row.duration_days
        if row.milestone and row.milestone in duration_by_name:
            duration = duration_by_name[row.milestone]
        else:
            # fallback for legacy rows where the Link never got saved
            duration = duration_by_title.get(row.milestone_title)

        # if duration is missing, zero, or None — default to 5 days
        return duration if duration else 5

    milestones = []
    total_count = 0
    completed_count = 0
    cursor_date = activation_date

    for row in rows:
        total_count += 1
        duration = get_duration(row)
        is_done = row.status == "Completed"
        if is_done:
            completed_count += 1

        if is_done:
            actual_date = getdate(row.completed_at) if row.completed_at else cursor_date
            display_date = formatdate(actual_date, "MMM d")
            date_label = "completed"
            cursor_date = actual_date
        elif row.status == "In Progress":
            due_date = add_days(cursor_date, duration)
            display_date = f"Due {formatdate(due_date, 'MMM d')}"
            date_label = "due"
            cursor_date = due_date
        else:
            projected_date = add_days(cursor_date, duration)
            display_date = formatdate(projected_date, "MMM d")
            date_label = "projected"
            cursor_date = projected_date

        # Get checklist points for this milestone
        m_points = [
            {
                "name": p.name,
                "point_title": p.point_title,
                "status": p.status
            }
            for p in (enrollment.get("milestone_points") or [])
            if p.milestone_title == row.milestone_title
        ]

        milestones.append({
            "name"                : row.name,
            "milestone_title"     : row.milestone_title,
            "status"              : row.status,
            "is_mandatory"        : row.is_mandatory,
            "duration_days"       : duration,
            "completed_at"        : row.completed_at,
            "display_date"        : display_date,
            "date_label"          : date_label,
            "skill"               : row.skill,
            "required_skill_level": row.required_skill_level,
            "category"            : row.skill_tier or row.category,
            "topic"               : row.topic,
            "subtopic"            : row.subtopic,
            "milestone_type"      : row.milestone_type,
            "linked_resource"     : row.linked_resource,
            "linked_resource_type": row.linked_resource_type,
            "is_prereq"           : row.is_prereq,
            "is_lock"             : row.is_lock,
            "points"              : m_points,
        })

    difficulty_level, average_salary = frappe.db.get_value(
        "Career Path",
        enrollment.career_path,
        ["difficulty_level", "average_salary_lpa"]
    ) or ("Moderate", 0.0)

    prereq_skills = frappe.get_all(
        "Prerequisite Skills",
        filters={"parent": enrollment.career_path, "parentfield": "prerequisite_skills"},
        fields=["prerequisite_skills", "level"],
        order_by="idx asc",
    )

    score_data = calculate_fit_score(student, enrollment.career_path)
    missing_skills = score_data.get("missing_skills", [])

    progress_percent = int(round((completed_count / total_count) * 100)) if total_count > 0 else 0
    is_completed = 1 if (total_count > 0 and completed_count == total_count) else 0

    return {
        "has_active_plan"      : True,
        "enrollment_id"        : enrollment.name,
        "career_path"          : enrollment.career_path,
        "progress_percent"     : progress_percent,
        "is_completed"         : is_completed,
        "total_milestones"     : total_count,
        "completed_milestones" : completed_count,
        "estimated_completion" : formatdate(cursor_date, "MMM yyyy"),
        "milestones"           : milestones,
        "difficulty_level"     : difficulty_level,
        "average_salary"       : average_salary,
        "prerequisite_skills"  : prereq_skills,
        "missing_skills"       : missing_skills,
        "matched_skills"       : score_data.get("matched_skills", []),
    }


@frappe.whitelist()
def get_all_career_paths(search_query=None, page=1, page_length=20):
    """
    Returns a paginated list of career paths from the Career Knowledge database,
    optionally filtered by search_query (matching career_name, industry, summary, or skill_name).
    """
    try:
        page = int(page)
        page_length = int(page_length)
    except ValueError:
        page = 1
        page_length = 20

    start = (page - 1) * page_length

    # Build filters dynamically
    filters = {}
    or_filters = []
    if search_query:
        query = f"%{search_query}%"
        # Find parents with matching skills
        matching_parents = frappe.db.sql("""
            SELECT DISTINCT parent 
            FROM `tabCareer Knowledge Skill`
            WHERE parenttype = 'Career Knowledge' AND skill_name LIKE %s
        """, query, pluck=True)

        or_filters = [
            ["career_name", "like", query],
            ["industry", "like", query],
            ["summary", "like", query]
        ]
        if matching_parents:
            or_filters.append(["name", "in", matching_parents])

    total_count = len(frappe.get_all("Career Knowledge", filters=filters, or_filters=or_filters, pluck="name"))

    records = frappe.get_all(
        "Career Knowledge",
        fields=[
            "name",
            "career_name",
            "industry",
            "category",
            "career_stage",
            "minimum_salary",
            "maximum_salary",
            "summary"
        ],
        filters=filters,
        or_filters=or_filters,
        start=start,
        page_length=page_length,
        order_by="career_name asc"
    )

    if not records:
        return {
            "paths": [],
            "total_count": 0,
            "page": page,
            "page_length": page_length,
            "total_pages": 0
        }

    record_names = [r.name for r in records]
    skills_map = {}
    skills_data = frappe.db.sql("""
        SELECT parent, skill_name 
        FROM `tabCareer Knowledge Skill`
        WHERE parenttype = 'Career Knowledge' AND parent IN %s
    """, (record_names,), as_dict=True)

    for row in skills_data:
        parent = row["parent"]
        skill = row["skill_name"]
        if parent not in skills_map:
            skills_map[parent] = []
        skills_map[parent].append(skill)

    paths = []
    for r in records:
        paths.append({
            "name": r.name,
            "path_name": r.career_name,
            "difficulty_level": r.career_stage or "Moderate",
            "target_role": r.career_name,
            "target_industry": r.industry or "Technology",
            "estimated_duration_months": 6,
            "average_salary_lpa": 0,
            "skills": skills_map.get(r.name, []),
            "summary": r.summary
        })

    import math
    total_pages = math.ceil(total_count / page_length)

    return {
        "paths": paths,
        "total_count": total_count,
        "page": page,
        "page_length": page_length,
        "total_pages": total_pages
    }