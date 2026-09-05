# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt
#
# nexedu/path_finder/api/path_enrollment.py
# ─────────────────────────────────────────────────────────────────────────────
# COMPLETE API FILE — all whitelisted endpoints for the PathFinder module
#
# INDEX
# ─────
#  1.  check_prerequisite_skills            (student, career_path)
#  2.  enroll_student                       (student, career_path, force_enroll, prereq_paths)
#  3.  get_milestone_overview               (enrollment)
#  4.  skip_milestone                       (enrollment, row_name)
#  5.  get_enrollment_for_student_path      (student, career_path)
#  6.  get_milestone_count_summary          (enrollment)
#  7.  get_path_suggestions                 (student, limit)
#  8.  get_enrollment_milestones_for_select (enrollment)
#  9.  complete_milestone_in_enrollment     [internal only]
#  10. get_student_enrollments              (student, status)
#  11. get_career_path_detail               (career_path, student)
#  12. get_student_skill_profile            (student)
#  13. update_enrollment_status             (enrollment, status)
#  14. get_path_progress_logs               (enrollment)
#  15. log_milestone_progress               (enrollment, milestone_row_name, score, ai_feedback, evidence)
#  16. get_leaderboard                      (career_path, limit)
#  17. get_student_dashboard                (student)
#  18. recalculate_fit_scores               (student)
# ─────────────────────────────────────────────────────────────────────────────

import frappe
from frappe.utils import now_datetime

from nexedu.path_finder.utils.milestone_engine import (
    build_milestone_rows_from_path,
    calculate_fit_score,
    get_top_path_suggestions,
    level_rank,
    recalculate_all_milestones,
)


# ══════════════════════════════════════════════════════════════════════════════
# 1. CHECK PREREQUISITE SKILLS
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def check_prerequisite_skills(student, career_path):
    """
    Compares a student's skills against a career path (prereq_skills + milestones).

    Returns:
        status              : "clear" | "gap"
        readiness_percent   : float  (0-100, weighted: full=1, partial=0.5)
        matched             : int
        total_prerequisites : int
        matched_skills      : list
        partial_skills      : list
        missing_skills      : list

    Each skill item: { skill, required_level, current_level, is_prereq, recommended_path }
    """
    score_data = calculate_fit_score(student, career_path)

    for s in score_data["partial_skills"] + score_data["missing_skills"]:
        s["recommended_path"] = _get_recommended_path_for_skill(s["skill"])

    status = "clear" if (score_data["partial_count"] + score_data["missing_count"]) == 0 else "gap"

    return {
        "status"             : status,
        "readiness_percent"  : score_data["fit_score"],
        "matched"            : score_data["matched_count"],
        "total_prerequisites": score_data["total_skills"],
        "matched_skills"     : score_data["matched_skills"],
        "partial_skills"     : score_data["partial_skills"],
        "missing_skills"     : score_data["missing_skills"],
    }


def _get_recommended_path_for_skill(skill_name):
    result = frappe.db.sql("""
        SELECT cp.name AS path_name, cp.path_name AS display_name,
               cp.estimated_duration_months AS duration_months,
               cp.difficulty_level AS difficulty
        FROM `tabCareer Path` cp
        INNER JOIN `tabPrerequisite Skills` ps
            ON ps.parent = cp.name AND ps.parentfield = 'prerequisite_skills'
           AND ps.prerequisite_skills = %s
        WHERE cp.published = 1
        ORDER BY cp.success_stories DESC LIMIT 1
    """, skill_name, as_dict=True)
    return result[0] if result else None


def ensure_skill_exists(s):
    if not s:
        return
    if not frappe.db.exists("Skill", s):
        try:
            frappe.get_doc({
                "doctype": "Skill",
                "skill_name": s
            }).insert(ignore_permissions=True)
        except Exception:
            pass


def ensure_category_exists(c):
    if not c:
        return
    if not frappe.db.exists("Skill Category", c):
        try:
            frappe.get_doc({
                "doctype": "Skill Category",
                "category_name": c,
                "is_active": 1
            }).insert(ignore_permissions=True)
        except Exception:
            pass


def check_and_create_career_path(career_path):
    exists = frappe.db.exists("Career Path", career_path)
    is_incomplete = False
    if exists:
        doc = frappe.get_doc("Career Path", career_path)
        if not doc.path_milestone:
            is_incomplete = True
            frappe.delete_doc("Career Path", career_path, ignore_permissions=True)
            frappe.db.commit()

    if not exists or is_incomplete:
        _do_create_career_path(career_path)


def _do_create_career_path(career_path):
    exists = frappe.db.exists("Career Path", career_path)
    if exists:
        doc = frappe.get_doc("Career Path", career_path)
        if doc.path_milestone:
            return
            
    try:
        from job_search_ai.agents.skill_agent.skill_agent import SkillAgent
        from job_search_ai.agents.skill_agent.schemas import SkillRequest
        
        agent = SkillAgent()
        request = SkillRequest(role=career_path)
        res = agent.run(request, save_to_doctype=False)
        profile = res.profile
        
        cp_doc = frappe.get_doc({
            "doctype": "Career Path",
            "path_name": career_path,
            "path_type": "Job",
            "difficulty_level": "Moderate",
            "target_role": career_path,
            "estimated_duration_months": 6,
            "published": 1,
            "prerequisite_skills": [],
            "path_milestone": []
        })
        
        for skill in profile.foundation_skills:
            ensure_skill_exists(skill)
            cp_doc.append("prerequisite_skills", {
                "prerequisite_skills": skill,
                "level": "Beginner"
            })
            
        for skill in profile.core_domain_skills:
            ensure_skill_exists(skill)
            ensure_category_exists("Core Domain")
            cp_doc.append("path_milestone", {
                "milestone_title": f"Master {skill}",
                "category": "Core Domain",
                "skill": skill,
                "milestone_type": "Learn",
                "required_skill_level": "Intermediate",
                "is_mandatory": 1,
                "duration_days": 10
            })
            
        for skill in profile.industry_skills:
            ensure_skill_exists(skill)
            ensure_category_exists("Industry")
            cp_doc.append("path_milestone", {
                "milestone_title": f"Master {skill}",
                "category": "Industry",
                "skill": skill,
                "milestone_type": "Learn",
                "required_skill_level": "Intermediate",
                "is_mandatory": 1,
                "duration_days": 10
            })
            
        for skill in profile.emerging_skills:
            ensure_skill_exists(skill)
            ensure_category_exists("Emerging")
            cp_doc.append("path_milestone", {
                "milestone_title": f"Master {skill}",
                "category": "Emerging",
                "skill": skill,
                "milestone_type": "Learn",
                "required_skill_level": "Intermediate",
                "is_mandatory": 1,
                "duration_days": 10
            })
            
        cp_doc.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(f"Failed to auto-create Career Path for {career_path}: {str(e)}", "Career Path Auto-Creation")


def build_roadmap_template_from_career_path(career_path):
    if frappe.db.exists("Roadmap Template", career_path):
        return
        
    if not frappe.db.exists("Career Path", career_path):
        return

    import json
    try:
        cp_doc = frappe.get_doc("Career Path", career_path)
        milestones = []
        
        # Add prerequisite skills
        for p in cp_doc.prerequisite_skills:
            if not p.prerequisite_skills:
                continue
            milestones.append({
                "title": f"Prerequisite: {p.prerequisite_skills}",
                "type": "Learn",
                "primary_skill": p.prerequisite_skills,
                "skill": p.prerequisite_skills,
                "skill_tier": "Foundation",
                "duration_days": 10,
                "objective": f"Develop comprehensive practical skills and theoretical understanding of {p.prerequisite_skills}.",
                "project": f"Build a practical hands-on application implementing {p.prerequisite_skills} features, focusing on industry best practices.",
                "points": [],
                "completion_criteria": [f"Complete the tasks defined for {p.prerequisite_skills} milestone."],
                "learning_outcomes": [f"Understand the basic core logic of {p.prerequisite_skills}."]
            })
            
        # Add path milestones
        for pm in cp_doc.path_milestone:
            if not pm.skill:
                continue
            points = [pt.strip() for pt in (pm.milestone_points or "").split("\n") if pt.strip()]
            milestones.append({
                "title": pm.milestone_title,
                "type": pm.milestone_type or "Learn",
                "primary_skill": pm.skill,
                "skill": pm.skill,
                "skill_tier": pm.category or "Core Domain",
                "duration_days": pm.duration_days or 14,
                "objective": f"Develop comprehensive practical skills and theoretical understanding of {pm.skill}.",
                "project": f"Build a practical hands-on application implementing {pm.skill} features, focusing on industry best practices.",
                "points": points,
                "linked_resource_type": pm.linked_resource_type,
                "linked_resource": pm.linked_resource,
                "completion_criteria": [f"Complete the tasks defined for {pm.skill} milestone."],
                "learning_outcomes": [f"Understand the basic core logic of {pm.skill}."]
            })

        template_doc = frappe.get_doc({
            "doctype": "Roadmap Template",
            "career_path": career_path,
            "roadmap_version": "1.0",
            "milestones_json": json.dumps({"milestones": milestones})
        })
        template_doc.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(f"Failed to auto-create Roadmap Template from Career Path {career_path}: {str(e)}", "AI Roadmap Template Conversion")


# ══════════════════════════════════════════════════════════════════════════════
# 2. ENROLL STUDENT
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def enroll_student(student, career_path, force_enroll=0, path_generation_mode=None, roadmap_source=None):
    """
    Creates a Student Path Enrollment.
    Prerequisite skill rows are auto-prepended by the controller's after_insert,
    unless AI roadmap generation is requested (via path_generation_mode='AI' or roadmap_source='AI'),
    in which case personalized milestones are generated via RoadmapAgent.

    Returns: { status: "success"|"already_enrolled", enrollment: <name> }
    """
    existing_active = frappe.db.exists(
        "Student Path Enrollment",
        {"student": student, "career_path": career_path, "status": "Active"},
    )
    if existing_active:
        return {"status": "already_enrolled", "enrollment": existing_active}

    existing_generating = frappe.db.exists(
        "Student Path Enrollment",
        {"student": student, "career_path": career_path, "status": "Generating"},
    )
    if existing_generating:
        return {"status": "generating", "enrollment": existing_generating}

    # Clean up any paused failed enrollments (paused with no milestones)
    existing_paused = frappe.db.exists(
        "Student Path Enrollment",
        {"student": student, "career_path": career_path, "status": "Paused"},
    )
    if existing_paused:
        enr_doc = frappe.get_doc("Student Path Enrollment", existing_paused)
        if not enr_doc.milestone_progress:
            frappe.delete_doc("Student Path Enrollment", existing_paused, ignore_permissions=True)
            frappe.db.commit()

    check_and_create_career_path(career_path)

    # Pause other active paths for the student
    other_active = frappe.get_all(
        "Student Path Enrollment",
        filters={"student": student, "status": "Active", "career_path": ["!=", career_path]},
        fields=["name"]
    )
    for enrollment in other_active:
        frappe.db.set_value("Student Path Enrollment", enrollment.name, "status", "Paused")
    if other_active:
        frappe.db.commit()

    is_ai = (path_generation_mode == "AI" or roadmap_source == "AI")

    if is_ai:
        # If Career Path already exists, seed Roadmap Template instantly to avoid background queue latency
        build_roadmap_template_from_career_path(career_path)

        # ── Smart Cache Check ─────────────────────────────────────────────────
        # If a generic Roadmap Template exists, we reuse and personalize it
        # immediately. No background queue or LLM call is needed.
        if frappe.db.exists("Roadmap Template", career_path):
            doc_data = {
                "doctype"                : "Student Path Enrollment",
                "student"                : student,
                "career_path"            : career_path,
                "status"                 : "Active",
                "enrolled_at"            : now_datetime(),
                "current_milestone_order": 1,
                "force_enroll"           : int(force_enroll),
                "triggered_from"         : "API",
                "ai_recommended"         : 1,
            }
            doc = frappe.get_doc(doc_data)
            try:
                from job_search_ai.tasks import personalize_enrollment_from_template
                personalize_enrollment_from_template(doc)
                
                from nexedu.path_finder.utils.milestone_engine import recalculate_all_milestones
                recalculate_all_milestones(doc)

                doc.insert(ignore_permissions=True)
                frappe.db.commit()
                return {"status": "success", "enrollment": doc.name}
            except Exception as e:
                frappe.log_error(f"Sync template personalization failed for {career_path}: {str(e)}")
                # Fall through to background generation if personalization failed

        # Template not yet seeded — run the AI agent to generate the roadmap
        doc = frappe.get_doc({
            "doctype"                : "Student Path Enrollment",
            "student"                : student,
            "career_path"            : career_path,
            "status"                 : "Generating",
            "enrolled_at"            : now_datetime(),
            "current_milestone_order": 1,
            "force_enroll"           : int(force_enroll),
            "triggered_from"         : "API",
            "ai_recommended"         : 1,
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

        frappe.enqueue(
            "job_search_ai.tasks.generate_personalized_roadmap",
            queue="long",
            timeout=600,
            enrollment_name=doc.name
        )

        return {"status": "success", "enrollment": doc.name}

    # Rules-based / Standard enrollment
    doc_data = {
        "doctype"                : "Student Path Enrollment",
        "student"                : student,
        "career_path"            : career_path,
        "status"                 : "Active",
        "enrolled_at"            : now_datetime(),
        "current_milestone_order": 1,
        "force_enroll"           : int(force_enroll),
        "triggered_from"         : "API",
        "ai_recommended"         : 0,
    }

    doc = frappe.get_doc(doc_data)
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "success", "enrollment": doc.name}


# ══════════════════════════════════════════════════════════════════════════════
# 3. GET MILESTONE OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_milestone_overview(enrollment):
    """
    Full milestone list for the Journey board.

    Returns:
        milestones, completion_percent, status_counts,
        total_count, completed_count, prereq_count, prereq_completed,
        path_count, path_completed

    Each milestone:
        row_name, milestone_title, milestone_type, milestone_idx,
        skill, required_skill_level, status, score, started_on,
        completed_on, is_current, is_prereq, is_lock, is_skippable,
        is_auto_skipped, topic, subtopic, category, duration_days,
        linked_resource, linked_resource_type, ai_feedback
    """
    doc  = frappe.get_doc("Student Path Enrollment", enrollment)
    rows = sorted(doc.milestone_progress, key=lambda r: r.idx)

    status_counts    = {}
    milestones_out   = []
    prereq_count     = 0
    prereq_completed = 0
    path_count       = 0
    path_completed   = 0

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
            "row_name"            : row.name,
            "milestone_title"     : row.milestone_title,
            "milestone_type"      : row.milestone_type,
            "milestone_idx"       : row.idx,
            "skill"               : getattr(row, "skill", None),
            "required_skill_level": getattr(row, "required_skill_level", None),
            "status"              : status,
            "score"               : row.score,
            "started_on"          : str(row.started_on)   if getattr(row, "started_on",   None) else None,
            "completed_on"        : str(row.completed_at) if getattr(row, "completed_at", None) else None,
            "is_current"          : row.idx == (doc.current_milestone_order or 1),
            "is_prereq"           : is_prereq,
            "is_lock"             : bool(getattr(row, "is_lock", 0)),
            "is_skippable"        : not bool(getattr(row, "is_mandatory", 1)),
            "is_auto_skipped"     : bool(getattr(row, "is_auto_skipped", 0)),
            "topic"               : getattr(row, "topic",    None),
            "subtopic"            : getattr(row, "subtopic", None),
            "category"            : getattr(row, "skill_tier", None) or getattr(row, "category", None),
            "duration_days"       : getattr(row, "duration_days", None),
            "linked_resource"     : getattr(row, "linked_resource", None),
            "linked_resource_type": getattr(row, "linked_resource_type", None),
            "ai_feedback"         : getattr(row, "ai_feedback", None),
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
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def skip_milestone(enrollment, row_name):
    """
    Skips a non-mandatory milestone and advances the enrollment pointer.
    Returns: { success: True, skipped_milestone: str }
    """
    doc    = frappe.get_doc("Student Path Enrollment", enrollment)
    target = next((r for r in doc.milestone_progress if r.name == row_name), None)

    if not target:
        frappe.throw(f"Milestone row <b>{row_name}</b> not found.")
    if getattr(target, "is_mandatory", 1):
        frappe.throw(f"Milestone '<b>{target.milestone_title}</b>' is mandatory and cannot be skipped.")

    target.status       = "Skipped"
    target.completed_at = now_datetime()

    _advance_enrollment(doc, target.idx)
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"success": True, "skipped_milestone": target.milestone_title}


def _advance_enrollment(doc, completed_idx):
    rows_sorted = sorted(doc.milestone_progress, key=lambda r: r.idx)
    advanced    = False

    for row in rows_sorted:
        if row.idx <= completed_idx:
            continue
        if row.status not in ("Completed", "Skipped"):
            row.status                  = "In Progress"
            doc.current_milestone_order = row.idx
            advanced = True
            break

    if not advanced:
        doc.status = "Completed"

    mandatory = [r for r in doc.milestone_progress if getattr(r, "is_mandatory", 1)]
    done      = sum(1 for r in mandatory if r.status in ("Completed", "Skipped"))
    doc.completion_percent = round((done / len(mandatory)) * 100, 2) if mandatory else 0.0
    if doc.completion_percent >= 100:
        doc.status = "Completed"


# ══════════════════════════════════════════════════════════════════════════════
# 5. GET ENROLLMENT FOR STUDENT + PATH
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_enrollment_for_student_path(student, career_path):
    """Returns active enrollment name for student+path, or None."""
    return frappe.db.get_value(
        "Student Path Enrollment",
        {"student": student, "career_path": career_path, "status": "Active"},
        "name",
    ) or None


# ══════════════════════════════════════════════════════════════════════════════
# 6. GET MILESTONE COUNT SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_milestone_count_summary(enrollment):
    """
    Returns all overview fields plus:
        label: "4 Prereqs + 11 Milestones = 15 Total | 5 Completed"
    """
    overview = get_milestone_overview(enrollment)
    overview["label"] = (
        f"{overview['prereq_count']} Prereqs"
        f" + {overview['path_count']} Milestones"
        f" = {overview['total_count']} Total"
        f" | {overview['completed_count']} Completed"
    )
    return overview


# ══════════════════════════════════════════════════════════════════════════════
# 7. GET PATH SUGGESTIONS
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_path_suggestions(student, limit=5):
    """
    Returns top N published career paths ranked by fit score.
    Excludes paths the student is already actively enrolled in.

    Each item:
        career_path, path_name, target_role, difficulty_level,
        fit_score, matched_count, partial_count, missing_count,
        total_skills, estimated_duration, average_salary, success_stories,
        skill_tags: [{skill, status: matched|partial|missing}]
    """
    suggestions  = get_top_path_suggestions(student, int(limit))
    enrolled_set = set(frappe.get_all(
        "Student Path Enrollment",
        filters={"student": student, "status": "Active"},
        pluck="career_path",
    ))

    result = []
    for s in suggestions:
        if s["career_path"] in enrolled_set:
            continue
        skill_tags = (
            [{"skill": sk["skill"], "status": "matched"} for sk in s.get("matched_skills", [])]
            + [{"skill": sk["skill"], "status": "partial"} for sk in s.get("partial_skills", [])]
            + [{"skill": sk["skill"], "status": "missing"} for sk in s.get("missing_skills", [])]
        )
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
            "skill_tags"        : skill_tags[:8],
        })
    return result[:int(limit)]


# ══════════════════════════════════════════════════════════════════════════════
# 8. GET ENROLLMENT MILESTONES FOR SELECT
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_enrollment_milestones_for_select(enrollment):
    """
    Returns milestone_progress child rows for the PPL milestone dropdown.
    row_name is stored as PPL.milestone (child row Frappe name).
    """
    doc  = frappe.get_doc("Student Path Enrollment", enrollment)
    rows = sorted(doc.milestone_progress, key=lambda r: r.idx)
    return [{
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
    } for row in rows]


# ══════════════════════════════════════════════════════════════════════════════
# 9. COMPLETE MILESTONE  [INTERNAL — called by PathProgressLog.on_update]
# ══════════════════════════════════════════════════════════════════════════════

def complete_milestone_in_enrollment(enrollment_name, milestone_row_name, score=None, ai_feedback=None):
    doc    = frappe.get_doc("Student Path Enrollment", enrollment_name)
    target = next((r for r in doc.milestone_progress if r.name == milestone_row_name), None)

    if not target:
        frappe.log_error(
            f"Row {milestone_row_name} not found in enrollment {enrollment_name}",
            "PathFinder: complete_milestone_in_enrollment",
        )
        return

    target.status       = "Completed"
    target.completed_at = now_datetime()
    if score is not None:
        target.score = score
    if ai_feedback:
        target.ai_feedback = ai_feedback

    _advance_enrollment(doc, target.idx)
    doc.save(ignore_permissions=True)
    frappe.db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# 10. GET STUDENT ENROLLMENTS
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_student_enrollments(student, status=None):
    """
    Returns all enrollments for a student, optionally filtered by status.

    Params:
        student : str
        status  : "Active" | "Completed" | "Paused" | "Abandoned" | None (all)

    Each item:
        enrollment, career_path, path_name, status,
        completion_percent, skill_match_percent, enrolled_at,
        target_date, current_milestone_order,
        total_milestones, prereq_count, path_count
    """
    filters = {"student": student}
    if status:
        filters["status"] = status

    enrollments = frappe.get_all(
        "Student Path Enrollment",
        filters=filters,
        fields=[
            "name", "career_path", "status", "completion_percent",
            "skill_match_percent", "enrolled_at", "target_date",
            "current_milestone_order",
        ],
        order_by="enrolled_at desc",
    )

    result = []
    for e in enrollments:
        path_name = frappe.db.get_value("Career Path", e.career_path, "path_name")
        doc       = frappe.get_doc("Student Path Enrollment", e.name)
        total     = len(doc.milestone_progress)
        prereq_c  = sum(1 for r in doc.milestone_progress if getattr(r, "is_prereq", 0))

        result.append({
            "enrollment"             : e.name,
            "career_path"            : e.career_path,
            "path_name"              : path_name or e.career_path,
            "status"                 : e.status,
            "completion_percent"     : e.completion_percent or 0,
            "skill_match_percent"    : e.skill_match_percent or 0,
            "enrolled_at"            : str(e.enrolled_at) if e.enrolled_at else None,
            "target_date"            : str(e.target_date) if e.target_date else None,
            "current_milestone_order": e.current_milestone_order,
            "total_milestones"       : total,
            "prereq_count"           : prereq_c,
            "path_count"             : total - prereq_c,
        })
    return result


# ══════════════════════════════════════════════════════════════════════════════
# 11. GET CAREER PATH DETAIL
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_career_path_detail(career_path, student=None):
    """
    Full detail of a Career Path including milestone tree and optional fit score.

    Params:
        career_path : str
        student     : str | None  — if given, includes fit_score and enrollment

    Returns:
        path metadata, prerequisite_skills[], milestones[], milestone_tree{},
        prereq_count, milestone_count, total_count,
        [if student]: fit_score, matched/partial/missing skills, enrollment name
    """
    check_and_create_career_path(career_path)
    
    if not frappe.db.exists("Career Path", career_path):
        return {
            "career_path"             : career_path,
            "path_name"               : career_path,
            "difficulty_level"        : "Moderate",
            "estimated_duration_months": 6,
            "target_role"             : career_path,
            "prerequisite_skills"     : [],
            "milestones"              : [],
            "milestone_tree"          : {},
            "prereq_count"            : 0,
            "milestone_count"         : 0,
            "total_count"             : 0,
            "status"                  : "generating"
        }

    doc = frappe.get_doc("Career Path", career_path)

    prereqs = [{"skill": r.prerequisite_skills, "required_skill_level": r.level}
               for r in doc.prerequisite_skills]

    milestones = sorted(doc.path_milestone, key=lambda r: r.idx)
    milestone_list = [{
        "idx"                 : m.idx,
        "milestone_title"     : m.milestone_title,
        "milestone_type"      : m.milestone_type,
        "skill"               : m.skill,
        "category"            : m.category,
        "topic"               : m.topic,
        "subtopic"            : m.subtopic,
        "required_skill_level": m.required_skill_level,
        "is_mandatory"        : m.is_mandatory,
        "duration_days"       : m.duration_days,
        "linked_resource_type": m.linked_resource_type,
        "linked_resource"     : m.linked_resource,
        "pass_percentage"     : m.pass_percentage,
    } for m in milestones]

    # Build tree: skill -> topic -> subtopic -> [milestones]
    tree = {}
    for m in milestone_list:
        tree.setdefault(m["skill"] or "General", {}) \
            .setdefault(m["topic"] or "General", {}) \
            .setdefault(m["subtopic"] or "General", []) \
            .append(m)

    result = {
        "name"                    : doc.name,
        "path_name"               : doc.path_name,
        "path_type"               : doc.path_type,
        "target_role"             : doc.target_role,
        "target_industry"         : doc.target_industry,
        "difficulty_level"        : doc.difficulty_level,
        "estimated_duration_months": doc.estimated_duration_months,
        "average_salary_lpa"      : doc.average_salary_lpa,
        "success_stories"         : doc.success_stories,
        "published"               : doc.published,
        "prerequisite_skills"     : prereqs,
        "milestones"              : milestone_list,
        "milestone_tree"          : tree,
        "prereq_count"            : len(prereqs),
        "milestone_count"         : len(milestone_list),
        "total_count"             : len(prereqs) + len(milestone_list),
    }

    if student:
        sd = calculate_fit_score(student, career_path)
        result.update({
            "fit_score"      : sd["fit_score"],
            "matched_count"  : sd["matched_count"],
            "partial_count"  : sd["partial_count"],
            "missing_count"  : sd["missing_count"],
            "matched_skills" : sd["matched_skills"],
            "partial_skills" : sd["partial_skills"],
            "missing_skills" : sd["missing_skills"],
            "enrollment"     : frappe.db.get_value(
                "Student Path Enrollment",
                {"student": student, "career_path": career_path, "status": "Active"},
                "name",
            ) or None,
        })
    return result


# ══════════════════════════════════════════════════════════════════════════════
# 12. GET STUDENT SKILL PROFILE
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_student_skill_profile(student):
    """
    Complete skill profile for a student.

    Returns:
        student, skills[], by_level{}, total_skills,
        verified_count, self_declared, active_paths[]
    """
    skills = frappe.get_all(
        "Student Skill",
        filters={"student": student},
        fields=["skill", "skill_level", "is_verified", "is_public"],
        order_by="skill_level desc, skill asc",
    )

    by_level = {}
    for s in skills:
        by_level.setdefault(s.skill_level or "Beginner", []).append(s.skill)

    verified_count = sum(1 for s in skills if s.is_verified)

    active_paths = frappe.get_all(
        "Student Path Enrollment",
        filters={"student": student, "status": "Active"},
        fields=["name", "career_path", "completion_percent", "skill_match_percent"],
    )

    return {
        "student"        : student,
        "skills"         : [dict(s) for s in skills],
        "by_level"       : by_level,
        "total_skills"   : len(skills),
        "verified_count" : verified_count,
        "self_declared"  : len(skills) - verified_count,
        "active_paths"   : [dict(p) for p in active_paths],
    }


# ══════════════════════════════════════════════════════════════════════════════
# 13. UPDATE ENROLLMENT STATUS
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def update_enrollment_status(enrollment, status):
    """
    Updates enrollment status (Active / Paused / Abandoned).
    Completed is set automatically — not allowed here.

    Returns: { success: True, enrollment, new_status }
    """
    allowed = ["Active", "Paused", "Abandoned"]
    if status not in allowed:
        frappe.throw(f"Invalid status '{status}'. Allowed: {', '.join(allowed)}")

    doc = frappe.get_doc("Student Path Enrollment", enrollment)
    if doc.status == "Completed":
        frappe.throw("Cannot change the status of a Completed enrollment.")

    doc.status = status
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"success": True, "enrollment": enrollment, "new_status": status}


# ══════════════════════════════════════════════════════════════════════════════
# 14. GET PATH PROGRESS LOGS
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_path_progress_logs(enrollment):
    """
    Returns all Path Progress Log entries for an enrollment, sorted by order asc.

    Each item:
        name, milestone (row_name), milestone_title, milestone_idx,
        is_prereq, skill, order, score, ai_feedback, completed_at, evidence
    """
    logs = frappe.get_all(
        "Path Progress Log",
        filters={"enrollment": enrollment},
        fields=["name", "milestone", "order", "score", "ai_feedback", "completed_at", "evidence"],
        order_by="order asc",
    )

    enr_doc = frappe.get_doc("Student Path Enrollment", enrollment)
    row_map  = {r.name: r for r in enr_doc.milestone_progress}

    result = []
    for log in logs:
        row = row_map.get(log.milestone)
        result.append({
            "name"           : log.name,
            "milestone"      : log.milestone,
            "milestone_title": row.milestone_title if row else "—",
            "milestone_idx"  : row.idx if row else log.order,
            "is_prereq"      : bool(getattr(row, "is_prereq", 0)) if row else False,
            "skill"          : getattr(row, "skill", None) if row else None,
            "order"          : log.order,
            "score"          : log.score,
            "ai_feedback"    : log.ai_feedback,
            "completed_at"   : str(log.completed_at) if log.completed_at else None,
            "evidence"       : log.evidence,
        })
    return result


# ══════════════════════════════════════════════════════════════════════════════
# 15. LOG MILESTONE PROGRESS  (direct API — alternative to form-based PPL entry)
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def log_milestone_progress(enrollment, milestone_row_name, score=None, ai_feedback=None, evidence=None):
    """
    Creates a Path Progress Log for a milestone child row.
    The PPL controller (on_update) handles:
        - Marking the child row Completed
        - Advancing current_milestone_order
        - Creating/upgrading Student Skill

    Params:
        enrollment         : str   — Student Path Enrollment name
        milestone_row_name : str   — Child row name from milestone_progress
        score              : float | None
        ai_feedback        : str   | None
        evidence           : str   | None  — Skill Evidence link

    Returns:
        success, log, completed_milestone_idx, completed_milestone_title,
        next_milestone_idx, next_milestone_title,
        completion_percent, enrollment_status
    """
    enr_doc = frappe.get_doc("Student Path Enrollment", enrollment)
    target  = next((r for r in enr_doc.milestone_progress if r.name == milestone_row_name), None)

    if not target:
        frappe.throw(f"Milestone row <b>{milestone_row_name}</b> not found in enrollment <b>{enrollment}</b>.")

    current_order = enr_doc.current_milestone_order or 1
    if int(target.idx) != int(current_order):
        frappe.throw(
            f"Cannot log milestone <b>#{target.idx} — {target.milestone_title}</b>.<br>"
            f"Current expected milestone is <b>#{current_order}</b>."
        )

    if frappe.db.exists("Path Progress Log", {"enrollment": enrollment, "milestone": milestone_row_name}):
        frappe.throw(f"Milestone <b>#{target.idx}</b> is already logged for this enrollment.")

    log_doc = frappe.get_doc({
        "doctype"     : "Path Progress Log",
        "enrollment"  : enrollment,
        "career_path" : enr_doc.career_path,
        "milestone"   : milestone_row_name,
        "score"       : float(score) if score is not None else None,
        "ai_feedback" : ai_feedback,
        "evidence"    : evidence,
        "completed_at": now_datetime(),
    })
    log_doc.insert(ignore_permissions=True)
    frappe.db.commit()

    enr_fresh  = frappe.get_doc("Student Path Enrollment", enrollment)
    next_idx   = enr_fresh.current_milestone_order
    next_row   = next((r for r in enr_fresh.milestone_progress if r.idx == next_idx), None)

    return {
        "success"                  : True,
        "log"                      : log_doc.name,
        "completed_milestone_idx"  : target.idx,
        "completed_milestone_title": target.milestone_title,
        "next_milestone_idx"       : next_idx if next_row else None,
        "next_milestone_title"     : next_row.milestone_title if next_row else None,
        "completion_percent"       : enr_fresh.completion_percent,
        "enrollment_status"        : enr_fresh.status,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 16. GET LEADERBOARD
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_leaderboard(career_path=None, limit=10):
    """
    Returns top students ranked by completion_percent.

    Params:
        career_path : str | None  — filter by path; None = all paths
        limit       : int         — default 10

    Each item:
        rank, student, student_name, career_path, path_name,
        completion_percent, skill_match_percent, enrolled_at
    """
    filters = {"status": ["in", ["Active", "Completed"]]}
    if career_path:
        filters["career_path"] = career_path

    enrollments = frappe.get_all(
        "Student Path Enrollment",
        filters=filters,
        fields=["name", "student", "career_path", "completion_percent", "skill_match_percent", "enrolled_at"],
        order_by="completion_percent desc",
        limit=int(limit),
    )

    result = []
    for i, e in enumerate(enrollments, 1):
        result.append({
            "rank"               : i,
            "student"            : e.student,
            "student_name"       : frappe.db.get_value("Student", e.student, "full_name") or e.student,
            "career_path"        : e.career_path,
            "path_name"          : frappe.db.get_value("Career Path", e.career_path, "path_name") or e.career_path,
            "completion_percent" : e.completion_percent or 0,
            "skill_match_percent": e.skill_match_percent or 0,
            "enrolled_at"        : str(e.enrolled_at) if e.enrolled_at else None,
        })
    return result


# ══════════════════════════════════════════════════════════════════════════════
# 17. GET STUDENT DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_student_dashboard(student):
    """
    Single call for a student's home dashboard.

    Returns:
        student, active_enrollments[], completed_count,
        total_skills, verified_skills,
        top_suggestions[] (max 5), recent_logs[] (max 5)
    """
    active_enrollments = get_student_enrollments(student, status="Active")
    completed_count    = frappe.db.count("Student Path Enrollment", {"student": student, "status": "Completed"})

    skills_data     = frappe.get_all("Student Skill", filters={"student": student}, fields=["is_verified"])
    total_skills    = len(skills_data)
    verified_skills = sum(1 for s in skills_data if s.is_verified)

    top_suggestions = get_path_suggestions(student, limit=5)

    enrollment_names = frappe.get_all("Student Path Enrollment", filters={"student": student}, pluck="name")
    recent_logs = []
    if enrollment_names:
        logs_raw = frappe.get_all(
            "Path Progress Log",
            filters={"enrollment": ["in", enrollment_names]},
            fields=["name", "enrollment", "milestone", "score", "completed_at"],
            order_by="completed_at desc",
            limit=5,
        )
        for log in logs_raw:
            enr_doc = frappe.get_doc("Student Path Enrollment", log.enrollment)
            row     = next((r for r in enr_doc.milestone_progress if r.name == log.milestone), None)
            recent_logs.append({
                "log"            : log.name,
                "enrollment"     : log.enrollment,
                "career_path"    : enr_doc.career_path,
                "milestone_title": row.milestone_title if row else "—",
                "milestone_idx"  : row.idx if row else None,
                "score"          : log.score,
                "completed_at"   : str(log.completed_at) if log.completed_at else None,
            })

    return {
        "student"           : student,
        "active_enrollments": active_enrollments,
        "completed_count"   : completed_count,
        "total_skills"      : total_skills,
        "verified_skills"   : verified_skills,
        "top_suggestions"   : top_suggestions,
        "recent_logs"       : recent_logs,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 18. RECALCULATE FIT SCORES
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def recalculate_fit_scores(student):
    """
    Refreshes skill_match_percent on all active enrollments for a student.
    Call when the student's skill ledger changes.

    Returns: { updated: [{enrollment, career_path, old_score, new_score}] }
    """
    enrollments = frappe.get_all(
        "Student Path Enrollment",
        filters={"student": student, "status": "Active"},
        fields=["name", "career_path", "skill_match_percent"],
    )

    updated = []
    for e in enrollments:
        old_score  = e.skill_match_percent or 0
        new_score  = calculate_fit_score(student, e.career_path)["fit_score"]
        frappe.db.set_value("Student Path Enrollment", e.name, "skill_match_percent", new_score)
        updated.append({
            "enrollment" : e.name,
            "career_path": e.career_path,
            "old_score"  : old_score,
            "new_score"  : new_score,
        })

    frappe.db.commit()
    return {"updated": updated}


@frappe.whitelist()
def get_best_path(student):
    """
    Returns the highest fit-score career path for a student.
    """

    suggestions = get_top_path_suggestions(student, 1)

    if not suggestions:
        return {
            "status": "no_path_found"
        }

    best = suggestions[0]

    return {
        "status": "success",
        "career_path": best["career_path"],
        "path_name": best["path_name"],
        "target_role": best["target_role"],
        "difficulty_level": best["difficulty_level"],
        "fit_score": best["fit_score"],
        "matched_count": best["matched_count"],
        "partial_count": best["partial_count"],
        "missing_count": best["missing_count"],
        "total_skills": best["total_skills"],
        "estimated_duration": best["estimated_duration"],
        "average_salary": best["average_salary"],
        "success_stories": best["success_stories"]
    }
    
@frappe.whitelist()
def get_recommended_paths(student):
    """
    Returns next top 5 career paths after the best path.
    """

    suggestions = get_top_path_suggestions(student, 6)

    if not suggestions or len(suggestions) <= 1:
        return []

    # Remove best/top path
    recommendations = suggestions[1:6]

    result = []

    for path in recommendations:
        result.append({
            "career_path": path.get("career_path"),
            "path_name": path.get("path_name"),
            "target_role": path.get("target_role"),
            "difficulty_level": path.get("difficulty_level"),
            "fit_score": path.get("fit_score"),
            "matched_count": path.get("matched_count"),
            "partial_count": path.get("partial_count"),
            "missing_count": path.get("missing_count")
        })

    return result
    


@frappe.whitelist()
def get_path_dashboard(student):
    """
    Complete dashboard API for frontend.
    """

    best_path = get_best_path(student)

    recommended_paths = get_recommended_paths(student)

    # ai_suggestion = get_ai_path_suggestion(student)

    active_enrollment = frappe.get_all(
        "Student Path Enrollment",
        filters={
            "student": student,
            "status": "Active"
        },
        fields=[
            "name",
            "career_path",
            "completion_percent",
            "current_milestone_order"
        ],
        limit=1
    )

    return {
        "best_path": best_path,
        "recommended_paths": recommended_paths,
        # "ai_suggestion": ai_suggestion,
        "active_enrollment": active_enrollment[0] if active_enrollment else None
    }


@frappe.whitelist(allow_guest=True)
def get_hierarchy_skills_for_path(career_path):
    """
    Returns skills required by a career path, grouped by their tier/category:
    - foundation_skills
    - core_domain_skills
    - industry_skills
    - emerging_skills
    """
    check_and_create_career_path(career_path)

    if not frappe.db.exists("Career Path", career_path):
        foundation = []
        core = []
        industry = []
        emerging = []
        
        ck_name = frappe.db.get_value("Career Knowledge", {"career_name": career_path}, "name")
        if ck_name:
            ck = frappe.get_doc("Career Knowledge", ck_name)
            req_skills = [s.skill_name for s in ck.skills if s.skill_type == "Required"]
            pref_skills = [s.skill_name for s in ck.skills if s.skill_type == "Preferred"]
            
            foundation = req_skills[:2]
            core = req_skills[2:len(req_skills)//2 + 1] if len(req_skills) > 2 else []
            industry = req_skills[len(req_skills)//2 + 1:] if len(req_skills) > 2 else []
            emerging = pref_skills
            
        return {
            "foundation_skills": foundation,
            "core_domain_skills": core,
            "industry_skills": industry,
            "emerging_skills": emerging,
            "status": "generating",
            "message": "AI is actively generating a detailed curriculum. These are preliminary skills."
        }

    doc = frappe.get_doc("Career Path", career_path)

    foundation = []
    core = []
    industry = []
    emerging = []

    # Process prerequisite skills as foundation tier
    for r in doc.prerequisite_skills:
        skill = r.prerequisite_skills
        if skill and skill not in foundation:
            foundation.append(skill)

    # Process standard milestones
    for m in doc.path_milestone:
        skill = m.skill
        if not skill:
            continue
        category = (m.category or "").strip().lower()
        if "foundation" in category:
            if skill not in foundation:
                foundation.append(skill)
        elif "core" in category:
            if skill not in core:
                core.append(skill)
        elif "industry" in category:
            if skill not in industry:
                industry.append(skill)
        elif "emerging" in category:
            if skill not in emerging:
                emerging.append(skill)
        else:
            if skill not in core:
                core.append(skill)

    return {
        "foundation_skills": foundation,
        "core_domain_skills": core,
        "industry_skills": industry,
        "emerging_skills": emerging
    }


# ══════════════════════════════════════════════════════════════════════════════
# 19. COMPLETE MILESTONE POINT
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def complete_milestone_point(enrollment, milestone_title, point_title, completed=True):
    """
    Marks a milestone checklist point as Completed or Not Started.
    If all points for the parent milestone are completed, automatically creates a Path Progress Log to mark the milestone as Completed.
    If a point is unchecked and the milestone was previously completed, deletes the Path Progress Log to revert it.
    Returns: { success: True, milestone_completed: bool }
    """
    if isinstance(completed, str):
        completed = completed.lower() in ("true", "1")

    doc = frappe.get_doc("Student Path Enrollment", enrollment)

    # Find the parent milestone in milestone_progress
    parent_milestone = next((r for r in doc.milestone_progress if r.milestone_title == milestone_title), None)
    if not parent_milestone:
        frappe.throw(f"Parent milestone '<b>{milestone_title}</b>' not found in enrollment.")

    # Enforce locking: cannot modify points for a locked milestone (i.e. idx > current_milestone_order or status is "Not Started")
    current_order = doc.current_milestone_order or 1
    if int(parent_milestone.idx) > int(current_order) or parent_milestone.status == "Not Started":
        frappe.throw(
            f"Cannot modify checklist for locked milestone '<b>{milestone_title}</b>'. "
            f"Please complete current milestone '<b>#{current_order}</b>' first."
        )
    
    # Find the point
    point_row = None
    for row in doc.milestone_points:
        if row.milestone_title == milestone_title and row.point_title == point_title:
            point_row = row
            break
            
    if not point_row:
        frappe.throw(f"Checklist point '<b>{point_title}</b>' not found under milestone '<b>{milestone_title}</b>'.")

    point_row.status = "Completed" if completed else "Not Started"

    # Save to ensure status is updated in the database
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    # Check if all points for this milestone are now completed
    siblings = [r for r in doc.milestone_points if r.milestone_title == milestone_title]
    all_completed = len(siblings) > 0 and all(r.status == "Completed" for r in siblings)

    milestone_completed = False
    
    has_skill = bool(parent_milestone.skill)
    
    if all_completed:
        if not has_skill:
            # Create Path Progress Log if not already exists
            if not frappe.db.exists("Path Progress Log", {"enrollment": enrollment, "milestone": parent_milestone.name}):
                log = frappe.get_doc({
                    "doctype": "Path Progress Log",
                    "student": doc.student,
                    "enrollment": enrollment,
                    "career_path": doc.career_path,
                    "milestone": parent_milestone.name,
                    "status": "Completed",
                    "score": 100,
                    "feedback": "Completed via checklist points."
                })
                log.insert(ignore_permissions=True)
                frappe.db.commit()
                milestone_completed = True
    else:
        # If not all completed, but the parent milestone was completed (Path Progress Log exists), delete the Path Progress Log
        existing_log = frappe.db.exists("Path Progress Log", {"enrollment": enrollment, "milestone": parent_milestone.name})
        if existing_log:
            frappe.delete_doc("Path Progress Log", existing_log, ignore_permissions=True)
            frappe.db.commit()
            
            # Reload enrollment and set milestone status to In Progress
            doc.reload()
            for r in doc.milestone_progress:
                if r.name == parent_milestone.name:
                    r.status = "In Progress"
                    r.completed_at = None
                    break
            
            # Recalculate milestone orders/locks
            recalculate_all_milestones(doc)
            doc.save(ignore_permissions=True)
            frappe.db.commit()

    return {"success": True, "milestone_completed": milestone_completed}


@frappe.whitelist()
def delete_student_enrollment(enrollment):
    """
    Deletes a Student Path Enrollment if it is in Paused or Generating status.
    """
    if not frappe.db.exists("Student Path Enrollment", enrollment):
        return {"status": "not_found"}
        
    doc = frappe.get_doc("Student Path Enrollment", enrollment)
    if doc.status in ["Paused", "Generating"]:
        frappe.delete_doc("Student Path Enrollment", enrollment, ignore_permissions=True)
        frappe.db.commit()
        return {"status": "success"}
    else:
        frappe.throw("Only paused or generating enrollments can be deleted.")