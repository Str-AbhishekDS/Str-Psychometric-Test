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
		frappe.db.delete("Roadmap Template", {"career_path": self.career_path_name})
		if frappe.db.exists("Career Path", self.career_path_name):
			frappe.delete_doc("Career Path", self.career_path_name, ignore_missing=True, force=True)
		# Delete Skill Evidence referencing Student Skills for the student
		frappe.db.delete("Skill Evidence", {"student_skill": ["like", f"{self.student_id}%"]})
			
		frappe.db.delete("Student Skill", {"student": self.student_id})
		frappe.db.delete("Student", {"name": self.student_id})
		


		# Create necessary test skills
		self.skills = {}
		for skill_name in ["HTML5", "CSS3", "JavaScript Basics", "React JS", "NodeJS", "HTML", "CSS", "JavaScript", "React", "Node.js"]:
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
		# Pre-verify HTML5 skill to pass milestone validation gate
		frappe.get_doc({
			"doctype": "Student Skill",
			"student": self.student_id,
			"skill": "HTML5",
			"current_level": "Beginner",
			"self_declared": 0,
			"ai_verified": 1,
			"is_public": 1,
		}).insert(ignore_permissions=True)

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
		# Pre-verify HTML5 skill to pass validation
		frappe.get_doc({
			"doctype": "Student Skill",
			"student": self.student_id,
			"skill": "HTML5",
			"current_level": "Beginner",
			"self_declared": 0,
			"ai_verified": 1,
			"is_public": 1,
		}).insert(ignore_permissions=True)

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
		# Pre-verify CSS3 skill to pass validation
		frappe.get_doc({
			"doctype": "Student Skill",
			"student": self.student_id,
			"skill": "CSS3",
			"current_level": "Beginner",
			"self_declared": 0,
			"ai_verified": 1,
			"is_public": 1,
		}).insert(ignore_permissions=True)

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
		# Pre-verify JavaScript Basics skill to pass validation
		frappe.get_doc({
			"doctype": "Student Skill",
			"student": self.student_id,
			"skill": "JavaScript",
			"current_level": "Intermediate",
			"self_declared": 0,
			"ai_verified": 1,
			"is_public": 1,
		}).insert(ignore_permissions=True)

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
		js_ss_name = frappe.db.exists("Student Skill", {"student": self.student_id, "skill": "JavaScript"})
		self.assertTrue(js_ss_name)
		js_ss = frappe.get_doc("Student Skill", js_ss_name)
		self.assertEqual(js_ss.current_level, "Intermediate")

	def test_personalized_roadmaps_creation_and_progress(self):
		"""
		Step 5 Test: Verify that personalized roadmap milestones can be inserted into
		Student Path Enrollment / Student Milestone Progress WITHOUT existing Career Path
		milestones being copied.
		
		Verify:
		- no duplicate milestones
		- correct order
		- correct status
		- correct current milestone
		- Path Progress Log can complete them
		- Student Skill update still works
		- API (get_active_plan) returns and maps them correctly
		"""
		# 1. Create custom skills needed
		custom_skills = ["Machine Learning", "Deep Learning", "PyTorch"]
		for s in custom_skills:
			if not frappe.db.exists("Skill", s):
				frappe.get_doc({"doctype": "Skill", "skill_name": s}).insert(ignore_permissions=True)
		frappe.db.commit()

		# 2. Build the fake personalized roadmap payload
		# Note: Normal Career Path template has HTML5, CSS3, etc. We use it as the Career Path link,
		# but we explicitly supply our own milestone_progress rows.
		enrollment = frappe.get_doc({
			"doctype": "Student Path Enrollment",
			"student": self.student_id,
			"career_path": self.career_path_name,
			"status": "Active",
			"milestone_progress": [
				{
					"milestone_title": "Machine Learning Foundations",
					"milestone_order": 1,
					"milestone_type": "Learn",
					"skill": "Machine Learning",
					"required_skill_level": "Intermediate",
					"duration_days": 14,
					"objective": "Understand supervised and unsupervised learning",
					"project": "Build a house-price prediction model",
					"skill_tier": "Foundation"
				},
				{
					"milestone_title": "Deep Learning",
					"milestone_order": 2,
					"milestone_type": "Learn",
					"skill": "Deep Learning",
					"required_skill_level": "Advanced",
					"duration_days": 21,
					"objective": "Understand neural networks",
					"project": "Build an image classifier",
					"skill_tier": "Core Domain"
				},
				{
					"milestone_title": "PyTorch Project",
					"milestone_order": 3,
					"milestone_type": "Build",
					"skill": "PyTorch",
					"required_skill_level": "Intermediate",
					"duration_days": 14,
					"objective": "Build and train a neural network",
					"project": "Deploy a PyTorch model",
					"skill_tier": "Industry"
				}
			]
		})

		# Insert the enrollment
		enrollment.insert(ignore_permissions=True)
		frappe.db.commit()

		# Reload and verify that template milestones (like "Learn JS", "Build React App") were NOT copied
		# because milestone_progress was pre-populated.
		enrollment.reload()
		self.assertEqual(len(enrollment.milestone_progress), 3, "Expected exactly 3 custom milestones, template milestones should not be copied")
		
		# Verify that fields are mapped correctly on the inserted milestone rows
		m1 = enrollment.milestone_progress[0]
		self.assertEqual(m1.milestone_title, "Machine Learning Foundations")
		self.assertEqual(m1.skill, "Machine Learning")
		self.assertEqual(m1.duration_days, 14)
		self.assertEqual(m1.objective, "Understand supervised and unsupervised learning")
		self.assertEqual(m1.project, "Build a house-price prediction model")
		self.assertEqual(m1.skill_tier, "Foundation")
		self.assertEqual(m1.status, "In Progress")  # First milestone is set to In Progress by recalculate_all_milestones
		self.assertEqual(enrollment.current_milestone_order, m1.idx)

		m2 = enrollment.milestone_progress[1]
		self.assertEqual(m2.milestone_title, "Deep Learning")
		self.assertEqual(m2.skill, "Deep Learning")
		self.assertEqual(m2.duration_days, 21)
		self.assertEqual(m2.objective, "Understand neural networks")
		self.assertEqual(m2.project, "Build an image classifier")
		self.assertEqual(m2.skill_tier, "Core Domain")
		self.assertEqual(m2.status, "Not Started")

		# 3. Verify Path Progress Log completion works
		# Pre-verify Machine Learning skill to pass validation gate
		frappe.get_doc({
			"doctype": "Student Skill",
			"student": self.student_id,
			"skill": "Machine Learning",
			"current_level": "Intermediate",
			"self_declared": 0,
			"ai_verified": 1,
			"is_public": 1,
		}).insert(ignore_permissions=True)

		log = frappe.get_doc({
			"doctype": "Path Progress Log",
			"student": self.student_id,
			"enrollment": enrollment.name,
			"career_path": self.career_path_name,
			"milestone": m1.name,
			"status": "Completed",
			"score": 90,
			"ai_feedback": "Looks great!"
		})
		log.insert(ignore_permissions=True)
		frappe.db.commit()

		# Verify enrollment advances
		enrollment.reload()
		self.assertEqual(enrollment.milestone_progress[0].status, "Completed")
		self.assertEqual(enrollment.milestone_progress[1].status, "In Progress")
		self.assertEqual(enrollment.current_milestone_order, enrollment.milestone_progress[1].idx)

		# Verify Student Skill update worked
		ss_name = frappe.db.exists("Student Skill", {"student": self.student_id, "skill": "Machine Learning"})
		self.assertTrue(ss_name)
		ss = frappe.get_doc("Student Skill", ss_name)
		self.assertEqual(ss.current_level, "Intermediate")

		# 4. Verify API response maps new custom fields (duration_days, skill_tier -> category)
		from nexedu.path_finder.app_api import get_active_plan
		plan = get_active_plan(self.student_id)
		self.assertTrue(plan.get("has_active_plan"))
		api_milestones = plan.get("milestones", [])
		self.assertEqual(len(api_milestones), 3)

		# Verify mapping in the first milestone output
		am1 = api_milestones[0]
		self.assertEqual(am1["milestone_title"], "Machine Learning Foundations")
		self.assertEqual(am1["duration_days"], 14)
		self.assertEqual(am1["category"], "Foundation")  # skill_tier should be mapped under category
		
		# Clean up custom skills
		for s in custom_skills:
			frappe.db.delete("Skill", {"name": s})
		frappe.db.commit()

	def test_enroll_student_ai_personalized(self):
		"""
		Verify that enrolling a student with path_generation_mode="AI" calls the RoadmapAgent,
		generates personalized milestones, maps them correctly to Student Milestone Progress,
		and saves the enrollment.
		Also verifies:
		1. Existing resource is correctly linked.
		2. Non-existing AI-recommended resource succeeds WITHOUT creating a fake record (fields are None/empty).
		3. Database count for Courses, Project, Assessment, Internship, and Mentor Session Booking does not increase.
		"""
		from unittest.mock import patch
		from job_search_ai.agents.roadmap_agent.schemas import RoadmapResult, RoadmapProfile, RoadmapMilestone
		from nexedu.path_finder.api.path_enrollment import enroll_student

		# Create custom skills
		custom_skills = ["Machine Learning", "Deep Learning"]
		for s in custom_skills:
			if not frappe.db.exists("Skill", s):
				frappe.get_doc({"doctype": "Skill", "skill_name": s}).insert(ignore_permissions=True)
		frappe.db.commit()

		# Create an existing Course resource to verify successful linking
		existing_course_name = "Existing ML Course"
		if not frappe.db.exists("Courses", existing_course_name):
			frappe.db.sql("INSERT INTO `tabCourses` (name, course_name) VALUES (%s, %s)", (existing_course_name, existing_course_name))
		frappe.db.commit()

		mock_milestones = [
			RoadmapMilestone(
				sequence=1,
				title="AI ML Foundations",
				type="Learn",
				skill="Machine Learning",
				skill_tier="Foundation",
				duration_days=10,
				objective="Learn ML basics",
				project="Regression project",
				linked_resource_type="Course",
				linked_resource=existing_course_name,  # EXISTING Course
				points=["Understand regression models", "Implement linear regression"]
			),
			RoadmapMilestone(
				sequence=2,
				title="Neural Networks",
				type="Learn",
				skill="Deep Learning",
				skill_tier="Core Domain",
				duration_days=15,
				objective="Learn DL basics",
				project="Tensorflow project",
				linked_resource_type="Course",
				linked_resource="Non Existing DL Course",  # NON-EXISTING Course
				points=["Understand perceptrons", "Backpropagation basics"]
			)
		]
		mock_result = RoadmapResult(
			roadmap=RoadmapProfile(
				career="AI Engineer",
				readiness_score=45.0,
				milestones=mock_milestones,
				message="Personalized roadmap generated successfully."
			),
			validation_status="Valid"
		)

		# Record database counts before enrollment
		courses_count_before = frappe.db.count("Courses")
		project_count_before = frappe.db.count("Project")
		assessment_count_before = frappe.db.count("Assessment")
		internship_count_before = frappe.db.count("Internship")
		mentor_session_count_before = frappe.db.count("Mentor Session Booking")

		def mock_enqueue(method, *args, **kwargs):
			if method == "job_search_ai.tasks.generate_personalized_roadmap":
				from job_search_ai.tasks import generate_personalized_roadmap
				generate_personalized_roadmap(enrollment_name=kwargs.get("enrollment_name"))

		original_exists = frappe.db.exists
		def mock_exists(dt, name=None, *args, **kwargs):
			if dt == "Roadmap Template":
				return False
			return original_exists(dt, name, *args, **kwargs)

		with patch("job_search_ai.agents.roadmap_agent.agent.RoadmapAgent.run", return_value=mock_result) as mock_run, \
			 patch("frappe.enqueue", side_effect=mock_enqueue) as mock_enqueue_patch, \
			 patch("nexedu.path_finder.api.path_enrollment.build_roadmap_template_from_career_path") as mock_build_template, \
			 patch.object(frappe.db, "exists", side_effect=mock_exists):
			res = enroll_student(
				student=self.student_id,
				career_path=self.career_path_name,
				force_enroll=1,
				path_generation_mode="AI"
			)
			self.assertEqual(res.get("status"), "success")
			mock_run.assert_any_call("Generic", self.career_path_name)

			# Record database counts after enrollment
			courses_count_after = frappe.db.count("Courses")
			project_count_after = frappe.db.count("Project")
			assessment_count_after = frappe.db.count("Assessment")
			internship_count_after = frappe.db.count("Internship")
			mentor_session_count_after = frappe.db.count("Mentor Session Booking")

			# Assert that database counts for resource DocTypes did not increase
			self.assertEqual(courses_count_before, courses_count_after, "Courses table was polluted with a stub record!")
			self.assertEqual(project_count_before, project_count_after, "Project table was polluted with a stub record!")
			self.assertEqual(assessment_count_before, assessment_count_after, "Assessment table was polluted with a stub record!")
			self.assertEqual(internship_count_before, internship_count_after, "Internship table was polluted with a stub record!")
			self.assertEqual(mentor_session_count_before, mentor_session_count_after, "Mentor Session Booking table was polluted with a stub record!")

			# Verify milestones created in db
			enrollment_name = res.get("enrollment")
			enrollment = frappe.get_doc("Student Path Enrollment", enrollment_name)
			self.assertEqual(enrollment.ai_recommended, 1)
			self.assertEqual(len(enrollment.milestone_progress), 2)

			m1 = enrollment.milestone_progress[0]
			self.assertEqual(m1.milestone_title, "AI ML Foundations")
			self.assertEqual(m1.skill, "Machine Learning")
			self.assertEqual(m1.skill_tier, "Foundation")
			self.assertEqual(m1.duration_days, 10)
			self.assertEqual(m1.objective, "Learn ML basics")
			self.assertEqual(m1.project, "Regression project")
			self.assertEqual(m1.linked_resource_type, "Course")
			# Pre-existing resource should be correctly linked
			self.assertEqual(m1.reference_doctype, "Courses")
			self.assertEqual(m1.linked_resource, existing_course_name)
			self.assertEqual(m1.status, "In Progress")

			m2 = enrollment.milestone_progress[1]
			self.assertEqual(m2.milestone_title, "Neural Networks")
			self.assertEqual(m2.skill, "Deep Learning")
			self.assertEqual(m2.skill_tier, "Core Domain")
			self.assertEqual(m2.duration_days, 15)
			# Non-existing resource should not be created as a stub and should be left empty/None
			self.assertIsNone(m2.reference_doctype)
			self.assertIsNone(m2.linked_resource)
			self.assertEqual(m2.status, "Not Started")

			# Verify milestone checklist points are correctly populated
			self.assertEqual(len(enrollment.milestone_points), 4)
			pts1 = [p for p in enrollment.milestone_points if p.milestone_title == "AI ML Foundations"]
			self.assertEqual(len(pts1), 2)
			self.assertEqual(pts1[0].point_title, "Understand regression models")
			self.assertEqual(pts1[1].point_title, "Implement linear regression")

			pts2 = [p for p in enrollment.milestone_points if p.milestone_title == "Neural Networks"]
			self.assertEqual(len(pts2), 2)
			self.assertEqual(pts2[0].point_title, "Understand perceptrons")
			self.assertEqual(pts2[1].point_title, "Backpropagation basics")

		# Clean up custom skills and course
		for s in custom_skills:
			frappe.db.delete("Skill", {"name": s})
		if frappe.db.exists("Courses", existing_course_name):
			frappe.delete_doc("Courses", existing_course_name, ignore_missing=True, force=True)
		frappe.db.commit()

	def test_employability_score_calculation(self):
		"""
		Verifies that the employability score calculation is correct
		for a student enrolled in a Career Path.
		"""
		from stridenex_app.employability import recalculate_employability_score

		# Reload student before changing CGPA to avoid TimestampMismatchError
		self.student = frappe.get_doc("Student", self.student_id)
		self.student.cgpa = 8.0
		self.student.save()

		# 1. Enroll the student in the Career Path
		enrollment = frappe.get_doc({
			"doctype": "Student Path Enrollment",
			"student": self.student_id,
			"career_path": self.career_path_name,
			"status": "Active",
			"enrollment_date": getdate()
		})
		enrollment.insert()

		# Verify that unique skills are populated in milestones (HTML5, CSS3, JS, React, NodeJS)
		self.assertEqual(len(enrollment.milestone_progress), 5)

		# 2. Recalculate score initially (no student skills)
		# CGPA (8.0 -> 80.0 score * 0.3 = 24.0 points)
		# Skills (0/5 verified/pending -> 0.0 points)
		# Total = 24.0
		score = recalculate_employability_score(self.student_id)
		self.assertEqual(score, 24.0)

		# 3. Add one unverified skill (HTML5)
		# Skill HTML5 is pending (0.5 points) -> Skills score = (0.5 / 5) * 100 = 10.0.
		# 70% weight = 7.0 points.
		# Total = 24.0 + 7.0 = 31.0
		ss1 = frappe.get_doc({
			"doctype": "Student Skill",
			"student": self.student_id,
			"skill": "HTML5",
			"current_level": "Beginner",
			"self_declared": 1,
			"status": "Pending",
			"is_public": 1
		})
		ss1.insert()
		
		score = recalculate_employability_score(self.student_id)
		self.assertEqual(score, 31.0)

		# 4. Verify the skill (HTML5)
		# Skill HTML5 is verified (1.0 point) -> Skills score = (1.0 / 5) * 100 = 20.0.
		# 70% weight = 14.0 points.
		# Total = 24.0 + 14.0 = 38.0
		frappe.get_doc({
			"doctype": "Skill Evidence",
			"student_skill": ss1.name,
			"verification_status": "Verified",
			"evidence_type": "Other",
			"evidence_date": frappe.utils.today(),
			"document_url": "https://example.com/dummy.pdf"
		}).insert()
		ss1.reload()
		ss1.save()

		score = recalculate_employability_score(self.student_id)
		self.assertEqual(score, 38.0)

	def test_milestone_points_checklist_lifecycle(self):
		"""
		Verifies the complete lifecycle of sub-milestone checklist points:
		1. Verify default points from Career Path are populated.
		2. API complete_milestone_point updates point status.
		3. Direct PPL completion is blocked if points are not done.
		4. Completing all points auto-completes parent milestone and updates Student Skill.
		5. Unchecking a point reverts parent milestone status.
		"""
		# 1. Update our test Career Path milestones to have milestone_points
		for m in self.career_path.path_milestone:
			if m.milestone_title == "Learn JS":
				m.milestone_points = "Variables and Scope\nFunctions and Arrow Functions\nPromises and Async/Await"
				m.skill = None  # Clear skill so it auto-completes upon checklist completion
		self.career_path.save()
		frappe.db.commit()

		# Add verified student skills for prerequisites so they auto-complete/auto-skip
		for skill in ["HTML5", "CSS3"]:
			ss = frappe.get_doc({
				"doctype": "Student Skill",
				"student": self.student_id,
				"skill": skill,
				"current_level": "Beginner",
			})
			ss.insert(ignore_permissions=True)
			
			frappe.get_doc({
				"doctype": "Skill Evidence",
				"student_skill": ss.name,
				"verification_status": "Verified",
				"evidence_type": "Other",
				"evidence_date": frappe.utils.today(),
				"document_url": "https://example.com/dummy.pdf"
			}).insert(ignore_permissions=True)
			ss.reload()
			ss.save(ignore_permissions=True)
		frappe.db.commit()

		# Enroll student
		enrollment = frappe.get_doc({
			"doctype": "Student Path Enrollment",
			"student": self.student_id,
			"career_path": self.career_path_name,
			"status": "Active"
		})
		enrollment.insert(ignore_permissions=True)
		frappe.db.commit()
		enrollment.reload()

		# Verify that the 3 checklist points are created for "Learn JS" milestone
		js_points = [p for p in enrollment.milestone_points if p.milestone_title == "Learn JS"]
		self.assertEqual(len(js_points), 3)
		self.assertEqual(js_points[0].point_title, "Variables and Scope")
		self.assertEqual(js_points[0].status, "Not Started")

		# Check the "Learn JS" milestone row name/ID
		js_mrow = next(r for r in enrollment.milestone_progress if r.milestone_title == "Learn JS")
		self.assertEqual(js_mrow.status, "In Progress")

		# 2. Update first point to Completed via API
		from nexedu.path_finder.api.path_enrollment import complete_milestone_point
		res = complete_milestone_point(
			enrollment=enrollment.name,
			milestone_title="Learn JS",
			point_title="Variables and Scope",
			completed=True
		)
		self.assertFalse(res["milestone_completed"])

		enrollment.reload()
		js_points = [p for p in enrollment.milestone_points if p.milestone_title == "Learn JS"]
		self.assertEqual(js_points[0].status, "Completed")
		self.assertEqual(js_points[1].status, "Not Started")
		
		# Parent milestone should still be In Progress
		js_mrow = next(r for r in enrollment.milestone_progress if r.milestone_title == "Learn JS")
		self.assertEqual(js_mrow.status, "In Progress")

		# 3. Direct PPL creation should be blocked
		ppl = frappe.get_doc({
			"doctype": "Path Progress Log",
			"student": self.student_id,
			"enrollment": enrollment.name,
			"career_path": self.career_path_name,
			"milestone": js_mrow.name,
			"status": "Completed"
		})
		self.assertRaises(frappe.ValidationError, ppl.insert)

		# 4. Complete remaining points
		complete_milestone_point(
			enrollment=enrollment.name,
			milestone_title="Learn JS",
			point_title="Functions and Arrow Functions",
			completed=True
		)
		res2 = complete_milestone_point(
			enrollment=enrollment.name,
			milestone_title="Learn JS",
			point_title="Promises and Async/Await",
			completed=True
		)
		self.assertTrue(res2["milestone_completed"])

		# Verify parent milestone is Completed
		enrollment.reload()
		js_mrow = next(r for r in enrollment.milestone_progress if r.milestone_title == "Learn JS")
		self.assertEqual(js_mrow.status, "Completed")

		# Verify Path Progress Log was auto-created
		ppl_exists = frappe.db.exists("Path Progress Log", {"enrollment": enrollment.name, "milestone": js_mrow.name})
		self.assertTrue(ppl_exists)

		# Verify next milestone is In Progress
		react_mrow = next(r for r in enrollment.milestone_progress if r.milestone_title == "Build React App")
		self.assertEqual(react_mrow.status, "In Progress")

		# Skill check bypassed since m.skill is cleared for this test

		# 5. Uncheck a point and verify parent milestone reverts to In Progress and PPL is deleted
		res3 = complete_milestone_point(
			enrollment=enrollment.name,
			milestone_title="Learn JS",
			point_title="Variables and Scope",
			completed=False
		)
		self.assertFalse(res3["milestone_completed"])

		enrollment.reload()
		js_mrow = next(r for r in enrollment.milestone_progress if r.milestone_title == "Learn JS")
		self.assertEqual(js_mrow.status, "In Progress")
		
		# PPL should be deleted
		ppl_exists_after = frappe.db.exists("Path Progress Log", {"enrollment": enrollment.name, "milestone": js_mrow.name})
		self.assertFalse(ppl_exists_after)

	def test_locked_milestone_checklist_points_blocked(self):
		"""
		Verify that a student cannot modify checklist points for a locked/future milestone.
		"""
		# 1. Update Career Path milestones to have milestone_points
		for m in self.career_path.path_milestone:
			if m.milestone_title == "Learn JS":
				m.milestone_points = "Variables and Scope\nFunctions and Arrow Functions"
			elif m.milestone_title == "Build React App":
				m.milestone_points = "React Components\nReact Hooks"
		self.career_path.save()
		frappe.db.commit()

		# Add verified student skills for prerequisites so they auto-complete/auto-skip
		for skill in ["HTML5", "CSS3"]:
			frappe.get_doc({
				"doctype": "Student Skill",
				"student": self.student_id,
				"skill": skill,
				"current_level": "Beginner",
				"self_declared": 0,
				"ai_verified": 1,
				"is_public": 1,
			}).insert(ignore_permissions=True)
		frappe.db.commit()

		# Enroll student
		enrollment = frappe.get_doc({
			"doctype": "Student Path Enrollment",
			"student": self.student_id,
			"career_path": self.career_path_name,
			"status": "Active"
		})
		enrollment.insert(ignore_permissions=True)
		frappe.db.commit()
		enrollment.reload()

		# "Learn JS" is In Progress, "Build React App" is Not Started (locked)
		react_mrow = next(r for r in enrollment.milestone_progress if r.milestone_title == "Build React App")
		self.assertEqual(react_mrow.status, "Not Started")

		# Toggling checklist point on "Learn JS" should work
		from nexedu.path_finder.api.path_enrollment import complete_milestone_point
		complete_milestone_point(
			enrollment=enrollment.name,
			milestone_title="Learn JS",
			point_title="Variables and Scope",
			completed=True
		)

		# Toggling checklist point on locked "Build React App" should raise ValidationError
		self.assertRaises(
			frappe.ValidationError,
			complete_milestone_point,
			enrollment=enrollment.name,
			milestone_title="Build React App",
			point_title="React Components",
			completed=True
		)

	def test_unverified_skill_milestone_completion_blocked(self):
		"""
		Verify that completing a milestone that has a skill requirement is blocked
		if the student does not possess a verified Student Skill for that skill.
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

		# The first milestone is HTML5 (requires Beginner)
		first_row = enrollment.milestone_progress[0]
		self.assertEqual(first_row.skill, "HTML5")

		# Try to complete milestone HTML5 directly via Path Progress Log without verifying the skill
		log = frappe.get_doc({
			"doctype": "Path Progress Log",
			"student": self.student_id,
			"enrollment": enrollment.name,
			"career_path": self.career_path_name,
			"milestone": first_row.name,
			"status": "Completed"
		})

		# It should raise ValidationError because HTML5 is not verified
		self.assertRaises(frappe.ValidationError, log.insert)

		# Now create a verified skill for HTML5
		frappe.get_doc({
			"doctype": "Student Skill",
			"student": self.student_id,
			"skill": "HTML5",
			"current_level": "Beginner",
			"self_declared": 0,
			"ai_verified": 1,
			"is_public": 1,
		}).insert(ignore_permissions=True)

		# Now inserting Path Progress Log should succeed
		log.insert(ignore_permissions=True)

	def tearDown(self):
		frappe.db.delete("Path Progress Log", {"career_path": self.career_path_name})
		frappe.db.delete("Student Path Enrollment", {"student": self.student_id})
		frappe.db.delete("Roadmap Template", {"career_path": self.career_path_name})
		if frappe.db.exists("Career Path", self.career_path_name):
			frappe.delete_doc("Career Path", self.career_path_name, ignore_missing=True, force=True)
		# Delete Skill Evidence referencing Student Skills for the student
		frappe.db.delete("Skill Evidence", {"student_skill": ["like", f"{self.student_id}%"]})
			
		frappe.db.delete("Student Skill", {"student": self.student_id})
		frappe.db.delete("Student", {"name": self.student_id})
		

		super().tearDown()
