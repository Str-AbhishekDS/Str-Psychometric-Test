# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt
#
# nexedu/path_finder/utils/milestone_engine.py
# ─────────────────────────────────────────────────────────────────────────────
# Core engine for:
#   1. Building milestone_progress rows (prereqs first, then path milestones)
#   2. Recalculating all milestone statuses after changes
#   3. Auto-skipping milestones whose skill the student already has (verified)
#   4. Fit score calculation for career path suggestions
# ─────────────────────────────────────────────────────────────────────────────

import frappe
from frappe.utils import now_datetime

LEVEL_RANK = {"Beginner": 1, "Intermediate": 2, "Advanced": 3}


def level_rank(level):
    return LEVEL_RANK.get(level or "Beginner", 1)


# ══════════════════════════════════════════════════════════════════════════════
# BUILD MILESTONE ROWS
# ══════════════════════════════════════════════════════════════════════════════

def build_milestone_rows_from_path(career_path, student=None, order_offset=0):
    """
    Returns a list of dicts to be appended into enrollment.milestone_progress.

    Structure:
        Section 1 — Prerequisite Skills (from Career Path → prerequisite_skills table)
            One row per prerequisite skill entry (milestone_type = "Learn", is_prereq = 1)
        Section 2 — Path Milestones (from Career Path → path_milestone child table)
            Rows sorted by idx

    If student is given, any prereq skill already verified on the student
    is created with status="Completed" and is_auto_skipped=1.

    Returns list of dicts (NOT frappe document rows — caller does append()).
    """
    rows = []

    # ── Get student's verified skills once ───────────────────────────────────
    student_skill_map = {}
    if student:
        student_skills = frappe.get_all(
            "Student Skill",
            filters={"student": student},
            fields=["skill", "current_level", "status"],
        )
        student_skill_map = {
            s.skill: s for s in student_skills
        }

    # ── SECTION 1: Prerequisite Skills ───────────────────────────────────────
    prereq_skills = frappe.get_all(
        "Prerequisite Skills",
        filters={"parent": career_path, "parentfield": "prerequisite_skills"},
        fields=["prerequisite_skills", "level", "idx"],
        order_by="idx asc",
    )

    for prereq in prereq_skills:
        skill = prereq.prerequisite_skills
        req_level = prereq.level or "Beginner"
        student_entry = student_skill_map.get(skill) if skill else None
        already_has = (
            student_entry
            and level_rank(student_entry.current_level) >= level_rank(req_level)
        )
        is_verified = bool(student_entry and student_entry.get("status") == "Verified")

        status = "Completed" if (already_has and is_verified) else "Not Started"
        is_auto_skip = 1 if (already_has and is_verified) else 0

        rows.append({
            "milestone_title"     : f"Prerequisite: {skill}",
            "milestone_order"     : len(rows) + 1,
            "milestone_type"      : "Learn",
            "is_prereq"           : 1,
            "is_mandatory"        : 1,
            "skill"               : skill,
            "required_skill_level": req_level,
            "status"              : status,
            "is_auto_skipped"     : is_auto_skip,
            "is_lock"             : 0,
            "completed_at"        : now_datetime() if is_auto_skip else None,
        })

    # ── SECTION 2: Path Milestones ────────────────────────────────────────────
    path_milestones = frappe.get_all(
        "Path Milestone",
        filters={"parent": career_path, "parentfield": "path_milestone"},
        fields=[
            "name", "milestone_title", "milestone_type", "skill",
            "category", "topic", "subtopic", "required_skill_level",
            "is_mandatory", "duration_days", "linked_resource",
            "linked_resource_type", "pass_percentage", "assessment", "idx",
        ],
        order_by="idx asc",
    )

    for i, pm in enumerate(path_milestones):
        # Check if student already has this milestone's skill
        student_entry = student_skill_map.get(pm.skill) if pm.skill else None
        already_has   = (
            student_entry
            and pm.skill
            and level_rank(student_entry.current_level) >= level_rank(pm.required_skill_level)
        )
        is_verified   = bool(student_entry and student_entry.get("status") == "Verified")

        # Auto-complete if student already has verified skill for this milestone
        if already_has and is_verified and pm.skill:
            status       = "Completed"
            is_auto_skip = 1
        else:
            status       = "Not Started"
            is_auto_skip = 0

        rows.append({
            "milestone_title"     : pm.milestone_title,
            "milestone_order"     : len(rows) + 1,
            "milestone_type"      : pm.milestone_type,
            "is_prereq"           : 0,
            "is_mandatory"        : pm.is_mandatory if pm.is_mandatory is not None else 1,
            "skill"               : pm.skill,
            "required_skill_level": pm.required_skill_level,
            "category"            : pm.category,
            "topic"               : pm.topic,
            "subtopic"            : pm.subtopic,
            "duration_days"       : pm.duration_days,
            "linked_resource"     : pm.linked_resource,
            "linked_resource_type": pm.linked_resource_type,
            "pass_percentage"     : pm.pass_percentage,
            "assessment"          : pm.assessment,
            "status"              : status,
            "is_auto_skipped"     : is_auto_skip,
            "is_lock"             : 0,
            "completed_at"        : now_datetime() if is_auto_skip else None,
            "score"               : 100 if is_auto_skip else None,
            "ai_feedback"         : "Skill already verified — auto-completed." if is_auto_skip else None,
            # Store source milestone name for reference/linking
            "source_milestone"    : pm.name,
        })

    return rows


# ══════════════════════════════════════════════════════════════════════════════
# RECALCULATE ALL MILESTONES
# ══════════════════════════════════════════════════════════════════════════════

def recalculate_all_milestones(enrollment_doc):
    """
    After building rows, set the first non-completed row to 'In Progress'
    and lock any rows that come after incomplete mandatory prerequisites.

    enrollment_doc: StudentPathEnrollment document (in memory, not yet saved)
    """
    rows = enrollment_doc.milestone_progress
    if not rows:
        return

    # Find first non-completed row → set as In Progress
    found_current = False
    for row in rows:
        if row.status == "Completed":
            row.is_lock = 0
            continue
        if not found_current:
            row.status   = "In Progress"
            row.is_lock  = 0
            found_current = True
            enrollment_doc.current_milestone_order = row.idx
        else:
            row.status  = "Not Started"
            row.is_lock = 0  # unlock all; locking happens per-action


def update_milestone_status(row, enrollment_doc):
    """
    Called in before_save for each milestone_progress row.
    Ensures completed_at is set when status → Completed.
    """
    if row.status == "Completed" and not row.completed_at:
        row.completed_at = now_datetime()
    if row.status != "Completed":
        row.completed_at = None


# ══════════════════════════════════════════════════════════════════════════════
# FIT SCORE ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def calculate_fit_score(student, career_path_name):
    """
    Calculates a fit score (0–100) for a student against a career path.

    Scoring formula:
        - Each skill in path milestones + prerequisite_skills counts as 1 point
        - Student gets full point if they have the skill at or above required level (verified)
        - Student gets 0.5 point if they have the skill but below required level
        - Student gets 0 if skill is missing entirely
        - Final score = (weighted_match / total_skills) * 100

    Returns dict:
        {
            fit_score        : float,
            matched_count    : int,
            partial_count    : int,
            missing_count    : int,
            total_skills     : int,
            matched_skills   : list,
            partial_skills   : list,
            missing_skills   : list,
        }
    """
    # Get all skills required by this path (prereqs + milestones)
    skill_requirements = _get_all_path_skills(career_path_name)

    if not skill_requirements:
        return {
            "fit_score"    : 100,
            "matched_count": 0,
            "partial_count": 0,
            "missing_count": 0,
            "total_skills" : 0,
            "matched_skills": [],
            "partial_skills": [],
            "missing_skills": [],
        }

    # Get student skills
    student_skills = frappe.get_all(
        "Student Skill",
        filters={"student": student},
        fields=["skill", "current_level", "status"],
    )
    student_skill_map = {s.skill: s for s in student_skills}

    matched_skills = []
    partial_skills = []
    missing_skills = []
    weighted_score = 0.0

    for skill_name, req in skill_requirements.items():
        student_entry  = student_skill_map.get(skill_name)
        required_level = req.get("required_skill_level") or "Beginner"

        if not student_entry:
            missing_skills.append({
                "skill"         : skill_name,
                "required_level": required_level,
                "current_level" : None,
                "is_prereq"     : req.get("is_prereq", 0),
            })
        elif level_rank(student_entry.current_level) >= level_rank(required_level):
            matched_skills.append({
                "skill"         : skill_name,
                "required_level": required_level,
                "current_level" : student_entry.current_level,
                "is_verified"   : 1 if student_entry.get("status") == "Verified" else 0,
                "is_prereq"     : req.get("is_prereq", 0),
            })
            weighted_score += 1.0
        else:
            partial_skills.append({
                "skill"         : skill_name,
                "required_level": required_level,
                "current_level" : student_entry.current_level,
                "is_prereq"     : req.get("is_prereq", 0),
            })
            weighted_score += 0.5

    total      = len(skill_requirements)
    fit_score  = round((weighted_score / total) * 100, 1) if total else 100

    return {
        "fit_score"     : fit_score,
        "matched_count" : len(matched_skills),
        "partial_count" : len(partial_skills),
        "missing_count" : len(missing_skills),
        "total_skills"  : total,
        "matched_skills": matched_skills,
        "partial_skills": partial_skills,
        "missing_skills": missing_skills,
    }


def _get_all_path_skills(career_path_name):
    """
    Collects all unique skills from:
      1. prerequisite_skills child table
      2. path_milestone child table
    Returns dict: { skill_name: {required_skill_level, is_prereq} }
    Using highest required level when a skill appears multiple times.
    """
    skill_map = {}

    # Prereq skills
    prereqs = frappe.get_all(
        "Prerequisite Skills",
        filters={"parent": career_path_name, "parentfield": "prerequisite_skills"},
        fields=["prerequisite_skills", "level"],
    )
    for p in prereqs:
        skill = p.prerequisite_skills
        if not skill:
            continue
        existing = skill_map.get(skill)
        req_level = p.level or "Beginner"
        if not existing or level_rank(req_level) > level_rank(existing["required_skill_level"]):
            skill_map[skill] = {
                "required_skill_level": req_level,
                "is_prereq"           : 1,
            }

    # Path milestone skills
    milestones = frappe.get_all(
        "Path Milestone",
        filters={"parent": career_path_name, "parentfield": "path_milestone"},
        fields=["skill", "required_skill_level"],
    )
    for m in milestones:
        if not m.skill:
            continue
        existing = skill_map.get(m.skill)
        if not existing or level_rank(m.required_skill_level) > level_rank(existing.get("required_skill_level", "Beginner")):
            skill_map[m.skill] = {
                "required_skill_level": m.required_skill_level or "Beginner",
                "is_prereq"           : existing.get("is_prereq", 0) if existing else 0,
            }

    return skill_map


def get_top_path_suggestions(student, limit=5):
    """
    Computes fit scores for ALL published career paths for a student
    and returns the top N sorted by fit_score descending.

    Returns list of dicts:
        [{
            career_path       : str,
            target_role       : str,
            difficulty_level  : str,
            fit_score         : float,
            matched_count     : int,
            partial_count     : int,
            missing_count     : int,
            total_skills      : int,
            estimated_duration: int,
            average_salary    : float,
        }]
    """
    published_paths = frappe.get_all(
        "Career Path",
        filters={"published": 1},
        fields=[
            "name", "path_name", "target_role", "difficulty_level",
            "estimated_duration_months", "average_salary_lpa", "success_stories",
        ],
    )

    results = []
    for cp in published_paths:
        score_data = calculate_fit_score(student, cp.name)
        results.append({
            "career_path"       : cp.name,
            "path_name"         : cp.path_name,
            "target_role"       : cp.target_role,
            "difficulty_level"  : cp.difficulty_level,
            "fit_score"         : score_data["fit_score"],
            "matched_count"     : score_data["matched_count"],
            "partial_count"     : score_data["partial_count"],
            "missing_count"     : score_data["missing_count"],
            "total_skills"      : score_data["total_skills"],
            "matched_skills"    : score_data["matched_skills"],
            "partial_skills"    : score_data["partial_skills"],
            "missing_skills"    : score_data["missing_skills"],
            "estimated_duration": cp.estimated_duration_months,
            "average_salary"    : cp.average_salary_lpa,
            "success_stories"   : cp.success_stories,
        })

    results.sort(key=lambda x: x["fit_score"], reverse=True)
    return results[:limit]