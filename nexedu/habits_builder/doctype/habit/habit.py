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

    def _is_scheduled_day(self, date):
        """Check if a given date is a scheduled day for this habit."""
        day_abbr = date.strftime("%a")
        if self.frequency == "Daily":
            return True
        if self.frequency == "Weekdays":
            return day_abbr not in ("Sat", "Sun")
        if self.frequency == "Custom Days" and self.custom_days:
            custom = [d.strip() for d in self.custom_days.split(",")]
            return day_abbr in custom
        return False

    def compute_streak(self, student):
        """
        Compute current and longest streak respecting habit frequency.
        Skips non-scheduled days so Weekdays habits don't break on weekends.
        """
        # ✅ Bug 2 fixed: use self.habit_name not self.habit
        logs = frappe.get_all(
            "Habit Daily Log",
            filters={
                "habit": self.habit_name,
                "student": student,
                "status": "Done"
            },
            fields=["log_date"],
            order_by="log_date desc"
        )

        if not logs:
            return 0, self.longest_streak or 0

        done_dates = set(getdate(l.log_date) for l in logs)

        # ✅ Bug 3 fixed: walk back skipping non-scheduled days
        current_streak = 0
        check_date = getdate(today())

        while True:
            if not self._is_scheduled_day(check_date):
                # not a scheduled day — skip it without breaking streak
                check_date = getdate(add_days(check_date, -1))
                continue
            if check_date in done_dates:
                current_streak += 1
                check_date = getdate(add_days(check_date, -1))
            else:
                break

        # Longest streak — walk all done dates in ascending order
        sorted_dates = sorted(done_dates)
        longest = 0
        streak = 1

        for i in range(1, len(sorted_dates)):
            prev = sorted_dates[i - 1]
            curr = sorted_dates[i]
            # Walk day by day from prev to curr, count scheduled days in between
            gap = (curr - prev).days
            # Check if all scheduled days between prev and curr are consecutive
            all_covered = True
            check = prev + datetime.timedelta(days=1)
            while check < curr:
                if self._is_scheduled_day(check) and check not in done_dates:
                    all_covered = False
                    break
                check += datetime.timedelta(days=1)

            if all_covered:
                streak += 1
                longest = max(longest, streak)
            else:
                streak = 1

        longest = max(longest, streak)
        return current_streak, max(longest, self.longest_streak or 0)

    def compute_completion_rate(self, student, days=30):
        """Return 30-day rolling completion rate as a percentage."""
        from_date = add_days(today(), -days)
        total_due = 0
        current = getdate(from_date)
        end = getdate(today())

        while current <= end:
            if self._is_scheduled_day(current):
                total_due += 1
            current = getdate(add_days(current, 1))

        if total_due == 0:
            return 0.0

        done_count = frappe.db.count(
            "Habit Daily Log",
            {
                "habit": self.habit_name,  # ✅ consistent fix
                "student": student,
                "status": "Done",
                "log_date": [">=", from_date]
            }
        )
        return round((done_count / total_due) * 100, 2)

    def refresh_computed_fields(self, student):
        """Recompute and persist streak + rate fields using direct DB update."""
        current, longest = self.compute_streak(student)
        rate = self.compute_completion_rate(student)

        # ✅ Child rows need frappe.db.set_value — db_set doesn't persist for child doctypes
        frappe.db.set_value("Habit", self.name, {
            "current_streak": current,
            "longest_streak": longest,
            "completion_rate": rate
        })
        frappe.db.commit()

        return current, longest, rate