import frappe
import unittest

 
class TestStudentSkill(unittest.TestCase):
 
    def setUp(self):
        frappe.set_user("Administrator")
        # Ensure a test student and skill exist
        student = frappe.db.get_value("Student", {}, "name")
        if student:
            frappe.db.delete("Skill Endorsement", {"student_skill": ["like", f"{student}%"]})
            frappe.db.delete("Student Skill", {"student": student})
        if not frappe.db.exists("Skill", {"skill_name": "Test Python"}):
            frappe.get_doc({
                "doctype": "Skill",
                "skill_name": "Test Python",
                "skill_category": "Technical",  # adjust to match your category
                "skill_level_schema": "Beginner→Expert",
            }).insert()
 
    def test_declare_skill_creates_student_skill(self):
        from nexedu.skill_ledger.doctype.skill.skill import declare_skill
        # Use a real student name from your test fixtures
        student = frappe.db.get_value("Student", {}, "name")
        if not student:
            self.skipTest("No Student records found")
        skill = frappe.db.get_value("Skill", {"skill_name": "Test Python"}, "name")
        ss_name = declare_skill(student, skill, "Intermediate")
        self.assertTrue(frappe.db.exists("Student Skill", ss_name))
 
    def test_ledger_hash_changes_on_level_update(self):
        student = frappe.db.get_value("Student", {}, "name")
        if not student:
            self.skipTest("No Student records found")
        skill = frappe.db.get_value("Skill", {"skill_name": "Test Python"}, "name")
        # Create fresh Student Skill
        ss = frappe.get_doc({
            "doctype": "Student Skill",
            "student": student,
            "skill": skill,
            "current_level": "Beginner",
            "self_declared": 1,
            "is_public": 1,
        })
        ss.insert()
        old_hash = ss.ledger_hash
        ss.update_skill_level("Advanced")
        self.assertNotEqual(old_hash, ss.ledger_hash)
 
    def test_duplicate_endorsement_raises(self):
        from nexedu.skill_ledger.doctype.skill_endorsement.skill_endorsement import add_endorsement
        student = frappe.db.get_value("Student", {}, "name")
        if not student:
            self.skipTest("No Student records found")
        skill = frappe.db.get_value("Skill", {"skill_name": "Test Python"}, "name")
        ss_name = frappe.db.get_value(
            "Student Skill", {"student": student, "skill": skill}, "name"
        )
        if not ss_name:
            self.skipTest("No Student Skill found")
 
        add_endorsement(ss_name, "Intermediate", "Mentor")
        with self.assertRaises(frappe.DuplicateEntryError):
            add_endorsement(ss_name, "Advanced", "Mentor")
 
    def test_skill_score_range(self):
        from nexedu.skill_ledger.doctype.student_skill.student_skill import get_skill_score
        student = frappe.db.get_value("Student", {}, "name")
        if not student:
            self.skipTest("No Student records found")
        score = get_skill_score(student)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_submit_skill_test_answers_marks_ai_verified(self):
        from unittest.mock import patch
        from nexedu.api.skill_assessment_ai import submit_skill_test_answers

        student = frappe.db.get_value("Student", {}, "name")
        if not student:
            self.skipTest("No Student records found")
        skill = frappe.db.get_value("Skill", {"skill_name": "Test Python"}, "name")

        # Ensure Student Skill exists at Beginner level
        ss_name = frappe.db.get_value("Student Skill", {"student": student, "skill": skill}, "name")
        if ss_name:
            ss_doc = frappe.get_doc("Student Skill", ss_name)
            ss_doc.current_level = "Beginner"
            ss_doc.ai_verified = 0
            ss_doc.save(ignore_permissions=True)
        else:
            ss_doc = frappe.get_doc({
                "doctype": "Student Skill",
                "student": student,
                "skill": skill,
                "current_level": "Beginner",
                "self_declared": 1,
                "is_public": 1,
            })
            ss_doc.insert(ignore_permissions=True)
            ss_name = ss_doc.name

        from nexedu.skill_ledger.doctype.student_skill.student_skill import get_skill_score

        # Get score before test submission
        score_before = get_skill_score(student)

        answers = {
            "What is Python?": "A programming language"
        }

        mock_scores = {
            "score": 85.0,
            "passed": True,
            "verification_status": "Pass",
            "total_correct": 1,
            "total_questions": 1,
            "pass_score": 60,
            "breakdown": [
                {
                    "index": 1,
                    "type": "short_answer",
                    "question": "What is Python?",
                    "selected_answer": "A programming language",
                    "correct_answer": "",
                    "answer_score": 85.0,
                    "is_correct": True,
                    "evaluation_comment": "Good job",
                    "difficulty": "medium",
                }
            ]
        }

        mock_feedback = {
            "summary": "Passed assessment.",
            "strengths": ["Understanding of python"],
            "gaps": [],
            "next_step": "Move to intermediate.",
            "status": "verified"
        }

        mock_evals = {
            1: {
                "answer_score": 100.0,
                "is_correct": True,
                "evaluation_comment": "Good job",
            }
        }

        with patch("nexedu.api.skill_assessment_ai._evaluate_written_answers", return_value=mock_evals), \
             patch("nexedu.api.skill_assessment_ai._result_feedback", return_value=mock_feedback):

            submit_skill_test_answers(
                student=student,
                skill=skill,
                level="Intermediate",
                answers=answers
            )

        # Verify that student skill got updated
        updated_ss = frappe.get_doc("Student Skill", ss_name)
        self.assertEqual(updated_ss.ai_verified, 1)
        self.assertEqual(updated_ss.current_level, "Intermediate")

        # Verify that skill score (marks) has increased
        score_after = get_skill_score(student)
        self.assertGreater(score_after, score_before)

    def test_recalculate_employability_score_based_on_required_skills(self):
        from stridenex_app.employability import recalculate_employability_score
        
        # 1. Create a dummy Stream, Course, Department
        stream_name = "Test Stream"
        course_name = "Test Course"
        dept_name = "Test Department"
        
        college_name = frappe.db.get_value("College", {}, "name")
        if not college_name:
            col = frappe.get_doc({
                "doctype": "College",
                "college_name": "Test College"
            })
            col.insert()
            college_name = col.name
        
        if not frappe.db.exists("Stream", stream_name):
            frappe.get_doc({"doctype": "Stream", "stream_name": stream_name}).insert()
            
        course_doc_name = f"{college_name}-{course_name}"
        if not frappe.db.exists("Courses", course_doc_name):
            frappe.get_doc({
                "doctype": "Courses",
                "course_name": course_name,
                "college": college_name
            }).insert()
            
        if not frappe.db.exists("College Department", dept_name):
            frappe.get_doc({"doctype": "College Department", "department_name": dept_name}).insert()
            
        # 2. Create required skills
        skill1_name = "Test Skill A"
        skill2_name = "Test Skill B"
        if not frappe.db.exists("Skill", {"skill_name": skill1_name}):
            frappe.get_doc({
                "doctype": "Skill",
                "skill_name": skill1_name,
                "skill_category": "Technical",
                "skill_level_schema": "Beginner→Expert"
            }).insert()
        if not frappe.db.exists("Skill", {"skill_name": skill2_name}):
            frappe.get_doc({
                "doctype": "Skill",
                "skill_name": skill2_name,
                "skill_category": "Technical",
                "skill_level_schema": "Beginner→Expert"
            }).insert()
            
        skill1 = frappe.db.get_value("Skill", {"skill_name": skill1_name}, "name")
        skill2 = frappe.db.get_value("Skill", {"skill_name": skill2_name}, "name")
            
        # 3. Create Educational Skill Requirement
        req_name = f"{stream_name} - {course_doc_name} - {dept_name}"
        if frappe.db.exists("Educational Skill Requirement", req_name):
            frappe.delete_doc("Educational Skill Requirement", req_name)
            
        req_doc = frappe.get_doc({
            "doctype": "Educational Skill Requirement",
            "stream": stream_name,
            "course": course_doc_name,
            "department": dept_name,
            "skills": [
                {"skill": skill1},
                {"skill": skill2}
            ]
        })
        req_doc.insert()
        
        # 4. Create Student with these details
        student_name = "test_employability_student@stridenex.com"
        if frappe.db.exists("Student", student_name):
            frappe.delete_doc("Student", student_name)
            
        student_doc = frappe.get_doc({
            "doctype": "Student",
            "first_name": "Test",
            "last_name": "Student",
            "email_id": student_name,
            "college": college_name,
            "stream": stream_name,
            "course": course_doc_name,
            "department": dept_name,
            "cgpa": 8.0  # CGPA score = (8.0 / 10.0) * 100 = 80.0. 30% weight = 24.0 points.
        })
        student_doc.insert()
        
        # 5. Initially, score should be 24.0 because the student has none of the required skills
        # CGPA = 8.0 -> 24.0 points. Skills score = 0 -> 0.0 points. Total = 24.0
        score = recalculate_employability_score(student_name)
        self.assertEqual(score, 24.0)
        
        # 6. Add one skill (unverified)
        # Skills score = 25.0 -> 70% weight = 17.5 points. Total = 24.0 + 17.5 = 41.5
        ss1 = frappe.get_doc({
            "doctype": "Student Skill",
            "student": student_name,
            "skill": skill1,
            "current_level": "Beginner",
            "self_declared": 1,
            "status": "Pending",
            "is_public": 1
        })
        ss1.insert()
        
        score = recalculate_employability_score(student_name)
        self.assertEqual(score, 41.5)
        
        # 7. Verify the first skill
        # Skills score = 50.0 -> 70% weight = 35.0 points. Total = 24.0 + 35.0 = 59.0
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
        
        score = recalculate_employability_score(student_name)
        self.assertEqual(score, 59.0)
        
        # 8. Add second skill (unverified)
        # Skills score = 75.0 -> 70% weight = 52.5 points. Total = 24.0 + 52.5 = 76.5
        ss2 = frappe.get_doc({
            "doctype": "Student Skill",
            "student": student_name,
            "skill": skill2,
            "current_level": "Beginner",
            "self_declared": 1,
            "status": "Pending",
            "is_public": 1
        })
        ss2.insert()
        
        score = recalculate_employability_score(student_name)
        self.assertEqual(score, 76.5)

    def test_get_employability_score_api(self):
        from nexedu.skill_ledger.doctype.student_skill.student_skill import get_employability_score
        student = frappe.db.get_value("Student", {}, "name")
        if not student:
            self.skipTest("No Student records found")
        
        score = get_employability_score(student)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 100.0)
        
        email = frappe.db.get_value("Student", student, "email_id")
        if email:
            score_by_email = get_employability_score(email)
            self.assertEqual(score, score_by_email)
 
    def tearDown(self):
        frappe.db.rollback()