import frappe
from frappe.model.document import Document
from frappe.utils import today, add_days, getdate
import datetime


class Habit(Document):

    def validate(self):
        if self.frequency == "Custom Days" and not self.custom_days:
            frappe.throw(f"Please specify custom days for habit '{self.habit_name}'.")

    def is_due_today(self):
        day_abbr = getdate(today()).strftime("%a")
        if self.frequency == "Daily":
            return True
        if self.frequency == "Weekdays":
            return day_abbr not in ("Sat", "Sun")
        if self.frequency == "Custom Days" and self.custom_days:
            custom = [d.strip() for d in self.custom_days.split(",")]
            return day_abbr in custom
        return False

    def compute_streak(self, student):
        logs = frappe.get_all(
            "Habit Daily Log",
        
            fields=["log_date"],
            order_by="log_date desc"
        )

        if not logs:
            return 0, int(self.longest_streak or 0)

        # ✅ Fix: keep everything as Python date objects — no string mixing
        done_dates = set(getdate(l.log_date) for l in logs)

        # ── current streak ────────────────────────────────────────────────────
        current_streak = 0
        # start from today and walk backwards
        check_date = getdate(today())

        while True:
            if check_date in done_dates:
                current_streak += 1
                # ✅ Fix: subtract timedelta directly — no add_days string conversion
                check_date = check_date - datetime.timedelta(days=1)
            else:
                # if today itself is not logged yet, also check yesterday
                # so streak isn't broken just because today isn't logged yet
                if current_streak == 0:
                    yesterday = getdate(today()) - datetime.timedelta(days=1)
                    if check_date == getdate(today()) and yesterday in done_dates:
                        check_date = yesterday
                        continue
                break

        # ── longest streak ────────────────────────────────────────────────────
        sorted_dates = sorted(done_dates)   # ascending
        longest = 1
        streak = 1

        for i in range(1, len(sorted_dates)):
            delta = (sorted_dates[i] - sorted_dates[i - 1]).days
            if delta == 1:
                streak += 1
                if streak > longest:
                    longest = streak
            else:
                streak = 1

        prev_longest = int(self.longest_streak or 0)
        return current_streak, max(longest, prev_longest)

    def compute_completion_rate(self, student, days=30):
        from_date = add_days(today(), -days)
        total_due = 0
        current = getdate(from_date)
        end = getdate(today())

        while current <= end:
            day_abbr = current.strftime("%a")
            if self.frequency == "Daily":
                total_due += 1
            elif self.frequency == "Weekdays" and day_abbr not in ("Sat", "Sun"):
                total_due += 1
            elif self.frequency == "Custom Days" and self.custom_days:
                custom = [d.strip() for d in self.custom_days.split(",")]
                if day_abbr in custom:
                    total_due += 1
            current = current + datetime.timedelta(days=1)  # ✅ timedelta not add_days

        if total_due == 0:
            return 0.0

        done_count = frappe.db.count(
            "Habit Daily Log",
            {
                "habit": self.habit_name,
                "student": student,
                "status": "Done",
                "log_date": [">=", from_date]
            }
        )
        return round((done_count / total_due) * 100, 2)

    def refresh_computed_fields(self, student):
        current, longest = self.compute_streak(student)
        rate = self.compute_completion_rate(student)

        # ✅ Critical fix: child rows MUST use frappe.db.set_value
        # self.db_set() does NOT persist for child doctypes — it only updates memory
        frappe.db.set_value("Habit", self.name, {
            "current_streak": current,
            "longest_streak": longest,
            "completion_rate": rate
        }, update_modified=False)
        frappe.db.commit()

        return current, longest, rate