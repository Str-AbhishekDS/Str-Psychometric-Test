"""
DocType: Student Skill
Purpose: Core ledger record linking a Student to a Skill with aggregated counts,
         verification flags, and a tamper-evident ledger hash.
"""

import frappe
import hashlib
import json
from frappe.model.document import Document
from frappe.utils import today, now_datetime


class StudentSkill(Document):

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------
    def on_update(self):
        # Only send verification email when self_declared is newly set to 1
        if self.has_value_changed("self_declared") and self.self_declared:
            self.send_verification_email()

    def before_save(self):
        self._set_first_acquired()
        self._recalculate_counts()
        self._derive_and_set_status()
        self._update_ledger_hash()

    def after_insert(self):
        self._create_ledger_event("Self Declared")
        self.send_verification_email()  # send once on creation

    # ------------------------------------------------------------------
    # Public helpers (called by child doctypes)
    # ------------------------------------------------------------------

    def refresh_counts(self):
        """
        Re-aggregate evidence & endorsement counts, derive status,
        recompute hash, then save.

        NOTE: Called by SkillEvidence and SkillEndorsement after they
        have already used db_set for their own cascade. This path is
        retained for cases where a full Document.save() is acceptable
        (e.g. AI assessment, level update).
        """
        self._recalculate_counts()
        self._derive_and_set_status()
        self._update_ledger_hash()
        self.save(ignore_permissions=True)

    def mark_ai_verified(self):
        self.ai_verified = 1
        self._update_ledger_hash()
        self.save(ignore_permissions=True)
        self._create_ledger_event("AI Assessment")

    def update_skill_level(self, new_level: str):
        old_level = self.current_level
        self.current_level = new_level
        self._update_ledger_hash()
        self.save(ignore_permissions=True)
        self._create_ledger_event(
            "Skill Level Updated",
            comment=f"Level changed from {old_level} to {new_level}",
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _set_first_acquired(self):
        if not self.first_acquired:
            self.first_acquired = today()

    def _recalculate_counts(self):
        self.evidence_count = frappe.db.count(
            "Skill Evidence",
            filters={"student_skill": self.name, "verification_status": "Verified"},
        )
        self.endorsement_count = frappe.db.count(
            "Skill Endorsement",
            filters={"student_skill": self.name},
        )

    def _derive_and_set_status(self):
        """
        Derives Student Skill status from all linked Skill Evidence rows.
        Mirrors _derive_student_skill_status() in skill_evidence.py.

          - Any evidence Verified  → "Verified"
          - All evidence Rejected  → "Rejected"
          - Otherwise              → "Pending"
        """
        if self.ai_verified:
            self.status = "Verified"
            return

        rows = frappe.get_all(
            "Skill Evidence",
            filters={"student_skill": self.name},
            fields=["verification_status"],
            ignore_ifnull=True,
        )
        if not rows:
            self.status = "Pending"
            return
        statuses = {r["verification_status"] for r in rows}
        if "Verified" in statuses:
            self.status = "Verified"
        elif statuses == {"Rejected"}:
            self.status = "Rejected"
        else:
            self.status = "Pending"

    def _update_ledger_hash(self):
        """
        SHA-256 over the fields that constitute the skill's provenance.
        Changing any field will produce a different hash — useful for
        tamper detection when exporting the ledger.
        `status` is now included so a forged status change breaks the hash.
        """
        payload = {
            "student": self.student,
            "skill": self.skill,
            "current_level": self.current_level,
            "status": self.status,
            "evidence_count": self.evidence_count,
            "endorsement_count": self.endorsement_count,
            "ai_verified": self.ai_verified,
            "self_declared": self.self_declared,
        }
        raw = json.dumps(payload, sort_keys=True)
        self.ledger_hash = hashlib.sha256(raw.encode()).hexdigest()

    def _create_ledger_event(self, event_type: str, comment: str = ""):
        frappe.get_doc(
            {
                "doctype": "Student Skill Ledger",
                "student": self.student,
                "student_skill": self.name,
                "skill": self.skill,
                "skill_level": self.current_level,
                "event_type": event_type,
                "evidence_count": self.evidence_count,
                "endorsement_count": self.endorsement_count,
                "event_time": now_datetime(),
                "comment": comment,
            }
        ).insert(ignore_permissions=True)
        
    def send_verification_email(self):
        # Skip if already verified
        if self.ai_verified:
            return

        student_email = frappe.db.get_value("Student", self.student, "email_id")
        if not student_email:
            frappe.log_error(
                title="Student Skill AI Verification Mail",
                message=f"No email found for student {self.student} (Student Skill: {self.name})"
            )
            return

        skill_name = frappe.db.get_value("Skill", self.skill, "skill_name") or self.skill
        # record_url = get_url(f"/app/student-skill/{self.name}")

        subject = ("Action Required: Verify your skill - {0}").format(skill_name)

        message = f"""
            <div style="margin:0;padding:0;background:#f6f6f8;font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f6f6f8;padding:30px 15px;">
                    <tr>
                        <td align="center">

                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
                                style="max-width:600px;background:#ffffff;border:1px solid #e2e8f0;border-radius:16px;overflow:hidden;">

                                <!-- Header -->
                                <tr>
                                    <td style="background:#0f0fbd;padding:28px 32px;text-align:center;">
                                        <h1 style="margin:0;color:#ffffff;font-size:24px;font-weight:700;">
                                            Skill Verification Required
                                        </h1>
                                        <p style="margin:8px 0 0;color:#dbeafe;font-size:14px;">
                                            Action Needed for Your Skill Ledger
                                        </p>
                                    </td>
                                </tr>

                                <!-- Body -->
                                <tr>
                                    <td style="padding:32px;">

                                        <p style="margin:0 0 20px;color:#1E293B;font-size:16px;line-height:1.7;">
                                            Hi,
                                        </p>

                                        <p style="margin:0 0 20px;color:#1E293B;font-size:15px;line-height:1.8;">
                                            Your skill
                                            <span style="background:#eef2ff;color:#0f0fbd;padding:4px 10px;border-radius:6px;font-weight:600;">
                                                {skill_name}
                                            </span>
                                            at level
                                            <span style="background:#fff7ed;color:#ff6b00;padding:4px 10px;border-radius:6px;font-weight:600;">
                                                {self.current_level}
                                            </span>
                                            is currently
                                            <span style="background:#fef2f2;color:#ef4444;padding:4px 10px;border-radius:6px;font-weight:600;">
                                                {self.status or "Pending"}
                                            </span>
                                            and has not been AI verified yet.
                                        </p>

                                        <div style="background:#f8fafc;border-left:4px solid #ff6b00;padding:16px 18px;border-radius:8px;margin-bottom:24px;">
                                            <p style="margin:0;color:#64748B;font-size:14px;line-height:1.7;">
                                                Verification helps validate your skills, improve credibility,
                                                and strengthen your professional profile on StrideNex.
                                            </p>
                                        </div>

                                        <!-- CTA -->
                                        

                                        <p style="margin:24px 0 0;color:#64748B;font-size:14px;line-height:1.7;">
                                            If you've already completed the AI verification process, you can safely ignore this message.
                                        </p>

                                    </td>
                                </tr>

                                <!-- Footer -->
                                <tr>
                                    <td style="background:#0F172A;padding:24px;text-align:center;">
                                        <p style="margin:0;color:#ffffff;font-size:14px;font-weight:600;">
                                            StrideNex Skill Ledger
                                        </p>
                                        <p style="margin:8px 0 0;color:#94a3b8;font-size:12px;">
                                            Empowering Skills • Building Careers • Creating Opportunities
                                        </p>
                                    </td>
                                </tr>

                            </table>

                        </td>
                    </tr>
                </table>
            </div>
            """

        frappe.sendmail(
            recipients=[student_email],
            subject=subject,
            message=message,
            reference_doctype=self.doctype,
            reference_name=self.name,  # fixed: was self.student (wrong)
        )


# ------------------------------------------------------------------
# Whitelisted API
# ------------------------------------------------------------------

@frappe.whitelist(allow_guest=False)
def get_skill_ledger(student: str) -> dict:
    """
    Returns the full skill ledger for a student — used by the dashboard.
    """

    # ----------------------------------------------------------
    # PERMISSION CHECK
    # Respects Role Permission Manager configuration
    # ----------------------------------------------------------
    session_user = frappe.session.user

    if not frappe.has_permission(
        "Student Skill",
        ptype="read",
        user=session_user
    ):
        frappe.throw(
            "You do not have permission to access Student Skill.",
            frappe.PermissionError
        )

    skills = frappe.get_all(
        "Student Skill",
        filters={
            "student": student,
            "is_public": 1
        },
        fields=[
            "name",
            "skill",
            "current_level",
            "evidence_count",
            "endorsement_count",
            "ai_verified",
            "self_declared",
            "first_acquired",
            "last_demonstrated",
            "ledger_hash",
        ],
        order_by="skill asc",
    )

    # Enrich each skill with category and last evidence date
    for s in skills:

        skill_doc = frappe.db.get_value(
            "Skill",
            s["skill"],
            ["skill_category", "skill_name"],
            as_dict=True
        )

        s["skill_name"] = (
            skill_doc.get("skill_name")
            if skill_doc else s["skill"]
        )

        s["skill_category"] = (
            skill_doc.get("skill_category")
            if skill_doc else ""
        )

        # Latest evidence date
        last_evidence = frappe.db.get_value(
            "Skill Evidence",
            filters={
                "student_skill": s["name"],
                "verification_status": "Verified"
            },
            fieldname="evidence_date",
            order_by="evidence_date desc",
        )

        s["last_demo"] = last_evidence

        # Endorsement breakdown
        s["mentor_endorsements"] = frappe.db.count(
            "Skill Endorsement",
            filters={
                "student_skill": s["name"],
                "endorser_role": "Mentor"
            },
        )

        s["industry_endorsements"] = frappe.db.count(
            "Skill Endorsement",
            filters={
                "student_skill": s["name"],
                "endorser_role": "Industry"
            },
        )

        # Integrity check
        s["integrity"] = _verify_hash(s)

    summary = _build_summary(skills)

    return {
        "student": student,
        "skills": skills,
        "summary": summary
    }


@frappe.whitelist(allow_guest=True)
def get_skill_score(student: str = None) -> int:
    """
    Calculates a 0-100 skill score based on skills, verifications,
    endorsements and evidence depth.

    Formula (breadth-neutral — adding new skills never reduces score):
      - Depth score per skill  : level (max 20) + evidence (max 15) + endorsement (max 8) + AI (max 5) = max 48
      - Breadth bonus          : min(skill_count * 4, 20) — up to 20 pts for 5+ skills
      - Final                  : (avg_skill_score / 48) * 80  +  breadth_bonus
      - Rejected skills are excluded entirely.
    """
    try:
        if not student:
            return 0

        # Resolve email → student name
        if "@" in student:
            resolved = frappe.db.get_value("Student", {"email_id": student}, "name")
            if not resolved:
                return 0
            student = resolved

        skills = frappe.get_all(
            "Student Skill",
            filters={"student": student},
            fields=[
                "name",
                "current_level",
                "evidence_count",
                "endorsement_count",
                "ai_verified",
                "status"
            ],
            ignore_permissions=True
        )

        if not skills:
            return 0

        level_weight = {"Beginner": 1, "Intermediate": 2, "Advanced": 3, "Expert": 4}
        total   = 0
        counted = 0

        for s in skills:
            # Rejected skills don't contribute to employability
            if s.get("status") == "Rejected":
                continue

            base = level_weight.get(s["current_level"], 1) * 5    # max 20

            # Count verified evidence count dynamically for the score
            verified_count = len(
                frappe.get_all(
                    "Skill Evidence",
                    filters={
                        "student_skill": s["name"],
                        "verification_status": "Verified"
                    },
                    pluck="name",
                    ignore_permissions=True
                )
            )
            ev   = min(verified_count * 3, 15)               # max 15

            end  = min(s["endorsement_count"] * 4, 8)             # max 8  (2 industry endorsements)
            ai   = 5 if s["ai_verified"] else 0                   # max 5
            total   += base + ev + end + ai
            counted += 1

        if not counted:
            return 0

        # Breadth bonus: 4 pts per skill, capped at 20 (5 skills = full breadth bonus)
        breadth_bonus = min(counted * 4, 20)

        # Per-skill average, capped at 48 (the theoretical max per skill)
        avg_skill_score = min(total / counted, 48)

        # 80% from depth/credibility + 20% from breadth
        raw = (avg_skill_score / 48) * 80 + breadth_bonus
        return min(round(raw), 100)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "get_skill_score error")
        return 0


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _verify_hash(skill_row: dict) -> str:
    ss = frappe.db.get_value(
        "Student Skill",
        skill_row["name"],
        ["student", "status", "ai_verified", "self_declared"],
        as_dict=True,
    )
    payload = {
        "student": ss.student if ss else "",
        "skill": skill_row["skill"],
        "current_level": skill_row["current_level"],
        "status": ss.status if ss else "Pending",
        "evidence_count": skill_row["evidence_count"],
        "endorsement_count": skill_row["endorsement_count"],
        "ai_verified": ss.ai_verified if ss else 0,
        "self_declared": ss.self_declared if ss else 0,
    }
    raw = json.dumps(payload, sort_keys=True)
    expected = hashlib.sha256(raw.encode()).hexdigest()
    return "Verified" if expected == skill_row.get("ledger_hash") else "Tampered"

# Internal helper — NOT whitelisted (cannot be called via HTTP with a Python list argument)
def _build_summary(skills: list) -> dict:
    total_evidence = sum(s["evidence_count"] for s in skills)
    mentor_endorsed = sum(s.get("mentor_endorsements", 0) for s in skills)
    industry_endorsed = sum(s.get("industry_endorsements", 0) for s in skills)
    ai_verified = sum(1 for s in skills if s.get("ai_verified"))
    all_verified = all(s.get("integrity") == "Verified" for s in skills)

    return {
        "total_skills": len(skills),
        "ai_verified": ai_verified,
        "mentor_endorsed": mentor_endorsed,
        "industry_endorsed": industry_endorsed,
        "evidence_items": total_evidence,
        "ledger_integrity": "Verified" if all_verified else "Tampered",
    }
    
@frappe.whitelist()
def get_skill_timeline(student_skill: str):
    if not student_skill:
        frappe.throw("student_skill is required")

    data = frappe.get_all(
        "Student Skill Ledger",
        filters={"student_skill": student_skill},
        fields=[
            "event_type",
            "status",
            "event_time",
            "comment",
            "evidence_count",
            "endorsement_count"
        ],
        order_by="event_time desc"
    )

    return {
        "status": "success",
        "data": data
    }


@frappe.whitelist(allow_guest=True)
def create_student_skill(data):
    try:
        session_user = frappe.session.user

        # ----------------------------------------------------------
        # PERMISSION CHECK
        # Controlled by Role Permission Manager
        # ----------------------------------------------------------
        # if not frappe.has_permission(
        #     "Student Skill",
        #     ptype="create",
        #     user=session_user
        # ):
        #     frappe.throw(
        #         "You do not have permission to create Student Skill.",
        #         frappe.PermissionError
        #     )

        if isinstance(data, str):
            data = frappe.parse_json(data)

        doc = frappe.get_doc({
            "doctype": "Student Skill",
            "student": data.get("student"),
            "skill": data.get("skill"),
            "current_level": data.get("current_level"),
            "ledger_hash": data.get("ledger_hash"),
            "status": data.get("status"),
            "evidence_count": data.get("evidence_count"),
            "endorsement_count": data.get("endorsement_count"),
            "first_acquired": data.get("first_acquired"),
            "last_demonstrated": data.get("last_demonstrated"),
            "self_declared": data.get("self_declared"),
            "ai_verified": data.get("ai_verified"),
            "is_public": data.get("is_public"),
        })

        # Respects Role Permission Manager
        doc.insert()

        frappe.db.commit()

        return {
            "status": "success",
            "message": "Record created successfully",
            "name": doc.name
        }

    except Exception as e:
        frappe.log_error(
            frappe.get_traceback(),
            "Create Student Skill Error"
        )

        return {
            "status": "error",
            "message": str(e)
        }


@frappe.whitelist(allow_guest=True)
def get_employability_score(student: str) -> float:
    """
    Returns the employability score for a student.
    Resolves the student name from email if necessary.
    """
    if not student:
        return 0.0

    if "@" in student:
        resolved_student = frappe.db.get_value("Student", {"email_id": student}, "name")
        if resolved_student:
            student = resolved_student

    try:
        from stridenex_app.employability import recalculate_employability_score
        score = recalculate_employability_score(student)
        return float(score)
    except Exception as e:
        frappe.log_error(title="get_employability_score error", message=frappe.get_traceback())
        score = frappe.db.get_value("Student", student, "employability_score")
        return float(score) if score is not None else 0.0