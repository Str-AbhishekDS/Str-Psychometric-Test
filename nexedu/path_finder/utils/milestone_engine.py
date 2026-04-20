"""
nexedu/path_finder/utils/milestone_engine.py
────────────────────────────────────────────────────────────────────────────
Central engine for all milestone lifecycle logic in Path Finder.

FIX LOG
───────
v2 fixes:
  - build_milestone_rows_from_path: "milestones" → "path_milestone" (correct
    child table fieldname from Career Path JSON schema)
  - recalculate_all_milestones Pass 3: corrected lock logic — every row that
    is not Completed/Skipped and is not the current row gets locked=1,
    regardless of its position relative to current.
"""

import frappe
from frappe.utils import today

LEVEL_ORDER = {
    "Beginner":     1,
    "Intermediate": 2,
    "Advanced":     3,
    "Expert":       4,
}

STATUS_NOT_STARTED = "Not Started"
STATUS_IN_PROGRESS = "In Progress"
STATUS_COMPLETED   = "Completed"
STATUS_SKIPPED     = "Skipped"


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def recalculate_all_milestones(enrollment_doc):
    """
    Full recalculation pass over enrollment_doc.milestone_progress.

    Steps
    ─────
    1. Sort rows by milestone_order ascending.
    2. Auto-skip rows where the student already has the linked skill at or
       above the required_skill_level.
    3. Find the FIRST row that is not Completed/Skipped → that is "current".
    4. Lock ALL rows except: completed, skipped, and current.
       (This fixes the original bug where rows before current got unlocked.)
    5. Set "In Progress" on current if it was "Not Started".
    6. Sync enrollment_doc.current_milestone_order.
       If no pending row exists → mark enrollment Completed.
    """
    if not enrollment_doc.milestone_progress:
        return

    student_skills = get_student_skill_set(enrollment_doc.student)
    rows = sorted(
        enrollment_doc.milestone_progress,
        key=lambda r: int(r.milestone_order or 0),
    )

    # ── Pass 1: auto-skip ────────────────────────────────────────────────────
    for row in rows:
        if row.status in (STATUS_COMPLETED, STATUS_SKIPPED):
            continue

        skill = row.get("linked_skill") or row.get("skill")
        if not skill:
            continue

        required_level = row.get("required_skill_level") or "Beginner"
        required_rank  = LEVEL_ORDER.get(required_level, 1)
        student_level  = student_skills.get(skill)
        student_rank   = LEVEL_ORDER.get(student_level, 0) if student_level else 0

        if student_rank >= required_rank:
            row.status       = STATUS_SKIPPED
            row.is_skipped   = 1
            row.is_lock      = 0
            row.completed_on = row.completed_on or today()

    # ── Pass 2: find current (first non-done row) ────────────────────────────
    current_row = None
    for row in rows:
        if row.status not in (STATUS_COMPLETED, STATUS_SKIPPED):
            current_row = row
            break

    # ── Pass 3: apply lock / unlock correctly ────────────────────────────────
    #
    #  Rule: a row is UNLOCKED only if it is Completed, Skipped, or Current.
    #  Everything else is LOCKED.
    #  This prevents any row "before" current from being accidentally editable
    #  (edge case: a not-started row before current due to ordering bugs).
    #
    for row in rows:
        if row.status in (STATUS_COMPLETED, STATUS_SKIPPED):
            row.is_lock = 0
            continue

        if current_row and row.name == current_row.name:
            # Current milestone: unlock and activate
            row.is_lock = 0
            if row.status == STATUS_NOT_STARTED:
                row.status     = STATUS_IN_PROGRESS
                row.started_on = row.started_on or today()
        else:
            # Every other pending/not-started row → locked
            row.is_lock = 1

    # ── Pass 4: sync enrollment ──────────────────────────────────────────────
    if current_row:
        enrollment_doc.current_milestone_order = int(current_row.milestone_order or 1)
    else:
        enrollment_doc.status = STATUS_COMPLETED


def update_milestone_status(row, enrollment_doc):
    """
    Per-row status enforcement called from StudentPathEnrollment.before_save.

    Rules
    ─────
    - Locked rows: silently ignored (no changes allowed).
    - is_skipped checkbox ticked → force status = Skipped.
    - Build  milestone completing → must have project_link.
    - Assess milestone completing → score must be >= pass_percentage.
    - Apply  milestone completing → review_status must be "Approved".
    - Sets completed_on when status reaches Completed/Skipped.
    """
    # Locked rows are read-only
    if row.is_lock:
        return

    # is_skipped checkbox → force Skipped status
    if row.get("is_skipped"):
        row.status       = STATUS_SKIPPED
        row.completed_on = row.completed_on or today()
        return

    # Only enforce rules when marking Completed
    if row.status != STATUS_COMPLETED:
        return

    # ── Type-specific rules ───────────────────────────────────────────────────
    if row.milestone_type == "Build":
        if not row.get("project_link"):
            frappe.throw(
                f"Milestone <b>{row.milestone_title}</b>: "
                "Please add a Project Link before marking as Completed."
            )

    elif row.milestone_type == "Assess":
        score    = float(row.get("score") or 0)
        pass_pct = float(row.get("pass_percentage") or 50)
        if score < pass_pct:
            frappe.throw(
                f"Milestone <b>{row.milestone_title}</b>: "
                f"Score {score} is below the required pass percentage {pass_pct}."
            )

    elif row.milestone_type == "Apply":
        if row.get("review_status") != "Approved":
            frappe.throw(
                f"Milestone <b>{row.milestone_title}</b>: "
                "Apply milestone must be Approved (check Review Status) before completing."
            )

    # Set completion timestamp
    if not row.completed_on:
        row.completed_on = today()


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def get_student_skill_set(student):
    """Returns {skill_name: current_level} dict for a student."""
    rows = frappe.db.get_all(
        "Student Skill",
        filters={"student": student},
        fields=["skill", "current_level"],
    )
    return {r["skill"]: r["current_level"] for r in rows}


def build_milestone_rows_from_path(career_path_name, order_offset=0):
    """
    Fetches Path Milestone rows for a career path and returns a list of dicts
    ready to append() onto enrollment_doc.milestone_progress.

    FIX: child table fieldname is "path_milestone" (not "milestones").
         This is the name from the Career Path → Path Milestone JSON schema.

    order_offset: added to each milestone's own order value so prereq
                  milestones are sequenced before main path milestones.
    """
    path_doc   = frappe.get_doc("Career Path", career_path_name)
    # ✅ FIX: correct child table field name from Career Path JSON schema
    milestones = sorted(
        path_doc.get("path_milestone") or [],
        key=lambda m: int(m.order or 0),
    )

    rows = []
    for m in milestones:
        rows.append({
            "milestone":            m.name,
            "milestone_title":      m.milestone_title,
            "milestone_order":      int(m.order or 0) + order_offset,
            "milestone_type":       m.milestone_type,
            "linked_skill":         m.get("skill"),
            "required_skill_level": m.get("required_skill_level"),
            "is_skippable":         m.get("is_skippable") or 0,
            "assessment":           m.get("assessment"),
            "pass_percentage":      m.get("pass_percentage") or 50,
            "status":               STATUS_NOT_STARTED,
            "is_lock":              1,
            "is_skipped":           0,
            "source_path":          career_path_name,
        })
    return rows


def prepend_prerequisite_milestones(enrollment_doc, prereq_path_names):
    """
    Inserts prerequisite path milestones BEFORE the main path milestones
    in enrollment_doc.milestone_progress, re-sequencing all order numbers.

    prereq_path_names: list of Career Path name strings.

    How ordering works
    ──────────────────
    Prereq Path A has milestones with order 1, 2, 3  → stored as 1, 2, 3
    Prereq Path B has milestones with order 1, 2     → stored as 4, 5
    Main path milestones with order 1, 2, 3          → stored as 6, 7, 8

    Total prereq rows = 5, so main path rows get +5 offset.
    """
    if not prereq_path_names:
        return

    # ── 1. Build prereq rows with contiguous ordering ────────────────────────
    prereq_rows    = []
    current_offset = 0
    for path_name in prereq_path_names:
        batch = build_milestone_rows_from_path(path_name, order_offset=current_offset)
        if batch:
            current_offset = batch[-1]["milestone_order"]
        prereq_rows.extend(batch)

    if not prereq_rows:
        return

    total_prereq = len(prereq_rows)

    # ── 2. Snapshot and re-sequence existing main milestones ─────────────────
    existing_snapshot = sorted(
        [
            {
                "milestone":            r.milestone,
                "milestone_title":      r.milestone_title,
                "milestone_order":      int(r.milestone_order or 0) + total_prereq,
                "milestone_type":       r.milestone_type,
                "linked_skill":         r.get("linked_skill"),
                "required_skill_level": r.get("required_skill_level"),
                "is_skippable":         r.get("is_skippable") or 0,
                "assessment":           r.get("assessment"),
                "pass_percentage":      r.get("pass_percentage") or 50,
                "status":               r.status,
                "is_lock":              r.is_lock,
                "is_skipped":           r.get("is_skipped") or 0,
                "source_path":          r.get("source_path") or enrollment_doc.career_path,
            }
            for r in enrollment_doc.milestone_progress
        ],
        key=lambda x: x["milestone_order"],
    )

    # ── 3. Clear and rebuild in correct order ────────────────────────────────
    enrollment_doc.set("milestone_progress", [])

    for row_data in prereq_rows:
        enrollment_doc.append("milestone_progress", row_data)

    for row_data in existing_snapshot:
        enrollment_doc.append("milestone_progress", row_data)