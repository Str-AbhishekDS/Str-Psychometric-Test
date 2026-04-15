import frappe
import unittest

 
class TestStudentSkill(unittest.TestCase):
 
    def setUp(self):
        frappe.set_user("Administrator")
        # Ensure a test student and skill exist
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
        from nexedu.skill_ledger.doctype.skill_endorsement import add_endorsement
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
 
    def test_employability_score_range(self):
        from nexedu.skill_ledger.doctype.student_skill import get_employability_score
        student = frappe.db.get_value("Student", {}, "name")
        if not student:
            self.skipTest("No Student records found")
        score = get_employability_score(student)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)
 
    def tearDown(self):
        frappe.db.rollback()