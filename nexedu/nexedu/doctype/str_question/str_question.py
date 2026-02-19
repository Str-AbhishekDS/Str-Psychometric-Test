# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class StrQuestion(Document):
	def validate(self):

		# If multiple correct is enabled
		if self.multiple_correct_answers:

			for i in range(1, 11):

				option_value = self.get(f"option_{i}")

				if option_value:
					self.set(f"is_correct_{i}", 1)

		# else:

		# 	# # If unchecked, remove all correct flags
		# 	# for i in range(1, 11):

		# 	# 	if self.get(f"is_correct_{i}"):
		# 	# 		self.set(f"is_correct_{i}", 0)

