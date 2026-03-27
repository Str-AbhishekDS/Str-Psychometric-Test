import frappe
from frappe.model.document import Document


class PathProgressLog(Document):

    def validate(self):
        self.fetch_milestone_order()
        self.prevent_duplicate_entry()
        self.enforce_sequential_progress()

    def on_update(self):
        self.update_enrollment_progress()
        self.create_student_skill()


    # ══════════════════════════════════════════
    # 1. FETCH MILESTONE ORDER
    # ══════════════════════════════════════════
    def fetch_milestone_order(self):
        if not self.milestone:
            return

        milestone_order = frappe.db.get_value(
            "Path Milestone",
            {"name": self.milestone, "parent": self.career_path},
            "order"
        )

        if milestone_order is not None:
            self.order = int(milestone_order)
        else:
            frappe.throw(
                f"Milestone '{self.milestone}' does not belong to "
                f"Career Path '{self.career_path}'."
            )


    # ══════════════════════════════════════════
    # 2. PREVENT DUPLICATE MILESTONE ENTRY
    # ══════════════════════════════════════════
    # Check BEFORE sequential so user gets clean error
    def prevent_duplicate_entry(self):
        if not self.enrollment or not self.milestone:
            return

        exists = frappe.db.exists("Path Progress Log", {
            "enrollment": self.enrollment,
            "milestone": self.milestone,
            "name": ["!=", self.name]
        })

        if exists:
            frappe.throw(
                f"Milestone '{self.milestone}' is already completed "
                f"for this enrollment. Please create a new log "
                f"for the next milestone."
            )


    # ══════════════════════════════════════════
    # 3. ENFORCE SEQUENTIAL PROGRESS
    # ══════════════════════════════════════════
    def enforce_sequential_progress(self):
        if not self.enrollment or not self.order:
            return

        # ✅ FIX: Check if milestone changed on existing record
        # Get the ORIGINAL milestone order from DB before this save
        if not self.is_new():
            original_milestone = frappe.db.get_value(
                "Path Progress Log",
                self.name,
                "milestone"
            )
            # If milestone hasn't changed, no need to re-validate sequence
            if original_milestone == self.milestone:
                return

        # Get current expected order from enrollment
        current_milestone_order = frappe.db.get_value(
            "Student Path Enrollment",
            self.enrollment,
            "current_milestone_order"
        ) or 1

        if int(self.order) != int(current_milestone_order):
            frappe.throw(
                f"Cannot log Milestone Order {self.order}. "
                f"Please complete Milestone Order {current_milestone_order} first."
            )


    # ══════════════════════════════════════════
    # 4. UPDATE ENROLLMENT PROGRESS
    # ══════════════════════════════════════════
    def update_enrollment_progress(self):
        if not self.enrollment:
            return

        total = frappe.db.count("Path Milestone", {
            "parent": self.career_path
        })

        if not total:
            return

        current_order = int(self.order)
        percent = round((current_order / total) * 100, 2)
        next_order = current_order + 1
        status = "Completed" if current_order >= total else "Active"

        # ✅ Fetch previous status BEFORE updating
        previous_status = frappe.db.get_value(
            "Student Path Enrollment",
            self.enrollment,
            "status",
            cache=False
        )

        frappe.db.sql("""
            UPDATE `tabStudent Path Enrollment`
            SET
                current_milestone_order = %s,
                completion_percent = %s,
                status = %s,
                modified = NOW(),
                modified_by = %s
            WHERE name = %s
        """, (
            next_order,
            percent,
            status,
            frappe.session.user,
            self.enrollment
        ))

        frappe.db.commit()
        frappe.clear_cache(doctype="Student Path Enrollment")

        # ✅ Now check if status changed to Completed
        # and trigger success stories count
        if status == "Completed" and previous_status != "Completed":
            self.increment_success_stories()

        frappe.msgprint(
            f"Progress → Milestone {current_order}/{total} "
            f"| {percent}% | Next order: {next_order}",
            indicator="green",
            alert=True
        )


    def increment_success_stories(self):
        """
        Called when a student completes a career path.
        Increments success_stories count on Career Path.
        Triggered from Progress Log since enrollment
        is updated via direct SQL (bypasses doc hooks).
        """
        frappe.db.sql("""
            UPDATE `tabCareer Path`
            SET success_stories = IFNULL(success_stories, 0) + 1
            WHERE name = %s
        """, self.career_path)

        frappe.db.commit()

        frappe.msgprint(
            f"🎉 Path '{self.career_path}' completed! "
            f"Success stories updated.",
            indicator="green",
            alert=True
        )


    # ══════════════════════════════════════════
    # 5. CREATE STUDENT SKILL FROM MILESTONE
    # ══════════════════════════════════════════
    def create_student_skill(self):
        if not self.enrollment or not self.milestone:
            return

        enrollment = frappe.get_doc(
            "Student Path Enrollment",
            self.enrollment
        )
        milestone = frappe.get_doc("Path Milestone", self.milestone)

        if not milestone.get("skill"):
            return

        already_exists = frappe.db.exists("Student Skill", {
            "student": enrollment.student,
            "skill": milestone.skill
        })

        if already_exists:
            return

        frappe.get_doc({
            "doctype": "Student Skill",
            "student": enrollment.student,
            "skill": milestone.skill,
            "self_declared": 0,
            "current_level": "Beginner",
            "is_public": 1
        }).insert(ignore_permissions=True)

        frappe.db.commit()

        frappe.msgprint(
            f"Skill '{milestone.skill}' added to Skill Ledger.",
            indicator="blue",
            alert=True
        )
