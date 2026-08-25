# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt
#
# nexedu/path_finder/doctype/path_progress_log/path_progress_log.py
# ─────────────────────────────────────────────────────────────────────────────
# CORE DESIGN CHANGE:
#   `self.milestone` now stores the NAME of a child row in
#   Student Path Enrollment → milestone_progress (e.g. "abc123xyz").
#   This is the enrollment's child table row — NOT a Path Milestone doctype name.
#
#   Each child row IS one milestone. Its idx is the sequence position.
#   When a PPL is saved:
#     1. That child row → status = "Completed", completed_at = now
#     2. current_milestone_order on enrollment → next row's idx
#     3. Student Skill ledger → updated if row has a skill
# ─────────────────────────────────────────────────────────────────────────────

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class PathProgressLog(Document):
    """
    Path Progress Log — one document per milestone completion event.

    validate:
        1. resolve_milestone_row       — find the child row in enrollment
        2. prevent_duplicate_entry     — one log per child row per enrollment
        3. enforce_sequential_progress — idx must match current_milestone_order

    on_update:
        4. mark_milestone_complete     — mark child row Completed, advance pointer
        5. create_or_upgrade_student_skill
    """

    def validate(self):
        self._resolve_milestone_row()
        self._check_milestone_points_completion()
        self._enforce_skill_assessment_verification()
        self._prevent_duplicate_entry()
        self._enforce_sequential_progress()

    def _check_milestone_points_completion(self):
        if not self._mrow or not self._enr_doc:
            return

        # Check if there are checklist points for this milestone
        points = [p for p in getattr(self._enr_doc, "milestone_points", []) if p.milestone_title == self._mrow.milestone_title]
        if points and not all(p.status == "Completed" for p in points):
            incomplete = [p.point_title for p in points if p.status != "Completed"]
            frappe.throw(
                f"Cannot complete milestone <b>{self._mrow.milestone_title}</b>. "
                f"The following checklist points are not completed yet:<br>"
                f"<ul>" + "".join(f"<li>{p}</li>" for p in incomplete) + "</ul>"
            )

    def _enforce_skill_assessment_verification(self):
        if not self._mrow or not self._enr_doc:
            return

        skill = getattr(self._mrow, "skill", None)
        if not skill:
            return

        # Check if the student has a verified Student Skill for this milestone's skill
        try:
            from job_search_ai.services.skill_gap.normalizer import normalize_skill
            norm_skill = normalize_skill(skill)
        except Exception:
            norm_skill = skill

        is_verified = frappe.db.exists(
            "Student Skill",
            {
                "student": self._enr_doc.student,
                "skill": norm_skill,
                "ai_verified": 1
            }
        )
        if not is_verified:
            frappe.throw(
                f"Cannot complete milestone <b>{self._mrow.milestone_title}</b> without passing the AI Skill Assessment for <b>{skill}</b>."
            )

    def on_update(self):
        self._mark_milestone_complete()
        self._create_or_upgrade_student_skill()

    # ══════════════════════════════════════════════════════════════════════════
    # 1. RESOLVE — load the milestone_progress child row from enrollment
    # ══════════════════════════════════════════════════════════════════════════

    def _resolve_milestone_row(self):
        """
        self.milestone holds the child row `name` from
        Student Path Enrollment → milestone_progress.

        We load the full enrollment doc, find the matching row by name,
        and cache it as self._mrow for the other methods to reuse.
        """
        if not self.enrollment or not self.milestone:
            self._mrow = None
            return

        enr_doc = frappe.get_doc("Student Path Enrollment", self.enrollment)

        target = None
        for row in enr_doc.milestone_progress:
            if row.name == self.milestone:
                target = row
                break

        if not target:
            frappe.throw(
                f"Milestone row <b>{self.milestone}</b> was not found in "
                f"enrollment <b>{self.enrollment}</b>.<br>"
                "Please select a valid milestone from the dropdown."
            )

        self._mrow     = target
        self._enr_doc  = enr_doc

        # Sync career_path from enrollment onto the log (in case it wasn't set)
        if not self.career_path:
            self.career_path = enr_doc.career_path

        # Write the idx as the `order` field so it is stored on the PPL record
        # and visible in list/report views as the sequence number.
        self.order = target.idx

    # ══════════════════════════════════════════════════════════════════════════
    # 2. PREVENT DUPLICATE — one log per child row per enrollment
    # ══════════════════════════════════════════════════════════════════════════

    def _prevent_duplicate_entry(self):
        if not self.enrollment or not self.milestone:
            return

        duplicate = frappe.db.exists(
            "Path Progress Log",
            {
                "enrollment": self.enrollment,
                "milestone" : self.milestone,
                "name"      : ["!=", self.name or "__new__"],
            },
        )
        if duplicate:
            row_idx = getattr(self._mrow, "idx", "?") if self._mrow else "?"
            frappe.throw(
                f"A progress log already exists for milestone "
                f"<b>#{row_idx} — {getattr(self._mrow, 'milestone_title', self.milestone)}</b> "
                f"in this enrollment."
            )

    # ══════════════════════════════════════════════════════════════════════════
    # 3. ENFORCE SEQUENTIAL PROGRESS
    # ══════════════════════════════════════════════════════════════════════════

    def _enforce_sequential_progress(self):
        if not self._mrow:
            return

        # Skip re-validation when editing a saved record that hasn't changed milestone
        if not self.is_new():
            original_milestone = frappe.db.get_value(
                "Path Progress Log", self.name, "milestone"
            )
            if original_milestone == self.milestone:
                return

        current_order = int(
            frappe.db.get_value(
                "Student Path Enrollment",
                self.enrollment,
                "current_milestone_order",
            ) or 1
        )

        selected_idx = int(self._mrow.idx)

        if selected_idx != current_order:
            frappe.throw(
                f"Cannot log milestone <b>#{selected_idx} — {self._mrow.milestone_title}</b>.<br>"
                f"The current expected milestone is <b>#{current_order}</b>.<br>"
                "Please complete milestones in sequence."
            )

    # ══════════════════════════════════════════════════════════════════════════
    # 4. MARK MILESTONE COMPLETE IN ENROLLMENT
    # ══════════════════════════════════════════════════════════════════════════

    def _mark_milestone_complete(self):
        """
        Re-loads the enrollment (on_update runs after save, so we need a fresh load),
        marks the target child row as Completed,
        and advances current_milestone_order to the next row's idx.
        """
        if not self.enrollment or not self.milestone:
            return

        enr_doc = frappe.get_doc("Student Path Enrollment", self.enrollment)

        # Find the target child row
        target = None
        for row in enr_doc.milestone_progress:
            if row.name == self.milestone:
                target = row
                break

        if not target:
            frappe.log_error(
                f"PPL {self.name}: could not find milestone row {self.milestone} "
                f"in enrollment {self.enrollment}",
                "PathProgressLog._mark_milestone_complete"
            )
            return

        # Mark this row complete
        target.status       = "Completed"
        target.completed_at = now_datetime()
        if self.score is not None:
            target.score = self.score
        if self.ai_feedback:
            target.ai_feedback = self.ai_feedback

        # Find and activate the next row
        completed_idx = target.idx
        rows_sorted   = sorted(enr_doc.milestone_progress, key=lambda r: r.idx)
        advanced      = False

        for row in rows_sorted:
            if row.idx <= completed_idx:
                continue
            if row.status not in ("Completed", "Skipped"):
                row.status                       = "In Progress"
                enr_doc.current_milestone_order  = row.idx
                advanced = True
                break

        if not advanced:
            # All milestones done
            enr_doc.status                   = "Completed"
            enr_doc.current_milestone_order  = completed_idx  # stay at last

        # Recompute completion percent
        mandatory = [r for r in enr_doc.milestone_progress if getattr(r, "is_mandatory", 1)]
        done      = sum(1 for r in mandatory if r.status in ("Completed", "Skipped"))
        enr_doc.completion_percent = round((done / len(mandatory)) * 100, 2) if mandatory else 0.0
        if enr_doc.completion_percent >= 100:
            enr_doc.status = "Completed"

        enr_doc.save(ignore_permissions=True)
        frappe.db.commit()

        next_idx = enr_doc.current_milestone_order
        total    = len(enr_doc.milestone_progress)
        frappe.msgprint(
            f"✅ Milestone <b>#{completed_idx} — {target.milestone_title}</b> completed!<br>"
            f"Progress: <b>{done}/{total}</b> ({enr_doc.completion_percent}%)<br>"
            + (f"Next milestone: <b>#{next_idx}</b>" if advanced else "🎉 All milestones completed!"),
            indicator="green",
            alert=True,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # 5. CREATE / UPGRADE STUDENT SKILL
    # ══════════════════════════════════════════════════════════════════════════

    def _create_or_upgrade_student_skill(self):
        """
        If the completed milestone_progress row has a `skill` field,
        add or upgrade it in the student's skill ledger.
        """
        if not self.enrollment or not self.milestone:
            return

        # Re-fetch the child row (on_update is post-save, _mrow may be stale)
        enr_doc = frappe.get_doc("Student Path Enrollment", self.enrollment)
        target  = next(
            (r for r in enr_doc.milestone_progress if r.name == self.milestone), None
        )
        if not target:
            return

        skill = getattr(target, "skill", None)
        if not skill:
            return

        # Canonicalize skill name
        try:
            from job_search_ai.services.skill_gap.normalizer import normalize_skill
            canonical_skill = normalize_skill(skill)
        except Exception:
            canonical_skill = skill

        skill_level = getattr(target, "required_skill_level", None) or "Beginner"
        student     = enr_doc.student

        from nexedu.path_finder.utils.milestone_engine import level_rank

        existing = frappe.db.get_value(
            "Student Skill",
            {"student": student, "skill": canonical_skill},
            ["name", "current_level"],
            as_dict=True,
        )

        if existing:
            doc = frappe.get_doc("Student Skill", existing.name)
            changed = False
            if not doc.ai_verified:
                doc.ai_verified = 1
                changed = True
            if level_rank(skill_level) > level_rank(doc.current_level):
                doc.current_level = skill_level
                changed = True
            
            if changed:
                doc.save(ignore_permissions=True)
                frappe.db.commit()
                frappe.msgprint(
                    f"Skill '<b>{canonical_skill}</b>' upgraded to <b>{doc.current_level}</b>.",
                    indicator="blue", alert=True,
                )
        else:
            frappe.get_doc({
                "doctype"      : "Student Skill",
                "student"      : student,
                "skill"        : canonical_skill,
                "current_level": skill_level,
                "self_declared": 0,
                "ai_verified"  : 1,
                "is_public"    : 1,
            }).insert(ignore_permissions=True)
            frappe.db.commit()
            frappe.msgprint(
                f"Skill '<b>{canonical_skill}</b>' added to Skill Ledger at <b>{skill_level}</b>.",
                indicator="blue", alert=True,
            )