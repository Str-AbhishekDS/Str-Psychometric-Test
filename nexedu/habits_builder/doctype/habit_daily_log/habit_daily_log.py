import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, today, getdate


class HabitDailyLog(Document):

    def before_insert(self):
        self.logged_at = now_datetime()
        if not self.log_date:
            self.log_date = today()

    def validate(self):
        self.validate_no_duplicate()
        self.validate_future_date()

    def validate_no_duplicate(self):
        filters = {
            "habit": self.habit,
            "student": self.student,
            "log_date": self.log_date
        }
        if not self.is_new():
            filters["name"] = ["!=", self.name]

        existing = frappe.db.exists("Habit Daily Log", filters)
        if existing:
            frappe.throw(
                f"A log for habit '{self.habit}' on {self.log_date} already exists for this student."
            )

    def validate_future_date(self):
        if getdate(self.log_date) > getdate(today()):
            frappe.throw("Cannot log habits for a future date.")

    def after_insert(self):
        self.update_habit_streaks()
        self.check_and_send_streak_celebration()

    def on_update(self):
        self.update_habit_streaks()

    def update_habit_streaks(self):
        """Recompute streak and update the exact child row in Habit Plan."""
        try:
            plans = frappe.get_all(
                "Habit Plan",
                filters={"student": self.student, "status": "Active"},
                fields=["name"]
            )

            for plan_ref in plans:
                plan = frappe.get_doc("Habit Plan", plan_ref.name)

                for habit_row in plan.habits:
                    if habit_row.name == self.habit:

                        # 🔁 Recompute using Habit logic
                        habit_doc = frappe.get_doc("Habit", habit_row.name)
                        current, longest, rate = habit_doc.refresh_computed_fields(self.student)

                        # ✅ IMPORTANT: update child row in memory
                        habit_row.current_streak = current
                        habit_row.longest_streak = longest
                        habit_row.completion_rate = rate

                # ✅ Save parent to persist child updates
                plan.save(ignore_permissions=True)

        except Exception as e:
            frappe.log_error(
                f"Failed to update streaks after log {self.name}: {str(e)}",
                "Habit Streak Update"
            )
        
        self.check_and_award_badges()

    def check_and_award_badges(self):
        """Check if the student qualifies for any new streak badges and award them."""
        try:
            from nexedu.habits_builder.api import check_and_award_student_badges
            check_and_award_student_badges(self.student)
        except Exception as e:
            frappe.log_error(
                f"Failed to award streak badges after log {self.name}: {str(e)}",
                "Habit Badge Award Error"
            )

    def check_and_send_streak_celebration(self):
        milestone_days = [7, 14, 21, 30, 60, 90, 180, 365]
        try:
            plans = frappe.get_all(
                "Habit Plan",
                filters={"student": self.student, "status": "Active"},
                fields=["name"]
            )
            for plan_ref in plans:
                plan = frappe.get_doc("Habit Plan", plan_ref.name)
                for habit_row in plan.habits:
                    if habit_row.name == self.habit:
                        streak = habit_row.current_streak or 0
                        if streak in milestone_days:
                            frappe.enqueue(
                                # ✅ Bug 1 fixed: habit_builder not habits_builder
                                "nexedu.habits_builder.doctype.habit_daily_log.habit_daily_log.send_streak_celebration",
                                student=self.student,
                                habit_name=self.habit,
                                streak=streak,
                                queue="short"
                            )
        except Exception:
            pass


def send_streak_celebration(student, habit_name, streak):
    try:
        student_doc = frappe.get_doc("Student", student)
        frappe.sendmail(
            recipients=[student_doc.email_id],
            subject=f"🔥 {streak}-Day Streak on '{habit_name}'!",
            message=f"""
            <p>Hi {student_doc.first_name}!</p>
            <p>You've maintained a <strong>{streak}-day streak</strong> on your habit: <em>{habit_name}</em>!</p>
            <p>Keep up the incredible work. Consistency is the key to mastery.</p>
            """
        )
        frappe.publish_realtime(
            "habit_streak_milestone",
            {
                "message": f"🔥 {streak}-day streak on '{habit_name}'!",
                "streak": streak,
                "habit": habit_nameW
            },
            user=student_doc.email_id
        )
    except Exception as e:
        frappe.log_error(f"Streak celebration failed: {str(e)}", "Habit Streak Celebration")