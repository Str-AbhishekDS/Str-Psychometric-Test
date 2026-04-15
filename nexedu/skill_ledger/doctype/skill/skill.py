# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Skill(Document):
	def validate(self):

		if self.topic:
			if not frappe.db.exists("Topics", self.topic):
				frappe.throw(f"Topic {self.topic} not found")

			topic_category = frappe.db.get_value("Topics", self.topic, "category")

			if topic_category != self.skill_category:
				frappe.throw("Topic category mismatch")

		if self.subtopic:
			if not frappe.db.exists("Subtopic", self.subtopic):
				frappe.throw(f"Subtopic {self.subtopic} not found")

			subtopic_topic = frappe.db.get_value("Subtopic", self.subtopic, "topic")

			if subtopic_topic != self.topic:
				frappe.throw("Subtopic must belong to selected Topic")


"""
DocType: Skill
Purpose: Master list of skills with category, level schema, O*NET code,
         topic/subtopic classification, and industry alignment.
"""

import frappe
from frappe.model.document import Document


class Skill(Document):

    def before_save(self):
        self._validate_skill_name_unique()

    def _validate_skill_name_unique(self):
        # skill_name already has unique=1 in the DocType but
        # we add a friendlier error message here
        existing = frappe.db.get_value(
            "Skill",
            {"skill_name": self.skill_name, "name": ("!=", self.name)},
            "name",
        )
        if existing:
            frappe.throw(
                f"A skill named '{self.skill_name}' already exists ({existing}).",
                frappe.DuplicateEntryError,
            )


# ------------------------------------------------------------------
# Whitelisted API
# ------------------------------------------------------------------

@frappe.whitelist()
def get_skill_catalog(category: str = "", trending_only: bool = False) -> list:
    """
    Returns the skill master catalog.

    Args:
        category:      Optional Skill Category filter.
        trending_only: If True, returns only trending skills.

    Returns:
        List of skill dicts.
    """
    filters = {}
    if category:
        filters["skill_category"] = category
    if trending_only:
        filters["is_trending"] = 1

    return frappe.get_all(
        "Skill",
        filters=filters,
        fields=[
            "name", "skill_name", "skill_category", "onet_code",
            "skill_level_schema", "topic", "subtopic",
            "recommended_path", "is_trending", "description",
        ],
        order_by="skill_category asc, skill_name asc",
    )


@frappe.whitelist()
def search_skills(query: str) -> list:
    """Full-text search across skill_name and description."""
    return frappe.get_all(
        "Skill",
        filters=[
            ["skill_name", "like", f"%{query}%"],
        ],
        fields=["name", "skill_name", "skill_category", "is_trending"],
        limit=20,
    )


@frappe.whitelist()
def declare_skill(student: str, skill: str, level: str = "Beginner") -> str:
    """
    Self-declare a skill for a student. Creates a Student Skill record if one
    does not already exist.

    Args:
        student: Student document name.
        skill:   Skill document name.
        level:   Initial level (default: Beginner).

    Returns:
        The Student Skill document name.
    """
    existing = frappe.db.get_value(
        "Student Skill", {"student": student, "skill": skill}, "name"
    )
    if existing:
        frappe.msgprint(f"Skill already declared: {existing}")
        return existing

    doc = frappe.get_doc(
        {
            "doctype": "Student Skill",
            "student": student,
            "skill": skill,
            "current_level": level,
            "self_declared": 1,
            "is_public": 1,
        }
    )
    doc.insert()
    return doc.name