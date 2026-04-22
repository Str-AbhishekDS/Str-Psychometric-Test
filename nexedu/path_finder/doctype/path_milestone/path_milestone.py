import frappe
from frappe.model.document import Document

class PathMilestone(Document):

    def autoname(self):
        if not self.parent:
            return

        parent_name = self.parent.strip()

        # Get last number used for this parent
        last_name = frappe.db.sql("""
            SELECT name
            FROM `tabPath Milestone`
            WHERE parent = %s
            ORDER BY creation DESC
            LIMIT 1
        """, (self.parent,))

        last_number = 0

        if last_name:
            try:
                last_part = last_name[0][0].split("-")[-1]
                last_number = int(last_part)
            except:
                last_number = 0

        next_number = last_number + 1

        self.name = f"{parent_name} - MS-{next_number:04d}"