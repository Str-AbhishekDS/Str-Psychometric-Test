# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt

# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime
from nexedu.path_finder.utils.milestone_engine import (
    recalculate_all_milestones,
    update_milestone_status
)

class StudentPathEnrollment(Document):
    
    def validate(self):

        for row in self.milestone_progress:
            if row.is_lock:
                if row.has_value_changed("status"):
                    frappe.throw(f"Milestone {row.milestone_title} is locked")
            
            if row.is_skippable and row.status == "Skippable":
                row.status = "Completed"

            # 🔹 Build
            if row.milestone_type == "Build":
                if not row.project_link and row.status == "Completed":
                    frappe.throw(f"Project link required for {row.milestone_title}")

            # 🔹 Assess
            if row.milestone_type == "Assess":
                if not row.assessment:
                    frappe.throw(f"Assessment required for {row.milestone_title}")

            # 🔹 Apply
            if row.milestone_type == "Apply":
                if row.review_status == "Approved":
                    row.status = "Completed"

    def before_insert(self):
        self.enrolled_at = now_datetime()
        self.current_milestone_order = 1
        self.status = "Active"

    def on_update(self):
        self.check_and_update_success_stories()
        
    def before_save(self):
        """
        Runs every save. Re-evaluates status for any changed rows.
        """
        # Only run if milestone_progress table has rows
        if not self.milestone_progress:
            return
        recalculate_all_milestones(self)
        
        for row in self.milestone_progress:
            update_milestone_status(row, self)

    # ADD this helper
    def _populate_milestones_from_path(self):
        """
        Reads milestones from Career Path and creates
        Student Milestone Progress rows.
        """
        import frappe
        path_doc = frappe.get_doc("Career Path", self.career_path)
        for m in sorted(path_doc.milestones, key=lambda x: x.order or 0):
            self.append("milestone_progress", {
                "milestone":       m.name,
                "milestone_title": m.milestone_title,
                "milestone_order": m.order,
                "milestone_type":  m.milestone_type,
                "linked_skill":    m.linked_skill,
                "is_skippable":    m.is_skippable,
                "assessment":      m.assessment,
                "pass_percentage": m.pass_percentage or 50,
                "status":          "Not Started",
                "is_locked":       1
            })
        
    def after_insert(self):
        """
        Runs once when enrollment is first created.
        Populates milestone_progress if not already populated.
        Then runs auto-skip and lock logic.
        """
        if not self.milestone_progress:
            self._populate_milestones_from_path()

        recalculate_all_milestones(self)
        self.save(ignore_permissions=True)

    def check_and_update_success_stories(self):
        # ✅ Fetch the ACTUAL previous status directly from DB
        # This works even when updated via direct SQL
        previous_status = frappe.db.get_value(
            "Student Path Enrollment",
            self.name,
            "status",
            cache=False        # ✅ cache=False forces fresh DB read
        )

        frappe.log_error(
            f"enrollment: {self.name} | "
            f"current status in doc: {self.status} | "
            f"previous status from DB: {previous_status}",
            "Success Stories Debug"
        )

        if self.status == "Completed" and previous_status != "Completed":
            self.update_success_stories()

    def update_success_stories(self):
        frappe.db.sql("""
            UPDATE `tabCareer Path`
            SET success_stories = IFNULL(success_stories, 0) + 1
            WHERE name = %s
        """, self.career_path)

        frappe.db.commit()

        frappe.msgprint(
            f"Success story counted for path: {self.career_path}",
            indicator="green",
            alert=True
        )
        
@frappe.whitelist()
def check_prerequisite_skills(student, career_path):

    prerequisites = frappe.db.sql("""
        SELECT
            ps.prerequisite_skills,
            ps.level
        FROM `tabPrerequisite Skills` ps
        WHERE ps.parent = %s
        AND ps.parenttype = 'Career Path'
    """, career_path, as_dict=True)

    if not prerequisites:
        return {
            "status": "clear",
            "message": "No prerequisites required.",
            "missing_skills": [],
            "partial_skills": [],
            "readiness_percent": 100
        }

    student_skills = frappe.db.sql("""
        SELECT skill, current_level
        FROM `tabStudent Skill`
        WHERE student = %s
    """, student, as_dict=True)

    student_skill_map = {
        s["skill"]: s["current_level"]
        for s in student_skills
    }

    level_order = {
        "Beginner": 1,
        "Intermediate": 2,
        "Advanced": 3,
        "Expert": 4
    }

    missing_skills = []
    partial_skills = []
    matched_skills = []

    for prereq in prerequisites:
        skill = prereq["prerequisite_skills"]
        required_level = prereq["level"]
        required_rank = level_order.get(required_level, 1)

        # ✅ Fetch recommended path from Skill Master
        skill_data = frappe.db.get_value(
            "Skill",
            skill,
            [
                "recommended_path",
                "min_level_achieved",
                "description"
            ],
            as_dict=True
        ) or {}

        # Build path info to send to frontend
        path_info = None
        if skill_data.get("recommended_path"):
            path_details = frappe.db.get_value(
                "Career Path",
                skill_data["recommended_path"],
                [
                    "path_name",
                    "estimated_duration_months",
                    "difficulty_level",
                    "average_salary_lpa"
                ],
                as_dict=True
            ) or {}

            path_info = {
                "path_name": skill_data["recommended_path"],
                "display_name": path_details.get("path_name"),
                "duration_months": path_details.get("estimated_duration_months"),
                "difficulty": path_details.get("difficulty_level"),
                "description": skill_data.get("path_description")
            }

        if skill not in student_skill_map:
            missing_skills.append({
                "skill": skill,
                "required_level": required_level,
                "current_level": None,
                "gap": "Not started",
                "recommended_path": path_info  # ✅ Path attached
            })

        else:
            student_level = student_skill_map[skill]
            student_rank = level_order.get(student_level, 1)

            if student_rank < required_rank:
                partial_skills.append({
                    "skill": skill,
                    "required_level": required_level,
                    "current_level": student_level,
                    "gap": f"Need to reach {required_level}",
                    "recommended_path": path_info  # ✅ Path attached
                })
            else:
                matched_skills.append(skill)

    total = len(prerequisites)
    matched = len(matched_skills)
    readiness_percent = round((matched / total) * 100, 2) if total else 100

    status = "clear"
    if missing_skills or partial_skills:
        status = "partial" if readiness_percent >= 50 else "not_ready"

    return {
        "status": status,
        "readiness_percent": readiness_percent,
        "matched": matched,
        "total_prerequisites": total,
        "missing_skills": missing_skills,
        "partial_skills": partial_skills,
        "matched_skills": matched_skills
    }