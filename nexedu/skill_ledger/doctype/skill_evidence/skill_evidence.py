"""
DocType: Skill Evidence
Purpose: A single piece of evidence (course, project, cert, etc.) that backs
         a Student Skill entry. On verification, the parent ledger is updated.
         On creation, a mentor is auto-allocated to verify the skill.

Allocation Logic (fixed):
  Step 1 → Find mentors whose skill list includes the student's skill
  Step 2 → Among those skill-matched mentors, check if any is also the
            mentor of a session/booking the student is enrolled in
            → If YES  : assign that mentor  (method = "Session Mentor")
            → If NO   : pick randomly from top-10 skill-matched mentors
                        sorted by avg_rating  (method = "Auto Assigned")
"""

import frappe
import random
from frappe.model.document import Document
from frappe.utils import today, now_datetime


class SkillEvidence(Document):

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def before_save(self):
        if not self.evidence_date:
            self.evidence_date = today()

        if self.verification_status == "Verified" and not self.verified_by:
            user = frappe.session.user
            if user and user != "Guest":
                self.verified_by = user

    def after_insert(self):
        self._update_counts()
        self._create_ledger_event("Evidence Added")
        self._auto_allocate_mentor()

    def on_update(self):
        self.sync_status_to_parent()

        if not self.has_value_changed("verification_status"):
            return

        if self.verification_status == "Verified":
            self._update_last_demonstrated()
            self._auto_create_mentor_endorsement()

        ledger_name = frappe.db.get_value(
            "Student Skill Ledger",
            {
                "reference_doctype": "Skill Evidence",
                "reference_name": self.name
            },
            "name"
        )

        if ledger_name:
            frappe.db.set_value(
                "Student Skill Ledger",
                ledger_name,
                {
                    "status": self.verification_status,
                    "event_type": "Verification",
                    "event_time": now_datetime()
                }
            )

    def _auto_create_mentor_endorsement(self):
        if not self.student_skill:
            return

        endorsed_by = frappe.session.user
        if not endorsed_by or endorsed_by == "Guest":
            endorsed_by = self.verified_by or "Administrator"

        already_endorsed = frappe.db.exists(
            "Skill Endorsement",
            {
                "student_skill": self.student_skill,
                "endorsed_by": endorsed_by
            }
        )

        if not already_endorsed:
            level = frappe.db.get_value(
                "Student Skill",
                self.student_skill,
                "current_level"
            ) or "Beginner"

            endorsement_doc = frappe.get_doc({
                "doctype": "Skill Endorsement",
                "student_skill": self.student_skill,
                "endorsed_level": level,
                "endorsed_by": endorsed_by,
                "endorser_role": "Mentor",
                "endorsed_at": now_datetime(),
                "comment": self.remarks or "Auto-endorsed on evidence verification"
            })
            endorsement_doc.insert(ignore_permissions=True)

    # ------------------------------------------------------------------
    # Mentor Allocation — FIXED
    # ------------------------------------------------------------------

    def _auto_allocate_mentor(self):
        """
        Allocation flow (guaranteed to assign at least one mentor):

        1. Resolve student + skill from Student Skill doc
        2. Find ALL mentors who have this skill in their Mentor Skill
           child table  →  skill_matched_mentors
        3a. Among skill-matched mentors, check if any is also the mentor
            of a session/booking the student is enrolled in
               YES → assign that mentor  (method = "Session Mentor")
        3b. Fall back to random pick from top-10 skill-matched mentors
            sorted by avg_rating  (method = "Auto Assigned")
        4.  FINAL FALLBACK: if no mentor has this skill at all, pick any
            active mentor ordered by avg_rating
            (method = "Any Mentor" — auditable)
        5. Persist + notify
        """
        if not self.student_skill:
            return

        # ── Step 1: resolve student + skill ──────────────────────────
        student_skill_doc = frappe.db.get_value(
            "Student Skill",
            self.student_skill,
            ["student", "skill"],
            as_dict=True
        )

        if not student_skill_doc:
            frappe.log_error(
                f"Student Skill not found: {self.student_skill}",
                "Mentor Allocation Error"
            )
            return

        student = student_skill_doc.student
        skill   = student_skill_doc.skill

        if not student or not skill:
            frappe.log_error(
                f"Missing student or skill on Student Skill: {self.student_skill}",
                "Mentor Allocation Error"
            )
            return

        # ── Step 2: skill-matched mentors ─────────────────────────────
        skill_matched_mentors = self._get_skill_matched_mentors(skill)

        mentor, method = None, None

        if skill_matched_mentors:
            # ── Step 3a: prefer the student's existing session mentor ──
            mentor, method = self._get_session_mentor(student, skill_matched_mentors)

            # ── Step 3b: random top-10 skill-matched mentor ────────────
            if not mentor:
                mentor, method = self._get_random_top_mentor(skill, skill_matched_mentors)
        else:
            frappe.log_error(
                f"No skill-matched mentor found for skill '{skill}'.\n"
                f"Evidence: {self.name} | Student: {student}\n"
                f"Falling back to any available mentor.",
                "Mentor Allocation – No Skill Match"
            )

        # ── Step 4: FINAL FALLBACK — any active mentor ────────────────
        if not mentor:
            mentor, method = self._get_any_mentor_fallback()

        # ── Step 5: persist + notify ───────────────────────────────────
        if mentor:
            self.db_set({
                "allocated_mentor":  mentor,
                "allocation_method": method,
                "allocation_status": "Allocated"
            })

            self._notify_mentor(mentor, student, skill)

            frappe.publish_realtime(
                event="skill_evidence_mentor_allocated",
                message={
                    "evidence": self.name,
                    "mentor":   mentor,
                    "method":   method
                },
                user=frappe.session.user
            )
        else:
            frappe.log_error(
                f"Mentor allocation completely failed — no active mentors exist.\n"
                f"Evidence : {self.name}\n"
                f"Student  : {student}\n"
                f"Skill    : {skill}",
                "Mentor Allocation Failed"
            )

    # ------------------------------------------------------------------
    # Step 2 helper — all mentors with this skill
    # ------------------------------------------------------------------

    def _get_skill_matched_mentors(self, skill: str) -> list:

        rows = frappe.db.sql("""
            SELECT
                m.email_id AS mentor,
                m.name AS mentor_name,
                COALESCE(m.avg_rating, 0) AS rating
            FROM
                `tabStudent Skill Table` sst
            INNER JOIN
                `tabMentor` m
                    ON m.name = sst.parent
            WHERE
                sst.skill = %(skill)s
                AND sst.parenttype = 'Mentor'
                AND m.email_id IS NOT NULL
            ORDER BY
                rating DESC
        """, {"skill": skill}, as_dict=True)

        return rows

    # ------------------------------------------------------------------
    # Step 3a helper — session mentor whose skill matches
    # ------------------------------------------------------------------

    def _get_session_mentor(self, student: str, skill_matched_mentors: list):
        """
        Checks if the student has a Mentor Session Booking whose mentor
        is in skill_matched_mentors.

        Returns (mentor_name, "Session Mentor") or (None, None).

        Uses msb.mentor directly (Link → Mentor, whose name == email_id
        because Mentor is autonamed by field:email_id).
        """
        if not skill_matched_mentors:
            return None, None

        # Build a set of skill-matched mentor names (= email_id) for O(1) lookup
        matched_mentors = {row["mentor"] for row in skill_matched_mentors}

        # Fetch all bookings for this student using the direct mentor field
        # (most recent first)
        bookings = frappe.db.sql("""
            SELECT
                msb.mentor AS mentor
            FROM
                `tabMentor Session Booking` msb
            WHERE
                msb.student  = %(student)s
                AND msb.mentor IS NOT NULL
            ORDER BY
                msb.creation DESC
        """, {"student": student}, as_dict=True)

        for row in bookings:
            mentor = row.get("mentor")
            # Only assign if this booking's mentor also has the required skill
            if mentor and mentor in matched_mentors:
                return mentor, "Session Mentor"

        return None, None

    # ------------------------------------------------------------------
    # Step 3b helper — random pick from top-10 skill-matched mentors
    # ------------------------------------------------------------------

    def _get_random_top_mentor(self, skill: str, skill_matched_mentors: list):
        """
        Picks randomly from the top-10 skill-matched mentors
        (already sorted by avg_rating DESC from _get_skill_matched_mentors).

        Returns (mentor_email, "Auto Assigned") or (None, None).
        """
        if not skill_matched_mentors:
            return None, None

        top_10 = skill_matched_mentors[:10]
        chosen = random.choice(top_10)
        return chosen.get("mentor"), "Auto Assigned"

    # ------------------------------------------------------------------
    # Step 4 helper — ANY active mentor (final fallback)
    # ------------------------------------------------------------------

    def _get_any_mentor_fallback(self):
        """
        Last-resort fallback: picks randomly from up to top-10 active
        mentors ordered by avg_rating DESC.

        Used when no mentor has the requested skill in their profile.
        Returns (mentor_name, "Any Mentor") or (None, None).
        """
        rows = frappe.db.sql("""
            SELECT
                m.name    AS mentor,
                COALESCE(m.avg_rating, 0) AS rating
            FROM
                `tabMentor` m
            WHERE
                m.email_id IS NOT NULL
                AND (m.is_active = 1 OR m.is_active IS NULL)
            ORDER BY
                rating DESC
            LIMIT 10
        """, as_dict=True)

        if not rows:
            return None, None

        chosen = random.choice(rows)
        return chosen.get("mentor"), "Any Mentor"

    # ------------------------------------------------------------------
    # Notification helper
    # ------------------------------------------------------------------

    def _notify_mentor(self, mentor: str, student: str, skill: str):

            mentor_full_name = (
                frappe.db.get_value("User", mentor, "full_name")
                or mentor
            )

            student_doc = frappe.db.get_value(
                "Student",
                student,
                ["first_name", "last_name"],
                as_dict=True
            )

            student_full_name = student
            if student_doc:
                student_full_name = (
                    f"{student_doc.first_name or ''} "
                    f"{student_doc.last_name or ''}"
                ).strip()

            skill_label = (
                frappe.db.get_value("Skill", skill, "skill_name")
                or skill
            )

            evidence_url = (
                frappe.utils.get_url()
                + f"/app/skill-evidence/{self.name}"
            )

            # ---------------------------------------------------------
            # EMAIL
            # ---------------------------------------------------------
            try:
                frappe.sendmail(
                    recipients=[mentor],
                    subject=f"[Action Required] Verify Skill Evidence – {skill_label}",
                    message=f"""
                        <p>Dear {mentor_full_name},</p>
                        <p>You have been allocated to verify a skill evidence.</p>
                        <p>
                            <b>Student:</b> {student_full_name}<br>
                            <b>Skill:</b> {skill_label}<br>
                            <b>Evidence:</b> {self.name}
                        </p>
                        <p><a href="{evidence_url}">Review Evidence</a></p>
                        <br>
                        <p>Regards,<br>Skill Ledger System</p>
                    """,
                    now=False  # Queue for background delivery; avoids SMTP errors crashing the request
                )
            except Exception:
                frappe.log_error(
                    title="EMAIL ERROR",
                    message=frappe.get_traceback()
                )

            # ---------------------------------------------------------
            # NOTIFICATION LOG  ← fixed section
            # ---------------------------------------------------------
            try:
                # ── 1. Resolve the User record by email ──────────────
                user = frappe.db.get_value(
                    "User",
                    {"email": mentor},   # filter by email field
                    "name"               # returns the `name` (= login email usually)
                )

                # Fallback: maybe mentor stores the User.name directly
                if not user:
                    user = frappe.db.get_value("User", mentor, "name")

                if not user:
                    frappe.log_error(
                        f"No User record found for mentor: {mentor}",
                        "NOTIFICATION ERROR"
                    )
                    return

                # ── 2. Resolve from_user safely ──────────────────────
                from_user = frappe.session.user
                if not from_user or from_user == "Guest":
                    from_user = "Administrator"

                # Confirm from_user exists in tabUser
                if not frappe.db.exists("User", from_user):
                    from_user = "Administrator"

                # ── 3. Build and insert Notification Log ─────────────
                notification = frappe.get_doc({
                    "doctype":       "Notification Log",
                    "subject":       f"Skill Verification Assigned: {skill_label}",
                    "for_user":      user,           # ← must be User.name
                    "from_user":     from_user,      # ← must be User.name
                    "type":          "Alert",
                    "document_type": "Skill Evidence",
                    "document_name": self.name,
                    "email_content": (
                        f"Student <b>{student_full_name}</b> submitted evidence "
                        f"for <b>{skill_label}</b>. Please review and verify."
                    ),
                    "read":          0               # ← explicitly mark unread
                })

                notification.insert(ignore_permissions=True)

                # ── 4. Commit so the record is persisted ─────────────
                frappe.db.commit()

                # ── 5. Push real-time bell refresh ───────────────────
                frappe.publish_realtime(
                    event="notification",
                    message={"user": user},
                    user=user               # ← send to the mentor's user, not session user
                )

            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    "NOTIFICATION ERROR"
                )
    # ------------------------------------------------------------------
    # Existing helpers (unchanged)
    # ------------------------------------------------------------------

    def _update_counts(self):
        if not self.student_skill:
            return

        evidence_count = frappe.db.count(
            "Skill Evidence",
            {"student_skill": self.student_skill}
        )
        endorsement_count = frappe.db.count(
            "Skill Endorsement",
            {"student_skill": self.student_skill}
        )
        frappe.db.set_value(
            "Student Skill",
            self.student_skill,
            {
                "evidence_count":    evidence_count,
                "endorsement_count": endorsement_count
            }
        )

    def sync_status_to_parent(self):
        """
        Derives and syncs the correct Student Skill status from ALL evidences.
        Never blindly copies a single evidence's status — considers all evidence rows.
        """
        if not self.student_skill:
            return

        # Derive status from ALL evidence rows (same logic as _derive_and_set_status)
        rows = frappe.get_all(
            "Skill Evidence",
            filters={"student_skill": self.student_skill},
            fields=["verification_status"],
            ignore_ifnull=True,
        )
        if not rows:
            new_status = "Pending"
        else:
            statuses = {r["verification_status"] for r in rows}
            if "Verified" in statuses:
                new_status = "Verified"
            elif statuses == {"Rejected"}:
                new_status = "Rejected"
            else:
                new_status = "Pending"

        frappe.db.set_value(
            "Student Skill",
            self.student_skill,
            "status",
            new_status
        )

        ledger = frappe.db.get_value(
            "Student Skill Ledger",
            {"student_skill": self.student_skill},
            "name"
        )
        if ledger:
            frappe.db.set_value(
                "Student Skill Ledger",
                ledger,
                "status",
                new_status
            )

    def _refresh_parent(self):
        if self.student_skill:
            parent = frappe.get_doc("Student Skill", self.student_skill)
            parent.refresh_counts()

    def _update_last_demonstrated(self):
        frappe.db.set_value(
            "Student Skill",
            self.student_skill,
            "last_demonstrated",
            self.evidence_date,
        )

    def _create_ledger_event(self, event_type: str):
        if not self.student_skill:
            return
        rows = frappe.db.sql("""
            SELECT student, skill, current_level, evidence_count, endorsement_count
            FROM `tabStudent Skill`
            WHERE name = %s
        """, (self.student_skill,), as_dict=True)

        if not rows:
            return

        ss = rows[0]
        frappe.get_doc({
            "doctype":           "Student Skill Ledger",
            "student":           ss.student,
            "student_skill":     self.student_skill,
            "skill":             ss.skill,
            "skill_level":       ss.current_level,
            "event_type":        event_type,
            "evidence_count":    ss.evidence_count,
            "endorsement_count": ss.endorsement_count,
            "event_time":        now_datetime(),
            "status":            self.verification_status,
            "reference_doctype": "Skill Evidence",
            "reference_name":    self.name,
            "comment":           self.description or "",
        }).insert(ignore_permissions=True)


# ------------------------------------------------------------------
# Whitelisted API
# ------------------------------------------------------------------

@frappe.whitelist(allow_guest=False)
def add_evidence(
    student_skill: str,
    evidence_type: str,
    evidence_date: str,
    description: str = "",
    reference_doctype: str = "",
    reference_name: str = "",
    document_url: str = "",
) -> str:

    # ----------------------------------------------------------
    # PERMISSION CHECK
    # Controlled by Role Permission Manager
    # ----------------------------------------------------------
    session_user = frappe.session.user

    if not frappe.has_permission(
        "Skill Evidence",
        ptype="create",
        user=session_user
    ):
        frappe.throw(
            "You do not have permission to create Skill Evidence.",
            frappe.PermissionError
        )

    doc = frappe.get_doc({
        "doctype": "Skill Evidence",
        "student_skill": student_skill,
        "evidence_type": evidence_type,
        "evidence_date": evidence_date,
        "description": description,
        "reference_doctype": reference_doctype,
        "reference_name": reference_name,
        "document_url": document_url,
        "verification_status": "Pending",
    })

    # Respects Role Permission Manager
    doc.insert()

    try:
        frappe.db.commit()
    except Exception:
        # Log SMTP / after-commit hook failures but don't fail the API —
        # the evidence record is already saved.
        frappe.log_error(
            title="add_evidence commit error",
            message=frappe.get_traceback()
        )

    return doc.name

@frappe.whitelist()
def verify_evidence(evidence_name: str, status: str, remarks: str = ""):
    _check_verifier_role()

    doc = frappe.get_doc("Skill Evidence", evidence_name)
    doc.verification_status = status
    doc.verified_by         = frappe.session.user
    doc.remarks             = remarks
    doc.save(ignore_permissions=True)

    return {
        "status":  "success",
        "message": f"Evidence {status.lower()} successfully",
        "evidence": {
            "name":                doc.name,
            "verification_status": doc.verification_status,
            "verified_by":         doc.verified_by
        }
    }


@frappe.whitelist()
def get_evidence_for_skill(student_skill: str) -> list:
    return frappe.get_all(
        "Skill Evidence",
        filters={"student_skill": student_skill},
        fields=[
            "name", "evidence_type", "evidence_date", "verification_status",
            "verified_by", "allocated_mentor", "allocation_method",
            "allocation_status", "description", "document_url",
            "reference_doctype", "reference_name",
        ],
        order_by="evidence_date desc",
    )


@frappe.whitelist()
def reallocate_mentor(evidence_name: str) -> dict:
    _check_verifier_role()

    doc = frappe.get_doc("Skill Evidence", evidence_name)

    frappe.db.set_value("Skill Evidence", evidence_name, {
        "allocated_mentor":  None,
        "allocation_method": None,
        "allocation_status": "Not Allocated"
    })

    doc._auto_allocate_mentor()

    return {
        "allocated_mentor":  frappe.db.get_value(
            "Skill Evidence", evidence_name, "allocated_mentor"
        ),
        "allocation_method": frappe.db.get_value(
            "Skill Evidence", evidence_name, "allocation_method"
        ),
    }


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _check_verifier_role():
    roles = frappe.get_roles(frappe.session.user)
    if "Skill Verifier" not in roles and "System Manager" not in roles:
        frappe.throw(
            "You do not have permission to verify evidence. "
            "Required role: Skill Verifier",
            frappe.PermissionError,
        )
@frappe.whitelist(allow_guest=False)
def get_mentor_pending_verifications(
    mentor: str = None,
    limit: int = None
):
    """
    Returns pending Skill Evidence records allocated to mentor
    along with total pending count.

    Permission is controlled entirely by Role Permission Manager.
    """

    # ----------------------------------------------------------
    # PERMISSION CHECK
    # ----------------------------------------------------------
    session_user = frappe.session.user

    if not frappe.has_permission(
        "Skill Evidence",
        ptype="read",
        user=session_user
    ):
        frappe.throw(
            "You do not have permission to access Skill Evidence.",
            frappe.PermissionError
        )

    mentor = mentor or session_user

    filters = {
        "allocated_mentor": mentor,
        "verification_status": "Pending"
    }

    # -----------------------------------------
    # Total Pending Count
    # -----------------------------------------
    total_pending_count = frappe.db.count(
        "Skill Evidence",
        filters=filters
    )

    # -----------------------------------------
    # Get Records
    # Uses permissions automatically
    # -----------------------------------------
    evidence_list = frappe.get_list(
        "Skill Evidence",
        filters=filters,
        fields=[
            "name",
            "student_skill",
            "evidence_type",
            "evidence_date",
            "allocation_method",
            "allocation_status",
            "description",
            "document_url",
            "reference_doctype",
            "reference_name",
            "creation"
        ],
        order_by="evidence_date asc",
        limit_page_length=int(limit) if limit else 0
    )

    results = []

    for ev in evidence_list:

        student_skill = frappe.db.get_value(
            "Student Skill",
            ev.student_skill,
            ["student", "skill"],
            as_dict=True
        )

        student_name = ""
        skill_name = ""

        if student_skill:

            student_doc = frappe.db.get_value(
                "Student",
                student_skill.student,
                ["first_name", "last_name"],
                as_dict=True
            )

            if student_doc:
                student_name = (
                    f"{student_doc.first_name or ''} "
                    f"{student_doc.last_name or ''}"
                ).strip()

            skill_name = (
                frappe.db.get_value(
                    "Skill",
                    student_skill.skill,
                    "skill_name"
                )
                or student_skill.skill
            )

        results.append({
            "evidence_name": ev.name,
            "student_skill": ev.student_skill,
            "student_name": student_name,
            "skill": skill_name,
            "evidence_type": ev.evidence_type,
            "evidence_date": ev.evidence_date,
            "allocation_method": ev.allocation_method,
            "allocation_status": ev.allocation_status,
            "description": ev.description,
            "document_url": ev.document_url,
            "reference_doctype": ev.reference_doctype,
            "reference_name": ev.reference_name,
            "creation": ev.creation
        })

    return {
        "total_pending_count": total_pending_count,
        "records": results
    }
    
@frappe.whitelist(allow_guest=False)
def verify_and_endorse_skill(
    evidence_name,
    remarks="",
    endorsed_level="",
    endorser_company="",
    comment=""
):
    """
    Mentor verifies a skill evidence and auto-creates a Mentor endorsement.

    Flow:
    1. Mark the Skill Evidence as 'Verified'.
    2. Auto-create a Skill Endorsement with endorser_role='Mentor'
       (if the mentor hasn't already endorsed this skill).
    3. Update Student Skill status, evidence_count, endorsement_count.
    4. Update the Skill Ledger entry.

    Note: endorser_role is always forced to 'Mentor' — this function
    is exclusively for mentor verification.
    """
    # endorser_role is always Mentor in this flow — not configurable
    endorser_role = "Mentor"

    # ----------------------------------------------------------
    # PERMISSION CHECK
    # Respects Role Permission Manager configuration
    # ----------------------------------------------------------
    session_user = frappe.session.user

    if not frappe.has_permission(
        "Skill Evidence",
        ptype="write",
        user=session_user
    ):
        frappe.throw(
            "You do not have permission to verify skill evidence.",
            frappe.PermissionError
        )

    if not frappe.has_permission(
        "Skill Endorsement",
        ptype="create",
        user=session_user
    ):
        frappe.throw(
            "You do not have permission to create skill endorsements.",
            frappe.PermissionError
        )

    # ── Check Evidence Exists ──────────────────────────────────────────────
    if not frappe.db.exists("Skill Evidence", evidence_name):
        frappe.throw("Skill Evidence not found")

    # ── Get Evidence Doc ───────────────────────────────────────────────────
    evidence_doc = frappe.get_doc("Skill Evidence", evidence_name)

    if evidence_doc.verification_status == "Verified":
        return {
            "status": "warning",
            "message": "Skill evidence already verified"
        }

    # ── Update Skill Evidence ──────────────────────────────────────────────
    evidence_doc.verification_status = "Verified"
    evidence_doc.verified_by = session_user
    evidence_doc.remarks = remarks

    evidence_doc.save()

    # ── Create Skill Endorsement ───────────────────────────────────────────
    endorsement_name = None

    already_endorsed = frappe.db.exists(
        "Skill Endorsement",
        {
            "student_skill": evidence_doc.student_skill,
            "endorsed_by": session_user
        }
    )

    if not already_endorsed:

        level = endorsed_level or frappe.db.get_value(
            "Student Skill",
            evidence_doc.student_skill,
            "current_level"
        ) or "Beginner"

        endorsement_doc = frappe.get_doc({
            "doctype": "Skill Endorsement",
            "student_skill": evidence_doc.student_skill,
            "endorsed_level": level,
            "endorsed_by": session_user,
            "endorser_role": endorser_role,
            "endorser_company": endorser_company,
            "endorsed_at": now_datetime(),
            "comment": comment or remarks
        })

        endorsement_doc.insert()

        endorsement_name = endorsement_doc.name

    # Remaining logic unchanged...
        # SkillEndorsement.after_insert() will:
        # → call _update_counts() → updates evidence_count + endorsement_count
        # → call _create_ledger_event() → creates ledger entry

    # ── Update Student Skill counts & status ──────────────────────────────
    # Use verified_evidence_count for evidence_count field
    # (consistent with before_save._recalculate_counts which only counts Verified)
    verified_evidence_count = 0
    endorsement_count = 0

    if evidence_doc.student_skill:

        verified_evidence_count = frappe.db.count(
            "Skill Evidence",
            {
                "student_skill": evidence_doc.student_skill,
                "verification_status": "Verified"
            }
        )

        endorsement_count = frappe.db.count(
            "Skill Endorsement",
            {"student_skill": evidence_doc.student_skill}
        )

        frappe.db.set_value(
            "Student Skill",
            evidence_doc.student_skill,
            {
                "status": "Verified",
                "evidence_count": verified_evidence_count,   # only Verified evidences
                "endorsement_count": endorsement_count,
                "last_demonstrated": evidence_doc.evidence_date
            }
        )

    # ── Update Skill Ledger for this Evidence ──────────────────────────────
    ledger_name = frappe.db.get_value(
        "Student Skill Ledger",
        {
            "reference_doctype": "Skill Evidence",
            "reference_name": evidence_doc.name
        },
        "name"
    )

    if ledger_name:
        frappe.db.set_value(
            "Student Skill Ledger",
            ledger_name,
            {
                "status": "Verified",
                "event_type": "Verification",
                "event_time": now_datetime()
            }
        )

    frappe.db.commit()



    # ── Response ───────────────────────────────────────────────────────────
    return {
        "status": "success",
        "message": "Skill evidence verified and endorsed successfully",
        "data": {
            "evidence_name": evidence_doc.name,
            "student_skill": evidence_doc.student_skill,
            "verification_status": evidence_doc.verification_status,
            "verified_by": evidence_doc.verified_by,
            "remarks": evidence_doc.remarks,
            "endorsement_created": endorsement_name or "Already existed",
            "counts": {
                "evidence_count": verified_evidence_count if evidence_doc.student_skill else 0,
                "endorsement_count": endorsement_count if evidence_doc.student_skill else 0
            }
        }
    }
    
@frappe.whitelist(allow_guest=False)
def reject_skill_evidence(evidence_name, remarks=""):
    """
    Mentor rejects student skill evidence
    """

    # ----------------------------------------------------------
    # PERMISSION CHECK
    # Respects Role Permission Manager configuration
    # ----------------------------------------------------------
    session_user = frappe.session.user

    if not frappe.has_permission(
        "Skill Evidence",
        ptype="write",
        user=session_user
    ):
        frappe.throw(
            "You do not have permission to reject skill evidence.",
            frappe.PermissionError
        )

    # -------------------------------
    # Check Evidence Exists
    # -------------------------------
    if not frappe.db.exists("Skill Evidence", evidence_name):
        frappe.throw("Skill Evidence not found")

    # -------------------------------
    # Get Evidence Doc
    # -------------------------------
    evidence_doc = frappe.get_doc(
        "Skill Evidence",
        evidence_name
    )

    # Prevent duplicate rejection
    if evidence_doc.verification_status == "Rejected":
        return {
            "status": "warning",
            "message": "Skill evidence already rejected"
        }

    # -------------------------------
    # Update Skill Evidence
    # -------------------------------
    evidence_doc.verification_status = "Rejected"
    evidence_doc.verified_by = session_user
    evidence_doc.remarks = remarks

    # Respects Role Permission Manager
    evidence_doc.save()

    # -------------------------------
    # Update Student Skill Counts
    # -------------------------------
    if evidence_doc.student_skill:

        evidence_count = frappe.db.count(
            "Skill Evidence",
            {
                "student_skill": evidence_doc.student_skill
            }
        )

        # Count actual Skill Endorsements, not Skill Evidence
        endorsement_count = frappe.db.count(
            "Skill Endorsement",
            {
                "student_skill": evidence_doc.student_skill
            }
        )

        # Only mark skill as Rejected if there are no verified evidences
        verified_count = frappe.db.count(
            "Skill Evidence",
            {
                "student_skill": evidence_doc.student_skill,
                "verification_status": "Verified"
            }
        )

        skill_status = "Verified" if verified_count > 0 else "Rejected"

        frappe.db.set_value(
            "Student Skill",
            evidence_doc.student_skill,
            {
                "status": skill_status,
                "evidence_count": evidence_count,
                "endorsement_count": endorsement_count
            }
        )

    # -------------------------------
    # Update Skill Ledger
    # -------------------------------
    ledger_name = frappe.db.get_value(
        "Student Skill Ledger",
        {
            "reference_doctype": "Skill Evidence",
            "reference_name": evidence_doc.name
        },
        "name"
    )

    if ledger_name:
        frappe.db.set_value(
            "Student Skill Ledger",
            ledger_name,
            {
                "status": "Rejected",
                "event_type": "Verification",
                "event_time": now_datetime()
            }
        )

    frappe.db.commit()

    # -------------------------------
    # Response
    # -------------------------------
    return {
        "status": "success",
        "message": "Skill evidence rejected successfully",
        "data": {
            "evidence_name": evidence_doc.name,
            "student_skill": evidence_doc.student_skill,
            "verification_status": evidence_doc.verification_status,
            "verified_by": evidence_doc.verified_by,
            "remarks": evidence_doc.remarks
        }
    }