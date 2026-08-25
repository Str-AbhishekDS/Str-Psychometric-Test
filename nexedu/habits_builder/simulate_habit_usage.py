import frappe
from frappe.utils import getdate, add_days, today
import random
import time

def setup_students():
    print("Setting up 10 test students...")
    student_emails = [f"qa.student.habit_test_{i}@example.com" for i in range(1, 11)]
    for email in student_emails:
        # Check if student already exists
        if not frappe.db.exists("Student", email):
            student = frappe.get_doc({
                "doctype": "Student",
                "name": email,
                "first_name": "Habit",
                "last_name": f"Test {email.split('_')[-1].split('@')[0]}",
                "email_id": email,
                "college": "Tanvi International"
            })
            student.insert(ignore_permissions=True)
            print(f"Created student {email}")
        else:
            print(f"Student {email} already exists")
    frappe.db.commit()
    return student_emails

def clean_old_plans_and_logs(student_emails):
    print("Cleaning up old plans and logs for test students...")
    for student in student_emails:
        # Delete habit daily logs
        frappe.db.delete("Habit Daily Log", {"student": student})
        # Delete habit plans
        plans = frappe.get_all("Habit Plan", filters={"student": student}, fields=["name"])
        for p in plans:
            frappe.delete_doc("Habit Plan", p.name, ignore_permissions=True, force=True)
    frappe.db.commit()

def setup_plans(student_emails):
    print("Creating habit plans for test students...")
    t = today()
    start_date_30_ago = add_days(t, -30)
    end_date_15_ago = add_days(t, -15)
    start_date_10_ago = add_days(t, -10)
    end_date_10_future = add_days(t, 10)
    
    plan_details = []
    
    for student in student_emails:
        # Plan A: Coding (Active)
        plan_a = frappe.get_doc({
            "doctype": "Habit Plan",
            "student": student,
            "plan_name": f"Coding Plan - {student}",
            "start_date": start_date_30_ago,
            "end_date": end_date_10_future,
            "status": "Active",
            "habits": [
                {
                    "habit_name": "Solve Leetcode Easy",
                    "habit_type": "Learning",
                    "frequency": "Daily",
                    "target_duration_min": 30,
                    "doctype": "Habit Plan Item"
                },
                {
                    "habit_name": "Solve Leetcode Medium",
                    "habit_type": "Learning",
                    "frequency": "Daily",
                    "target_duration_min": 45,
                    "doctype": "Habit Plan Item"
                }
            ]
        })
        plan_a.insert(ignore_permissions=True)
        
        # Plan B: ML (Expired/Inactive)
        plan_b = frappe.get_doc({
            "doctype": "Habit Plan",
            "student": student,
            "plan_name": f"ML Study - {student}",
            "start_date": start_date_30_ago,
            "end_date": end_date_15_ago,
            "status": "Active", # Start as Active, will be auto-deactivated
            "habits": [
                {
                    "habit_name": "Read ML Paper",
                    "habit_type": "Learning",
                    "frequency": "Daily",
                    "target_duration_min": 60,
                    "doctype": "Habit Plan Item"
                }
            ]
        })
        plan_b.insert(ignore_permissions=True)
        
        # Plan C: Communication (Active, no end date)
        plan_c = frappe.get_doc({
            "doctype": "Habit Plan",
            "student": student,
            "plan_name": f"Communication Skills - {student}",
            "start_date": start_date_10_ago,
            "end_date": None,
            "status": "Active",
            "habits": [
                {
                    "habit_name": "Practice English Speech",
                    "habit_type": "Networking",
                    "frequency": "Daily",
                    "target_duration_min": 15,
                    "doctype": "Habit Plan Item"
                }
            ]
        })
        plan_c.insert(ignore_permissions=True)
        
        plan_details.append({
            "student": student,
            "plan_a": plan_a,
            "plan_b": plan_b,
            "plan_c": plan_c
        })
        
    frappe.db.commit()
    return plan_details

def seed_daily_logs(plan_details):
    print("Seeding habit daily logs over 30 days...")
    t = today()
    start_date = getdate(add_days(t, -30))
    end_date = getdate(t)
    
    for idx, detail in enumerate(plan_details):
        student = detail["student"]
        student_num = idx + 1
        
        # Fetch actual child habits names (IDs) created in Database
        plan_a_habits = frappe.get_all("Habit", filters={"parent": detail["plan_a"].name}, fields=["name", "habit_name"])
        plan_b_habits = frappe.get_all("Habit", filters={"parent": detail["plan_b"].name}, fields=["name", "habit_name"])
        plan_c_habits = frappe.get_all("Habit", filters={"parent": detail["plan_c"].name}, fields=["name", "habit_name"])
        
        # Map them by habit name
        a_map = {h.habit_name: h.name for h in plan_a_habits}
        b_map = {h.habit_name: h.name for h in plan_b_habits}
        c_map = {h.habit_name: h.name for h in plan_c_habits}
        
        curr = start_date
        while curr <= end_date:
            ds = str(curr)
            
            log_a1 = False
            log_a2 = False
            log_b = False
            log_c = False
            
            if student_num == 1:
                log_a1 = True
                log_a2 = True
                if curr <= getdate(add_days(t, -15)):
                    log_b = True
                if curr >= getdate(add_days(t, -10)):
                    log_c = True
            elif student_num == 2:
                if curr.day % 2 == 0:
                    log_a1 = True
                    log_a2 = True
                    if curr <= getdate(add_days(t, -15)):
                        log_b = True
                    if curr >= getdate(add_days(t, -10)):
                        log_c = True
            elif student_num == 3:
                pass
            elif student_num == 4:
                log_a1 = True
                log_a2 = False
                if curr <= getdate(add_days(t, -15)):
                    log_b = True
                if curr >= getdate(add_days(t, -10)):
                    log_c = True
            elif student_num == 5:
                weekday = curr.weekday()
                if weekday == 0:
                    log_a1 = True
                    log_a2 = True
                    if curr <= getdate(add_days(t, -15)):
                        log_b = True
                    if curr >= getdate(add_days(t, -10)):
                        log_c = True
                elif weekday in (2, 4):
                    log_a1 = True
                    log_a2 = False
                    if curr <= getdate(add_days(t, -15)):
                        log_b = False
                    if curr >= getdate(add_days(t, -10)):
                        log_c = True
            else:
                if random.random() > 0.3:
                    log_a1 = True
                if random.random() > 0.4:
                    log_a2 = True
                if curr <= getdate(add_days(t, -15)) and random.random() > 0.3:
                    log_b = True
                if curr >= getdate(add_days(t, -10)) and random.random() > 0.3:
                    log_c = True
            
            if log_a1 and "Solve Leetcode Easy" in a_map:
                create_log(student, a_map["Solve Leetcode Easy"], ds)
            if log_a2 and "Solve Leetcode Medium" in a_map:
                create_log(student, a_map["Solve Leetcode Medium"], ds)
            if log_b and "Read ML Paper" in b_map:
                create_log(student, b_map["Read ML Paper"], ds)
            if log_c and "Practice English Speech" in c_map:
                create_log(student, c_map["Practice English Speech"], ds)
                
            curr = add_days(curr, 1)
            
    frappe.db.commit()

def create_log(student, habit_id, date_str):
    log = frappe.get_doc({
        "doctype": "Habit Daily Log",
        "student": student,
        "habit": habit_id,
        "log_date": date_str,
        "status": "Done",
        "duration_actual_min": 30,
        "logged_via": "App",
        "logged_at": f"{date_str} 12:00:00"
    })
    log.insert(ignore_permissions=True)

def test_apis(student_emails):
    print("\n--- RUNNING API QA AUDIT ---")
    from nexedu.habits_builder.api import get_student_dashboard, get_student_plans, get_todays_pending_habits
    
    results = {}
    for email in student_emails:
        start_time = time.time()
        dashboard = get_student_dashboard(email)
        duration = time.time() - start_time
        
        plans = get_student_plans(email)
        pending = get_todays_pending_habits(email)
        
        done_30 = dashboard.get("done_30", 0)
        partial_30 = dashboard.get("partial_30", 0)
        missed_30 = dashboard.get("missed_30", 0)
        current_streak = dashboard.get("current_streak", 0)
        longest_streak = dashboard.get("longest_streak", 0)
        
        active_plans = [p for p in plans if p.get("status") == "Active"]
        inactive_plans = [p for p in plans if p.get("status") == "Inactive"]
        
        print(f"Student: {email}")
        print(f"  API Response Time: {duration:.4f}s")
        print(f"  Plans: Active={len(active_plans)}, Inactive={len(inactive_plans)}")
        print(f"  Pending Habits for Today: {len(pending)}")
        print(f"  30-Day Metrics: Done={done_30}, Partial={partial_30}, Missed={missed_30}")
        print(f"  Streaks: Current={current_streak}, Longest={longest_streak}")
        
        results[email] = {
            "duration": duration,
            "done_30": done_30,
            "partial_30": partial_30,
            "missed_30": missed_30,
            "current_streak": current_streak,
            "longest_streak": longest_streak,
            "pending_count": len(pending),
            "plans_count": len(plans)
        }
    return results

def run_simulation():
    student_emails = setup_students()
    clean_old_plans_and_logs(student_emails)
    plan_details = setup_plans(student_emails)
    seed_daily_logs(plan_details)
    results = test_apis(student_emails)
    print("\nSimulation and API validation completed successfully!")

if __name__ == "__main__":
    run_simulation()
