"""
tasks.py — Scheduled background tasks for Habit Builder
"""

import frappe
from frappe.utils import today, add_days, getdate, now_datetime


def send_morning_nudges():
    """
    Daily @ 8 AM: Send a nudge to students who have pending habits today
    and who have not already logged any habits today.
    """
    active_plans = frappe.get_all(
        "Habit Plan",
        filters={"status": "Active"},
        fields=["name", "student"]
    )

    students_nudged = set()

    for plan_ref in active_plans:
        student = plan_ref.student
        if student in students_nudged:
            continue

        # Check if student has any log today
        logged_today = frappe.db.count(
            "Habit Daily Log",
            {"student": student, "log_date": today()}
        )
        if logged_today > 0:
            continue

        try:
            student_doc = frappe.get_doc("Student", student)
            pending = frappe.get_all(
                "Habit",
                filters={"parent": plan_ref.name},
                fields=["habit_name", "current_streak"]
            )
            if not pending:
                continue

            habit_lines = "".join(
                f"<li>{h.habit_name} (🔥 {h.current_streak or 0}-day streak)</li>"
                for h in pending
            )

            frappe.sendmail(
                recipients=[student_doc.email],
                subject="⏰ Don't break your streak! Habits due today",
                message=f"""
                <p>Hi {student_doc.first_name}!</p>
                <p>You have habits due today:</p>
                <ul>{habit_lines}</ul>
                <p>Log them now to keep your streak alive!</p>
                """
            )
            students_nudged.add(student)
        except Exception as e:
            frappe.log_error(f"Morning nudge failed for {student}: {str(e)}", "Habit Morning Nudge")


def check_broken_streaks():
    """
    Daily: Detect habits where yesterday had no log (streak broken).
    Sends a gentle recovery nudge.
    """
    yesterday = add_days(today(), -1)

    active_plans = frappe.get_all(
        "Habit Plan",
        filters={"status": "Active"},
        fields=["name", "student"]
    )

    for plan_ref in active_plans:
        try:
            plan = frappe.get_doc("Habit Plan", plan_ref.name)
            broken_habits = []

            for habit_row in plan.habits:
                had_log_yesterday = frappe.db.exists(
                    "Habit Daily Log",
                    {
                        "habit": habit_row.habit_name,
                        "student": plan_ref.student,
                        "log_date": yesterday
                    }
                )
                had_log_day_before = frappe.db.exists(
                    "Habit Daily Log",
                    {
                        "habit": habit_row.habit_name,
                        "student": plan_ref.student,
                        "log_date": add_days(yesterday, -1)
                    }
                )
                # Was active before yesterday but skipped yesterday
                if had_log_day_before and not had_log_yesterday:
                    broken_habits.append(habit_row.habit_name)
                    # Reset streak
                    frappe.db.set_value("Habit", habit_row.name, "current_streak", 0)

            if broken_habits:
                student_doc = frappe.get_doc("Student", plan_ref.student)
                habit_list = ", ".join(broken_habits)
                frappe.sendmail(
                    recipients=[student_doc.email],
                    subject="💪 Your streak broke — time to bounce back!",
                    message=f"""
                    <p>Hi {student_doc.first_name},</p>
                    <p>You missed these habits yesterday: <strong>{habit_list}</strong></p>
                    <p>That's okay! Start fresh today. Every day is a new opportunity.</p>
                    """
                )
        except Exception as e:
            frappe.log_error(
                f"Streak check failed for plan {plan_ref.name}: {str(e)}",
                "Habit Streak Check"
            )


def send_evening_checkin():
    """
    Daily @ 8 PM: Remind students who haven't fully logged today's habits.
    """
    active_plans = frappe.get_all(
        "Habit Plan",
        filters={"status": "Active"},
        fields=["name", "student"]
    )

    for plan_ref in active_plans:
        try:
            student = plan_ref.student
            plan = frappe.get_doc("Habit Plan", plan_ref.name)
            total_habits = len(plan.habits)
            logged_today = frappe.db.count(
                "Habit Daily Log",
                {"student": student, "log_date": today()}
            )
            if logged_today < total_habits:
                student_doc = frappe.get_doc("Student", student)
                remaining = total_habits - logged_today
                frappe.sendmail(
                    recipients=[student_doc.email],
                    subject=f"🌙 {remaining} habit(s) left to log today!",
                    message=f"""
                    <p>Hi {student_doc.first_name},</p>
                    <p>You still have <strong>{remaining} habit(s)</strong> to log for today.</p>
                    <p>Don't let the day end without completing them!</p>
                    """
                )
        except Exception as e:
            frappe.log_error(
                f"Evening checkin failed for {plan_ref.student}: {str(e)}",
                "Habit Evening Checkin"
            )


def send_weekly_summary():
    """
    Weekly: Send each student a performance summary of the past 7 days.
    """
    from frappe.utils import add_days

    active_students = frappe.get_all(
        "Habit Plan",
        filters={"status": "Active"},
        fields=["student"],
        group_by="student"
    )

    for row in active_students:
        try:
            student = row.student
            from_date = add_days(today(), -6)
            logs = frappe.get_all(
                "Habit Daily Log",
                filters={"student": student, "log_date": [">=", from_date]},
                fields=["status"]
            )
            done = sum(1 for l in logs if l.status == "Done")
            total = len(logs)
            rate = round((done / total) * 100) if total else 0

            student_doc = frappe.get_doc("Student", student)
            frappe.sendmail(
                recipients=[student_doc.email],
                subject="📊 Your Weekly Habit Summary",
                message=f"""
                <p>Hi {student_doc.first_name}!</p>
                <p>This week you completed <strong>{done}/{total}</strong> habit logs
                   — that's a <strong>{rate}%</strong> completion rate.</p>
                <p>Keep it up next week!</p>
                """
            )
        except Exception as e:
            frappe.log_error(
                f"Weekly summary failed for {row.student}: {str(e)}",
                "Habit Weekly Summary"
            )


def auto_complete_ended_plans():
    """Mark plans whose end_date has passed as Completed."""
    expired = frappe.get_all(
        "Habit Plan",
        filters={
            "status": "Active",
            "end_date": ["<", today()]
        },
        fields=["name"]
    )
    for p in expired:
        frappe.db.set_value("Habit Plan", p.name, "status", "Completed")
    if expired:
        frappe.db.commit()
        frappe.logger().info(f"Auto-completed {len(expired)} expired habit plans.")