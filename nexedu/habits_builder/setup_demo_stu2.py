import os
import datetime
import frappe
from frappe.utils import getdate, today, add_days

def setup_demo():
    print("Initializing site...")
    frappe.init(site="devstridenex.quantcloud.in", sites_path="sites")
    frappe.connect()

    student = "stu2@gmail.com"
    print(f"Target student: {student}")

    # 1. Update the Habit Plan dates, status and ensure habits are present
    plan_name = "Daily Coding-94376"
    if not frappe.db.exists("Habit Plan", plan_name):
        print(f"Error: Habit Plan {plan_name} does not exist.")
        return

    plan_doc = frappe.get_doc("Habit Plan", plan_name)
    
    # Calculate start and end date relative to current time to ensure plan encompasses the range
    plan_doc.start_date = getdate(add_days(today(), -45))
    plan_doc.end_date = getdate(add_days(today(), 30))
    plan_doc.status = "Active"

    # Re-populate habits if they were cleared/deleted
    if not plan_doc.habits:
        print("Habits list was empty. Re-populating 'Project Building' and 'Leetcode Problem Solving'...")
        plan_doc.append("habits", {
            "habit_name": "Project Building",
            "habit_type": "Learning",
            "frequency": "Daily",
            "target_duration_min": 30,
        })
        plan_doc.append("habits", {
            "habit_name": "Leetcode Problem Solving",
            "habit_type": "Learning",
            "frequency": "Daily",
            "target_duration_min": 45,
        })
    
    plan_doc.save(ignore_permissions=True)
    print(f"Updated Habit Plan {plan_name} start_date to {plan_doc.start_date} and end_date to {plan_doc.end_date}")

    # 2. Clear old logs and earned badges for this student
    print("Clearing old Habit Daily Logs...")
    frappe.db.delete("Habit Daily Log", {"student": student})

    print("Clearing old Student Earned Badges...")
    frappe.db.delete("Student Earned Badge", {"student": student})

    # 3. Fetch habits in this plan
    habits = frappe.get_all("Habit", filters={"parent": plan_name}, fields=["name", "habit_name"])
    print(f"Found habits in DB: {[h.habit_name for h in habits]}")

    leetcode_habit = next((h for h in habits if "Leetcode" in h.habit_name), None)
    project_habit = next((h for h in habits if "Project" in h.habit_name), None)

    if not leetcode_habit or not project_habit:
        print("Error: Could not retrieve habits after plan save.")
        return

    # 4. Generate logs for the past 29 days (ending yesterday)
    end_date = getdate(add_days(today(), -1))
    start_date = getdate(add_days(end_date, -28))

    current_date = start_date
    logs_created = 0

    while current_date <= end_date:
        ds = str(current_date)
        
        # Leetcode habit: Completed every day to maintain the 29-day streak
        log_lc = frappe.get_doc({
            "doctype": "Habit Daily Log",
            "student": student,
            "habit": leetcode_habit.name,
            "log_date": ds,
            "status": "Done",
            "duration_actual_min": 45,
            "logged_via": "App",
            "logged_at": f"{ds} 12:00:00"
        })
        log_lc.insert(ignore_permissions=True)
        logs_created += 1

        # Project Building habit: Completed only on some days (e.g. alternate days)
        # On other days, it is marked as "Skipped" to show a partial completion
        if current_date.day % 2 == 0:
            log_proj = frappe.get_doc({
                "doctype": "Habit Daily Log",
                "student": student,
                "habit": project_habit.name,
                "log_date": ds,
                "status": "Done",
                "duration_actual_min": 30,
                "logged_via": "App",
                "logged_at": f"{ds} 15:00:00"
            })
            log_proj.insert(ignore_permissions=True)
            logs_created += 1
        else:
            log_proj = frappe.get_doc({
                "doctype": "Habit Daily Log",
                "student": student,
                "habit": project_habit.name,
                "log_date": ds,
                "status": "Skipped",
                "duration_actual_min": 0,
                "logged_via": "App",
                "logged_at": f"{ds} 15:00:00"
            })
            log_proj.insert(ignore_permissions=True)
            logs_created += 1

        current_date = current_date + datetime.timedelta(days=1)

    print(f"Created {logs_created} logs from {start_date} to {end_date}.")

    # 5. Refresh computed fields to update streaks
    print("Recalculating computed fields...")
    for h in habits:
        habit_doc = frappe.get_doc("Habit", h.name)
        # Reset longest streak to 29 for Leetcode and 1 for Project Building to ensure fresh state
        if "Leetcode" in h.habit_name:
            frappe.db.set_value("Habit", h.name, "longest_streak", 29, update_modified=False)
        else:
            frappe.db.set_value("Habit", h.name, "longest_streak", 1, update_modified=False)
        
        current_streak, longest_streak, rate = habit_doc.refresh_computed_fields(student)
        print(f"Habit {h.habit_name}: current_streak={current_streak}, longest_streak={longest_streak}, rate={rate}%")

    # 6. Auto-award qualifying badges (7-day and 14-day)
    print("Awarding streak badges...")
    from nexedu.habits_builder.api import check_and_award_student_badges
    check_and_award_student_badges(student)

    earned = frappe.get_all("Student Earned Badge", filters={"student": student}, fields=["badge"])
    print(f"Earned badges now: {[e.badge for e in earned]}")

    frappe.db.commit()
    print("Demo setup completed successfully!")

if __name__ == "__main__":
    setup_demo()
