# -*- coding: utf-8 -*-
# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class SkillAssessmentCache(Document):
	def autoname(self):
		self.name = self.skill.strip().lower()
