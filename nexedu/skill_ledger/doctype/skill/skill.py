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
