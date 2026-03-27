# ============================================================
#  Path Finder — Milestone Status Engine
#  File   : pathfinder/utils/milestone_engine.py
#  Usage  : import and call update_milestone_status(row, enrollment_doc)
#           from before_save, after_insert, or any trigger hook.
# ============================================================

import frappe
from frappe import _
from frappe.utils import today, nowdate


# ─────────────────────────────────────────────────────────────
#  MAIN ENTRY POINT
#  Call this function from every trigger that can change a
#  milestone's completion state.
# ─────────────────────────────────────────────────────────────

def update_milestone_status(row, enrollment_doc):
    """
    Central function that decides the correct status for one
    milestone row inside Student Milestone Progress.

    Args:
        row             : A single child-table row object
                          (Student Milestone Progress)
        enrollment_doc  : The parent Student Enrollment document

    Returns:
        bool : True if the status was changed, False otherwise
    """

    # Never touch a locked milestone
    if row.is_lock:
        return False

    # Already completed — nothing to re-evaluate
    if row.status == "Completed":
        return False

    student = enrollment_doc.student
    original_status = row.status
    milestone_type  = row.milestone_type or _get_milestone_type(row.milestone)

    # ── Route to the correct handler ──────────────────────────
    if milestone_type == "Learn":
        _handle_learn(row, student)

    elif milestone_type == "Build":
        _handle_build(row)

    elif milestone_type == "Assess":
        _handle_assess(row, student)

    elif milestone_type == "Apply":
        _handle_apply(row)

    elif milestone_type == "Connect":
        _handle_connect(row)

    else:
        frappe.log_error(
            f"Unknown milestone_type '{milestone_type}' on milestone {row.milestone}",
            "Path Finder – Milestone Engine"
        )
        return False

    # ── Post-processing ───────────────────────────────────────
    status_changed = row.status != original_status

    if status_changed:
        # Stamp completion date when finishing
        if row.status in ("Completed", "Skipped") and not row.completed_on:
            row.completed_on = today()

        # Stamp start date on first activity
        if row.status == "In Progress" and not row.started_on:
            row.started_on = today()

        # Refresh lock state for ALL rows after any change
        _refresh_locks(enrollment_doc)

        # Update parent's current_milestone pointer
        _update_current_milestone(enrollment_doc)

    return status_changed

import frappe
from datetime import date


def recalculate_all_milestones(enrollment):
    """
    Main engine:
    1. Auto-skip
    2. Update status
    3. Lock/unlock
    4. Current milestone
    5. Progress %
    """

    auto_skip(enrollment)

    for row in enrollment.milestone_progress:
        update_milestone_status(row, enrollment)

    refresh_locks(enrollment)
    update_current_milestone(enrollment)
    update_progress(enrollment)


# 🔹 AUTO SKIP
def auto_skip(enrollment):

    student_skills = frappe.get_all(
        "Student Skill",
        filters={"parent": enrollment.student},
        pluck="skill"
    )

    for row in enrollment.milestone_progress:
        if row.is_skippable and row.linked_skill:
            if row.linked_skill in student_skills:
                row.status = "Skipped"
                row.is_skipped = 1
                row.completed_on = date.today()


# 🔹 STATUS LOGIC
def update_milestone_status(row, enrollment):

    old_status = row.status

    # LEARN
    if row.milestone_type == "Learn":
        student_skills = frappe.get_all(
            "Student Skill",
            filters={"parent": enrollment.student},
            pluck="skill"
        )
        if row.linked_skill in student_skills:
            row.status = "Completed"

    # BUILD
    elif row.milestone_type == "Build":
        if row.project_link:
            row.status = "Completed"
        else:
            row.status = "In Progress"

    # ASSESS
    elif row.milestone_type == "Assess":
        submission = frappe.get_all(
            "Assessment Submission",
            filters={
                "student": enrollment.student,
                "assessment": row.assessment
            },
            fields=["score"]
        )
        if submission:
            score = submission[0].score or 0
            row.score = score
            if score >= (row.pass_percentage or 50):
                row.status = "Completed"
            else:
                row.status = "In Progress"

    # APPLY
    elif row.milestone_type == "Apply":
        if row.review_status == "Approved":
            row.status = "Completed"
        else:
            row.status = "In Progress"

    return old_status != row.status


# 🔹 LOCK LOGIC
def refresh_locks(enrollment):

    rows = sorted(enrollment.milestone_progress, key=lambda x: x.milestone_order or 0)

    for i, row in enumerate(rows):
        if i == 0:
            row.is_locked = 0
        else:
            prev = rows[i - 1]
            if prev.status in ["Completed", "Skipped"]:
                row.is_locked = 0
            else:
                row.is_locked = 1


# 🔹 CURRENT MILESTONE
def update_current_milestone(enrollment):

    rows = sorted(enrollment.milestone_progress, key=lambda x: x.milestone_order or 0)

    for row in rows:
        if row.status == "In Progress":
            enrollment.current_milestone = row.milestone
            return

    for row in rows:
        if row.status == "Not Started" and not row.is_locked:
            enrollment.current_milestone = row.milestone
            return

    enrollment.current_milestone = None


# 🔹 PROGRESS %
def update_progress(enrollment):

    total = len(enrollment.milestone_progress)
    completed = len([r for r in enrollment.milestone_progress if r.status in ["Completed", "Skipped"]])

    if total:
        enrollment.progress_percent = (completed / total) * 100
    else:
        enrollment.progress_percent = 0


# ─────────────────────────────────────────────────────────────
#  TYPE HANDLERS
# ─────────────────────────────────────────────────────────────

def _handle_learn(row, student):
    """
    Learn milestone — two paths:
      A) Student already has the linked skill  → auto-skip
      B) Student manually clicks "Mark Complete" → Completed
         (the button sets row.status = "Completed" before save,
          so we just validate and accept it here)
    """
    # Path A: auto-skip if skill already in student profile
    if row.linked_skill and row.is_skippable:
        already_has = frappe.db.exists("Student Skill", {
            "parent": student,
            "skill" : row.linked_skill
        })
        if already_has:
            row.status     = "Skipped"
            row.is_skipped = 1
            return

    # Path B: manual completion — accept whatever the UI set,
    # but only allow In Progress or Completed (not backward)
    if row.status not in ("Not Started", "In Progress", "Completed"):
        row.status = "In Progress"


def _handle_build(row):
    """
    Build milestone — completion requires a project submission.
    Student submits a URL (project_link) or a file attachment.
    """
    if row.project_link:
        # Project submitted → mark complete
        row.status = "Completed"
    elif row.status == "Not Started":
        # First interaction — move to In Progress so the student
        # sees this milestone is now active
        pass  # stays Not Started until they submit
    # If already In Progress and no link yet, stay In Progress


def _handle_assess(row, student):
    """
    Assess milestone — completion requires passing an Assessment.
    Queries Assessment Submission for a passing score.
    pass_percentage comes from the milestone master (default 50).
    """
    if not row.assessment:
        # No assessment linked — treat like Learn (manual)
        frappe.msgprint(
            _(f"Milestone '{row.milestone_title}' has type Assess but no linked Assessment. Please link one."),
            alert=True
        )
        return

    pass_pct = _get_pass_percentage(row.milestone) or 50.0

    # Fetch best submission for this student + assessment
    submissions = frappe.get_all(
        "Assessment Submission",
        filters={
            "student"   : student,
            "assessment": row.assessment
        },
        fields=["score", "creation"],
        order_by="score desc",
        limit=1
    )

    if not submissions:
        # No attempt yet
        if row.status == "Not Started":
            pass  # wait for first attempt
        return

    best_score = submissions[0].score or 0.0
    row.score  = best_score

    if best_score >= pass_pct:
        row.status = "Completed"
    else:
        # Attempted but not passed
        row.status = "In Progress"
        frappe.msgprint(
            _(f"Score {best_score:.1f}% — need {pass_pct:.0f}% to pass '{row.milestone_title}'."),
            alert=True
        )


def _handle_apply(row):
    """
    Apply milestone — requires admin/mentor approval.
    Student submits work → admin sets review_status.
    Approved  → Completed
    Rejected  → back to In Progress (student must resubmit)
    Pending   → In Progress (waiting for review)
    """
    review = row.review_status

    if review == "Approved":
        row.status = "Completed"

    elif review == "Rejected":
        row.status     = "In Progress"
        row.review_status = "Rejected"   # keep the rejection flag
        frappe.msgprint(
            _(f"Milestone '{row.milestone_title}' was rejected. Please revise and resubmit."),
            alert=True
        )

    elif review == "Pending":
        row.status = "In Progress"

    else:
        # No submission yet — stay as is
        pass


def _handle_connect(row):
    """
    Connect milestone — pure manual, no automation.
    The UI button sets status = "Completed" directly.
    This handler just validates nothing invalid slipped in.
    """
    allowed = ("Not Started", "In Progress", "Completed")
    if row.status not in allowed:
        row.status = "In Progress"


# ─────────────────────────────────────────────────────────────
#  LOCK / UNLOCK  (runs after every status change)
# ─────────────────────────────────────────────────────────────

def _refresh_locks(enrollment_doc):
    """
    Re-evaluate is_locked for every milestone row.
    Rule: a milestone is UNLOCKED if the row before it
          (by milestone_order) has status Completed OR Skipped.
    The very first row is always unlocked.
    """
    rows = sorted(
        enrollment_doc.milestone_progress,
        key=lambda r: r.milestone_order or 0
    )

    for idx, row in enumerate(rows):
        if idx == 0:
            row.is_lock = 0   # first milestone always open
        else:
            prev_status = rows[idx - 1].status
            row.is_lock = 0 if prev_status in ("Completed", "Skipped") else 1


# ─────────────────────────────────────────────────────────────
#  CURRENT MILESTONE POINTER
# ─────────────────────────────────────────────────────────────

def _update_current_milestone(enrollment_doc):
    """
    Set enrollment_doc.current_milestone to the first row
    that is In Progress, or if none, the first unlocked
    Not Started row.
    """
    rows = sorted(
        enrollment_doc.milestone_progress,
        key=lambda r: r.milestone_order or 0
    )

    # Priority 1: first In Progress
    for row in rows:
        if row.status == "In Progress":
            enrollment_doc.current_milestone = row.milestone
            return

    # Priority 2: first unlocked Not Started
    for row in rows:
        if row.status == "Not Started" and not row.is_lock:
            enrollment_doc.current_milestone = row.milestone
            return

    # All done — clear the pointer
    enrollment_doc.current_milestone = None


# ─────────────────────────────────────────────────────────────
#  BULK ENTRY POINT — run for ALL rows in one enrollment
#  Call this from after_insert or a "Recalculate" button.
# ─────────────────────────────────────────────────────────────

def recalculate_all_milestones(enrollment_doc):
    """
    Run update_milestone_status for every milestone row.
    Useful on:
      - New enrollment (initial auto-skip pass)
      - "Recalculate" admin button
      - After bulk skill import
    """
    rows = sorted(
        enrollment_doc.milestone_progress,
        key=lambda r: r.milestone_order or 0
    )

    for row in rows:
        # Temporarily unlock locked rows so auto-skip can apply
        # to all milestones, then re-lock in _refresh_locks
        original_lock = row.is_lock
        row.is_lock = 0
        update_milestone_status(row, enrollment_doc)
        row.is_lock = original_lock

    # Final lock pass based on new statuses
    _refresh_locks(enrollment_doc)
    _update_current_milestone(enrollment_doc)


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────

def _get_milestone_type(milestone_name):
    """Fetch milestone_type from the Path Milestone master."""
    if not milestone_name:
        return None
    return frappe.db.get_value("Path Milestone", milestone_name, "milestone_type")


def _get_pass_percentage(milestone_name):
    """Fetch pass_percentage from Path Milestone master."""
    if not milestone_name:
        return 50.0
    val = frappe.db.get_value("Path Milestone", milestone_name, "pass_percentage")
    return float(val) if val else 50.0


# ─────────────────────────────────────────────────────────────
#  HOW TO WIRE THIS INTO YOUR DOCTYPES
# ─────────────────────────────────────────────────────────────
#
#  1. Student Enrollment — student_enrollment.py
#  ──────────────────────────────────────────────
#  from pathfinder.utils.milestone_engine import recalculate_all_milestones, update_milestone_status
#
#  def after_insert(self):
#      recalculate_all_milestones(self)   # auto-skip known skills on enroll
#
#  def before_save(self):
#      for row in self.milestone_progress:
#          update_milestone_status(row, self)
#
#
#  2. Assessment Submission — assessment_submission.py
#  ────────────────────────────────────────────────────
#  def on_submit(self):
#      enrollments = frappe.get_all("Student Enrollment",
#          filters={"student": self.student, "docstatus": 1})
#      for e in enrollments:
#          doc = frappe.get_doc("Student Enrollment", e.name)
#          for row in doc.milestone_progress:
#              if row.assessment == self.assessment:
#                  update_milestone_status(row, doc)
#          doc.save(ignore_permissions=True)
#
#
#  3. Progress Log — progress_log.py
#  ───────────────────────────────────
#  def on_submit(self):
#      enrollment = frappe.get_doc("Student Enrollment", self.enrollment)
#      for row in enrollment.milestone_progress:
#          if row.milestone == self.milestone:
#              update_milestone_status(row, enrollment)
#      enrollment.save(ignore_permissions=True)
#
#
#  4. Client Script — "Mark as Completed" button (Learn / Connect)
#  ──────────────────────────────────────────────────────────────
#  frappe.call({
#      method: "pathfinder.utils.milestone_engine.mark_completed_from_ui",
#      args: { enrollment: frm.doc.name, milestone_row_name: row.name },
#      callback: (r) => { frm.reload_doc(); }
#  });
#


# ─────────────────────────────────────────────────────────────
#  WHITELISTED API — called from client script buttons
# ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def mark_completed_from_ui(enrollment, milestone_row_name):
    """
    Called by the 'Mark as Completed' button on Learn / Connect
    milestones. Sets status to Completed and saves.
    """
    doc = frappe.get_doc("Student Enrollment", enrollment)

    for row in doc.milestone_progress:
        if row.name == milestone_row_name:
            if row.is_lock:
                frappe.throw(_("This milestone is locked. Complete the previous milestone first."))
            if row.milestone_type not in ("Learn", "Connect"):
                frappe.throw(_("Only Learn and Connect milestones can be manually completed."))
            row.status       = "Completed"
            row.completed_on = today()
            break

    _refresh_locks(doc)
    _update_current_milestone(doc)
    doc.save(ignore_permissions=True)

    return {"status": "success"}


@frappe.whitelist()
def submit_project_link(enrollment, milestone_row_name, project_link):
    """
    Called by the 'Submit Project' button on Build milestones.
    """
    if not project_link:
        frappe.throw(_("Project link cannot be empty."))

    doc = frappe.get_doc("Student Enrollment", enrollment)

    for row in doc.milestone_progress:
        if row.name == milestone_row_name:
            if row.is_lock:
                frappe.throw(_("This milestone is locked."))
            if row.milestone_type != "Build":
                frappe.throw(_("Only Build milestones accept a project link."))
            row.project_link = project_link
            update_milestone_status(row, doc)
            break

    doc.save(ignore_permissions=True)
    return {"status": "success"}


@frappe.whitelist()
def send_for_review(enrollment, milestone_row_name):
    """
    Called by the 'Send for Review' button on Apply milestones.
    Sets review_status = Pending and triggers a notification.
    """
    doc = frappe.get_doc("Student Enrollment", enrollment)

    for row in doc.milestone_progress:
        if row.name == milestone_row_name:
            if row.is_lock:
                frappe.throw(_("This milestone is locked."))
            if row.milestone_type != "Apply":
                frappe.throw(_("Only Apply milestones can be sent for review."))
            row.review_status = "Pending"
            row.status        = "In Progress"
            row.started_on    = row.started_on or today()
            break

    doc.save(ignore_permissions=True)

    # Notify mentor/admin
    frappe.sendmail(
        recipients=_get_mentor_emails(doc),
        subject=_(f"Milestone review requested — {doc.student_name}"),
        message=_(f"Student {doc.student_name} has submitted a milestone for review in enrollment {enrollment}.")
    )

    return {"status": "success"}


@frappe.whitelist()
def approve_or_reject(enrollment, milestone_row_name, decision, remarks=None):
    """
    Called by the mentor/admin Approve or Reject button
    on Apply milestones.
    decision: "Approved" or "Rejected"
    """
    if decision not in ("Approved", "Rejected"):
        frappe.throw(_("Decision must be Approved or Rejected."))

    doc = frappe.get_doc("Student Enrollment", enrollment)

    for row in doc.milestone_progress:
        if row.name == milestone_row_name:
            row.review_status = decision
            update_milestone_status(row, doc)
            break

    doc.save(ignore_permissions=True)
    return {"status": "success"}


# ─────────────────────────────────────────────────────────────
#  INTERNAL HELPER
# ─────────────────────────────────────────────────────────────

def _get_mentor_emails(enrollment_doc):
    """Return list of mentor email addresses for notification."""
    emails = []
    if hasattr(enrollment_doc, "mentor") and enrollment_doc.mentor:
        email = frappe.db.get_value("User", enrollment_doc.mentor, "email")
        if email:
            emails.append(email)
    if not emails:
        # Fallback: notify all users with Instructor role
        emails = [r[0] for r in frappe.db.get_all(
            "Has Role",
            filters={"role": "Instructor"},
            fields=["parent"],
            as_list=True
        )]
    return emails or ["admin@example.com"]