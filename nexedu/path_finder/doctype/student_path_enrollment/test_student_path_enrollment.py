# Copyright (c) 2026, Stride nex and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime, getdate

class IntegrationTestStudentPathEnrollment(IntegrationTestCase):
	"""
	Integration tests for Student Path Enrollment and Path Progress Log lifecycle.
	"""
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")

		self.student_id = "path_test_student@example.com"
		self.career_path_name = "Test Path Web Dev"
		
		# Clean up any residual test docs
		frappe.db.delete("Path Progress Log", {"career_path": self.career_path_name})
		frappe.db.delete("Student Path Enrollment", {"student": self.student_id})
		if frappe.db.exists("Career Path", self.career_path_name):
			frappe.delete_doc("Career Path", self.career_path_name, ignore_missing=True, force=True)
		frappe.db.delete("Student Skill", {"student": self.student_id})
		frappe.db.delete("Student", {"name": self.student_id})
		
		for skill_name in ["HTML5", "CSS3", "JavaScript Basics", "React JS", "NodeJS"]:
			frappe.db.delete("Skill", {"name": skill_name})
		frappe.db.commit()

		# Create necessary test skills
		self.skills = {}
		for skill_name in ["HTML5", "CSS3", "JavaScript Basics", "React JS", "NodeJS"]:
			if not frappe.db.exists("Skill", skill_name):
				doc = frappe.get_doc({
					"doctype": "Skill",
					"skill_name": skill_name
				})
				doc.insert(ignore_permissions=True)
			self.skills[skill_name] = skill_name

		# Create test college
		college_name = frappe.db.get_value("College", {}, "name")
		if not college_name:
			col = frappe.get_doc({
				"doctype": "College",
				"college_name": "Test College"
			})
			col.insert(ignore_permissions=True)
			college_name = col.name

		# Create student
		self.student = frappe.get_doc({
			"doctype": "Student",
			"first_name": "Path Test",
			"last_name": "Student",
			"email_id": self.student_id,
			"college": college_name
		})
		self.student.insert(ignore_permissions=True)

		# Create Career Path with prerequisite skills and milestones
		self.career_path = frappe.get_doc({
			"doctype": "Career Path",
			"path_name": self.career_path_name,
			"path_type": "Job",
			"difficulty_level": "Beginner-Friendly",
			"target_role": "Junior Web Developer",
			"estimated_duration_months": 6,
			"published": 1,
			"prerequisite_skills": [
				{
					"prerequisite_skills": self.skills["HTML5"],
					"level": "Beginner"
				},
				{
					"prerequisite_skills": self.skills["CSS3"],
					"level": "Beginner"
				}
			],
			"path_milestone": [
				{
					"milestone_title": "Learn JS",
					"milestone_type": "Learn",
					"skill": self.skills["JavaScript Basics"],
					"required_skill_level": "Intermediate",
					"is_mandatory": 1,
					"duration_days": 10
				},
				{
					"milestone_title": "Build React App",
					"milestone_type": "Build",
					"skill": self.skills["React JS"],
					"required_skill_level": "Beginner",
					"is_mandatory": 1,
					"duration_days": 15
				},
				{
					"milestone_title": "Assess NodeJS",
					"milestone_type": "Assess",
					"skill": self.skills["NodeJS"],
					"required_skill_level": "Beginner",
					"is_mandatory": 0,
					"duration_days": 5
				}
			]
		})
		self.career_path.insert(ignore_permissions=True)
		frappe.db.commit()

	def test_enrollment_creation_and_no_duplication(self):
		"""
		Test that when enrolling a student in a Career Path:
		1. Student Milestone Progress rows are created.
		2. There are no duplicate milestone progress rows.
		3. Prerequisites are represented correctly and NOT duplicated.
		"""
		enrollment = frappe.get_doc({
			"doctype": "Student Path Enrollment",
			"student": self.student_id,
			"career_path": self.career_path_name,
			"status": "Active"
		})
		enrollment.insert(ignore_permissions=True)
		frappe.db.commit()

		# Refresh to load populated milestones
		enrollment.reload()

		milestones = enrollment.milestone_progress
		
		# We expect:
		# Prereqs (HTML5, CSS3) - 2 rows
		# Milestones (Learn JS, Build React App, Assess NodeJS) - 3 rows
		# Total expected: 5 rows
		
		prereqs = [m for m in milestones if m.is_prereq]
		path_steps = [m for m in milestones if not m.is_prereq]

		self.assertEqual(len(prereqs), 2, f"Expected 2 prerequisite milestones, got {len(prereqs)}")
		self.assertEqual(len(path_steps), 3, f"Expected 3 path milestones, got {len(path_steps)}")
		self.assertEqual(len(milestones), 5, f"Expected 5 total milestones, got {len(milestones)}")

		# Check details of prereqs
		self.assertEqual(prereqs[0].skill, "HTML5")
		self.assertEqual(prereqs[0].required_skill_level, "Beginner")
		self.assertEqual(prereqs[1].skill, "CSS3")
		self.assertEqual(prereqs[1].required_skill_level, "Beginner")

		# Check details of path steps
		self.assertEqual(path_steps[0].milestone_title, "Learn JS")
		self.assertEqual(path_steps[0].required_skill_level, "Intermediate")
		self.assertEqual(path_steps[1].milestone_title, "Build React App")
		self.assertEqual(path_steps[1].required_skill_level, "Beginner")
		self.assertEqual(path_steps[2].milestone_title, "Assess NodeJS")
		self.assertEqual(path_steps[2].required_skill_level, "Beginner")

	def test_milestone_completion_advances_order(self):
		"""
		Test that completing a milestone via Path Progress Log:
		1. Marks the milestone as Completed.
		2. Sets the next milestone to In Progress.
		3. Advances current_milestone_order on the enrollment.
		"""
		enrollment = frappe.get_doc({
			"doctype": "Student Path Enrollment",
			"student": self.student_id,
			"career_path": self.career_path_name,
			"status": "Active"
		})
		enrollment.insert(ignore_permissions=True)
		frappe.db.commit()
		enrollment.reload()

		# Check that first milestone is In Progress, others are Not Started
		self.assertEqual(enrollment.milestone_progress[0].status, "In Progress")
		self.assertEqual(enrollment.current_milestone_order, enrollment.milestone_progress[0].idx)
		
		# Complete the first milestone
		first_row = enrollment.milestone_progress[0]
		log = frappe.get_doc({
			"doctype": "Path Progress Log",
			"student": self.student_id,
			"enrollment": enrollment.name,
			"career_path": self.career_path_name,
			"milestone": first_row.name,
			"score": 100,
			"status": "Completed",
			"feedback": "Great work!"
		})
		log.insert(ignore_permissions=True)
		frappe.db.commit()

		enrollment.reload()
		self.assertEqual(enrollment.milestone_progress[0].status, "Completed")
		self.assertEqual(enrollment.milestone_progress[1].status, "In Progress")
		self.assertEqual(enrollment.current_milestone_order, enrollment.milestone_progress[1].idx)

	def test_milestone_completion_updates_student_skill(self):
		"""
		Test that completing a milestone containing a skill:
		1. Creates a Student Skill record with the correct current_level.
		2. Upgrades the level when a higher level milestone is completed.
		"""
		enrollment = frappe.get_doc({
			"doctype": "Student Path Enrollment",
			"student": self.student_id,
			"career_path": self.career_path_name,
			"status": "Active"
		})
		enrollment.insert(ignore_permissions=True)
		frappe.db.commit()
		enrollment.reload()

		# Let's complete the first milestone which is HTML5 (prereq, idx=1)
		first_row = enrollment.milestone_progress[0]
		log1 = frappe.get_doc({
			"doctype": "Path Progress Log",
			"student": self.student_id,
			"enrollment": enrollment.name,
			"career_path": self.career_path_name,
			"milestone": first_row.name,
			"status": "Completed"
		})
		log1.insert(ignore_permissions=True)
		frappe.db.commit()

		# A Student Skill for HTML5 should have been created with current_level = Beginner
		ss_name = frappe.db.exists("Student Skill", {"student": self.student_id, "skill": "HTML5"})
		self.assertTrue(ss_name)
		ss = frappe.get_doc("Student Skill", ss_name)
		self.assertEqual(ss.current_level, "Beginner")

		# Complete the second milestone which is CSS3 (prereq, idx=2) to maintain sequential progression
		enrollment.reload()
		second_row = enrollment.milestone_progress[1]
		log2 = frappe.get_doc({
			"doctype": "Path Progress Log",
			"student": self.student_id,
			"enrollment": enrollment.name,
			"career_path": self.career_path_name,
			"milestone": second_row.name,
			"status": "Completed"
		})
		log2.insert(ignore_permissions=True)
		frappe.db.commit()

		# Now let's complete the Learn JS milestone (idx=3, which requires Intermediate level)
		enrollment.reload()
		js_row = enrollment.milestone_progress[2]
		log3 = frappe.get_doc({
			"doctype": "Path Progress Log",
			"student": self.student_id,
			"enrollment": enrollment.name,
			"career_path": self.career_path_name,
			"milestone": js_row.name,
			"status": "Completed"
		})
		log3.insert(ignore_permissions=True)
		frappe.db.commit()

		# Student Skill for JavaScript Basics should have been created with current_level = Intermediate
		js_ss_name = frappe.db.exists("Student Skill", {"student": self.student_id, "skill": "JavaScript Basics"})
		self.assertTrue(js_ss_name)
		js_ss = frappe.get_doc("Student Skill", js_ss_name)
		self.assertEqual(js_ss.current_level, "Intermediate")

	def tearDown(self):
		frappe.db.delete("Path Progress Log", {"career_path": self.career_path_name})
		frappe.db.delete("Student Path Enrollment", {"student": self.student_id})
		if frappe.db.exists("Career Path", self.career_path_name):
			frappe.delete_doc("Career Path", self.career_path_name, ignore_missing=True, force=True)
		frappe.db.delete("Student Skill", {"student": self.student_id})
		frappe.db.delete("Student", {"name": self.student_id})
		
		for skill_name in ["HTML5", "CSS3", "JavaScript Basics", "React JS", "NodeJS"]:
			frappe.db.delete("Skill", {"name": skill_name})
		frappe.db.commit()
		super().tearDown()
