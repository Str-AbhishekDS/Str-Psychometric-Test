# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt

from builtins import Exception, len, round, set, str, sum

import frappe
from frappe.model.document import Document
from frappe.utils import today, date_diff, add_days, getdate


class HabitPlan(Document):

    def validate(self):
        self.validate_dates()
        self.validate_habits()
        self.validate_unique_plan_name_per_student()

    def validate_dates(self):
        if self.end_date and self.start_date:
            if getdate(self.end_date) < getdate(self.start_date):
                frappe.throw("End Date cannot be before Start Date.")

    def validate_habits(self):
        if not self.habits:
            frappe.throw("At least one habit is required in a Habit Plan.")
        habit_names = [h.habit_name for h in self.habits]
        if len(habit_names) != len(set(habit_names)):
            frappe.throw("Duplicate habit names found in the plan. Each habit must be unique.")

    def validate_unique_plan_name_per_student(self):
        existing = frappe.db.exists(
            "Habit Plan",
            {
                "student": self.student,
                "plan_name": self.plan_name,
                "name": ["!=", self.name]
            }
        )
        if existing:
            frappe.throw(f"You already have a habit plan named '{self.plan_name}'. Please use a unique plan name.")

    def on_submit(self):
        self.status = "Active"
        self.db_set("status", "Active")

    def after_insert(self):
        """Auto-schedule reminders after plan creation."""
        self.schedule_reminders()

    def schedule_reminders(self):
        """Enqueue background job to schedule reminder notifications."""
        frappe.enqueue(
            "nexedu.habits_builder.doctype.habit_plan.habit_plan.send_reminder_setup_notification",
            plan_name=self.name,
            queue="long",
            timeout=300
        )

    @frappe.whitelist()
    def pause_plan(self):
        self.db_set("status", "Paused")
        frappe.msgprint(f"Habit Plan '{self.plan_name}' has been paused.")

    @frappe.whitelist()
    def resume_plan(self):
        self.db_set("status", "Active")
        frappe.msgprint(f"Habit Plan '{self.plan_name}' has been resumed.")

    @frappe.whitelist()
    def complete_plan(self):
        self.db_set("status", "Completed")
        frappe.msgprint(f"Habit Plan '{self.plan_name}' marked as Completed.")

    def get_active_habits(self):
        """Return list of active child habits."""
        return [h for h in self.habits]

    def get_completion_summary(self, days=30):
        """
        Returns a dict with overall completion stats for the last N days.
        {
            "done": int,
            "partial": int,
            "missed": int,
            "total": int,
            "rate": float
        }
        """
        from_date = add_days(today(), -days)
        logs = frappe.get_all(
            "Habit Daily Log",
            filters={
                "student": self.student,
                "log_date": [">=", from_date],
                "habit": ["in", [h.name for h in self.habits]]
            },
            fields=["status"]
        )
        done = sum(1 for l in logs if l.status == "Done")
        partial = sum(1 for l in logs if l.status == "Partial")
        missed = sum(1 for l in logs if l.status == "Skipped")
        total = len(logs)
        rate = round((done / total) * 100, 2) if total else 0.0
        return {
            "done": done,
            "partial": partial,
            "missed": missed,
            "total": total,
            "rate": rate
        }


def send_reminder_setup_notification(plan_name):
    """Background worker: sends a welcome notification for new habit plan."""
    try:
        plan = frappe.get_doc("Habit Plan", plan_name)
        student = frappe.get_doc("Student", plan.student)
        frappe.sendmail(
            recipients=[student.email],
            subject=f"Your Habit Plan '{plan.plan_name}' is now Active!",
            message=f"""
            <p>Hi {student.first_name},</p>
            <p>Your habit plan <strong>{plan.plan_name}</strong> has been created with {len(plan.habits)} habit(s).</p>
            <p>Keep your streak going every day!</p>
            """
        )
    except Exception as e:
        frappe.log_error(f"Reminder notification failed for plan {plan_name}: {str(e)}", "Habit Plan Reminder")