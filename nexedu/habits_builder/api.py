
"""
habit_builder/api.py
====================
All public (whitelisted) API endpoints consumed by the frontend UI and
any external integrations (WhatsApp bot, voice assistant, etc.).
"""

from datetime import datetime
from datetime import timedelta
import frappe
from frappe import _
from frappe.utils import today, add_days, getdate, now_datetime
timedelta = timedelta

# ---------------------------------------------------------------------------
# 1. DASHBOARD / SUMMARY
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def get_student_dashboard(student: str) -> dict:
    """
    Returns full dashboard data for the Habits page.
    Response shape:
    {
        "current_streak": int,
        "longest_streak": int,
        "last_30_days": [{"date": "YYYY-MM-DD", "status": "done|partial|missed|none"}, ...],
        "this_week": [{"day": "Mon", "progress": 0-100, "status": "done|partial|missed|none"}, ...],
        "done_30": int,
        "partial_30": int,
        "missed_30": int,
        "habits": [...habit plan details...]
    }
    """
    # frappe.has_permission("Habit Plan", throw=True)
    # _check_student_access(student)

    from_date_30 = add_days(today(), -29)

    # All logs for last 30 days
    logs = frappe.get_all(
    "Habit Daily Log",
    filters={"student": student, "log_date": [">=", from_date_30]},
    fields=["log_date", "status", "habit"],
    ignore_permissions=True
)

    # Group logs by date
    log_by_date = {}
    for l in logs:
        ds = str(getdate(l.log_date))
        if ds not in log_by_date:
            log_by_date[ds] = []
        log_by_date[ds].append(l.status)

    # Build 30-day heatmap
    last_30 = []
    for i in range(29, -1, -1):
        d = str(add_days(today(), -i))
        statuses = log_by_date.get(d, [])
        if not statuses:
            cell_status = "none"
        elif all(s == "Done" for s in statuses):
            cell_status = "done"
        elif any(s == "Done" for s in statuses):
            cell_status = "partial"
        else:
            cell_status = "missed"
        last_30.append({"date": d, "status": cell_status})

    done_30 = sum(1 for l in logs if l.status == "Done")
    partial_30 = sum(1 for l in logs if l.status == "Partial")
    missed_30 = sum(1 for l in logs if l.status == "Skipped")

    # This week
    this_week = _get_this_week_progress(student, logs)

    # Current + longest streak (across all active habits)
    current_streak, longest_streak = _get_overall_streaks(student)

    # Active habit plans
    habits_data = _get_active_habits_summary(student)

    return {
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "last_30_days": last_30,
        "this_week": this_week,
        "done_30": done_30,
        "partial_30": partial_30,
        "missed_30": missed_30,
        "habits": habits_data
    }

@frappe.whitelist(allow_guest=True)  
def _get_active_habits_summary(student: str) -> list:
    """Return all active habit plans with their child habit rows for the dashboard."""
    plans = frappe.get_all(
        "Habit Plan",
        filters={"student": student, "status": "Active"},
        fields=["name", "plan_name", "status", "start_date", "end_date", "ai_generated"],
        ignore_permissions=True
    )
    for plan in plans:
        plan["habits"] = frappe.get_all(
            "Habit",
            filters={"parent": plan["name"]},
            fields=[
                "habit_name", "habit_type", "frequency",
                "current_streak", "longest_streak",
                "completion_rate", "reminder_time"
            ]
        )
    return plans


@frappe.whitelist(allow_guest=True)
def get_plan_summary(plan_name: str) -> dict:
    """Returns completion summary for a specific Habit Plan."""
    frappe.has_permission("Habit Plan", throw=True)
    plan = frappe.get_doc("Habit Plan", plan_name)
    summary = plan.get_completion_summary(30)
    streak, longest = _get_overall_streaks(plan.student)
    summary["streak"] = streak
    summary["longest_streak"] = longest
    return summary


# ---------------------------------------------------------------------------
# 2. DAILY LOGGING
# ---------------------------------------------------------------------------

# @frappe.whitelist()
# def log_daily_habits(student: str, logs) -> dict:
#     frappe.has_permission("Habit Daily Log", "create", throw=True)
#     _check_student_access(student)

#     # ✅ Parse JSON if needed
#     if isinstance(logs, str):
#         logs = frappe.parse_json(logs)

#     logged = 0
#     skipped = 0
#     errors = []

#     # ✅ Get all active habit plans for student
#     plan_names = frappe.get_all(
#         "Habit Plan",
#         filters={"student": student},
#         pluck="name"
#     )

#     # ✅ Fetch all habits once (IMPORTANT optimization)
#     habits = frappe.get_all(
#         "Habit",
#         filters={"parent": ["in", plan_names]},
#         fields=["name", "habit_name"]
#     )

#     # ✅ Build lookup maps
#     name_map = {h.name: h.name for h in habits}  # docname → docname
#     label_map = {h.habit_name: h.name for h in habits}  # label → docname

#     for entry in logs:
#         if not isinstance(entry, dict):
#             errors.append({"habit": None, "error": "Invalid log format"})
#             continue

#         habit_input = entry.get("habit")
#         if not habit_input:
#             continue

#         # ✅ Resolve habit (supports both name + label)
#         habit_docname = name_map.get(habit_input) or label_map.get(habit_input)

#         if not habit_docname:
#             errors.append({"habit": habit_input, "error": "Habit not found"})
#             continue

#         # ✅ Check duplicate
#         existing = frappe.db.exists(
#             "Habit Daily Log",
#             {
#                 "habit": habit_docname,
#                 "student": student,
#                 "log_date": today()
#             }
#         )

#         if existing:
#             skipped += 1
#             continue

#         try:
#             doc = frappe.get_doc({
#                 "doctype": "Habit Daily Log",
#                 "habit": habit_docname,  # ✅ always correct now
#                 "student": student,
#                 "log_date": today(),
#                 "status": entry.get("status", "Done"),
#                 "duration_actual_min": entry.get("duration_actual_min"),
#                 "notes": entry.get("notes"),
#                 "logged_via": entry.get("logged_via", "App"),
#                 "logged_at": now_datetime()
#             })
#             doc.insert(ignore_permissions=False)
#             logged += 1

#         except Exception as e:
#             errors.append({
#                 "habit": habit_input,
#                 "error": str(e)
#             })

#     frappe.db.commit()

#     return {
#         "logged": logged,
#         "skipped_duplicates": skipped,
#         "errors": errors
#     }


@frappe.whitelist(allow_guest=True)
def log_daily_habits(student: str, logs) -> dict:
    frappe.has_permission("Habit Daily Log", "create", throw=True)
    _check_student_access(student)
    if isinstance(logs, str):
        logs = frappe.parse_json(logs)

    logged = 0
    skipped = 0
    errors = []
    habits_to_update = set()

    plan_names = frappe.get_all(
        "Habit Plan",
        filters={"student": student},
        pluck="name"
    )

    habits = frappe.get_all(
        "Habit",
        filters={"parent": ["in", plan_names]},
        fields=["name", "habit_name", "frequency", "custom_days", "longest_streak"]
    )

    name_map  = {h.name: h for h in habits}
    label_map = {h.habit_name: h for h in habits}

    for entry in logs:
        if not isinstance(entry, dict):
            errors.append({"habit": None, "error": "Invalid log format"})
            continue

        habit_input = entry.get("habit")
        if not habit_input:
            continue

        habit_obj = name_map.get(habit_input) or label_map.get(habit_input)
        if not habit_obj:
            errors.append({"habit": habit_input, "error": "Habit not found"})
            continue

        existing = frappe.db.exists(
            "Habit Daily Log",
            {
                "habit": habit_obj.name,
                "student": student,
                "log_date": today()
            }
        )

        if existing:
            skipped += 1
            continue

        try:
            doc = frappe.get_doc({
                "doctype": "Habit Daily Log",
                "habit": habit_obj.name,
                "student": student,
                "log_date": today(),
                "status": entry.get("status", "Done"),
                "duration_actual_min": entry.get("duration_actual_min"),
                "notes": entry.get("notes"),
                "logged_via": entry.get("logged_via", "App"),
                "logged_at": now_datetime()
            })
            doc.insert(ignore_permissions=False)
            logged += 1
            habits_to_update.add(habit_obj.name)

        except Exception as e:
            errors.append({"habit": habit_input, "error": str(e)})

    # frappe.db.commit()

    # ── Update streak + completion_rate for each logged habit ──────────────
    for habit_docname in habits_to_update:
        try:
            habit_meta = name_map.get(habit_docname)
            frequency   = habit_meta.frequency if habit_meta else "Daily"
            custom_days = habit_meta.custom_days if habit_meta else ""

            done_logs = frappe.get_all(
                "Habit Daily Log",
                filters={
                    "habit": habit_docname,
                    "student": student,
                    "status": "Done"
                },
                fields=["log_date"],
                order_by="log_date asc"
            )

            # ── Normalize dates ─────────────────────────────────────────
            done_dates = []
            for l in done_logs:
                d = l.log_date
                if hasattr(d, "date"):
                    d = d.date()
                else:
                    d = getdate(d)
                done_dates.append(d)

            done_dates = sorted(set(done_dates))   # ✅ IMPORTANT
            done_date_set = set(done_dates)

            # ── Current streak ─────────────────────────────────────────
            current_streak = 0
            check_date = getdate(today())

            while check_date in done_date_set:
                current_streak += 1
                check_date -= timedelta(days=1)

            # ── Longest streak ─────────────────────────────────────────
            longest = 0
            streak = 0

            for i, d in enumerate(done_dates):
                if i == 0:
                    streak = 1
                else:
                    if (d - done_dates[i - 1]).days == 1:
                        streak += 1
                    else:
                        streak = 1
                longest = max(longest, streak)

            # Preserve previous longest
            prev_longest = int(
                frappe.db.get_value("Habit", habit_docname, "longest_streak") or 0
            )

            final_longest = max(longest, prev_longest)

            # ── Completion rate: Done=100%, Partial=50%, Skipped=0% ────────
            # Fetch all logs (all statuses) for last 30 days
            habit_plan = frappe.db.get_value("Habit", habit_docname, "parent")
            from_date, end_date = frappe.db.get_value(
                "Habit Plan",
                habit_plan,
                ["start_date", "end_date"]
            )

            # Fetch all logs in range
            all_logs = frappe.get_all(
                "Habit Daily Log",
                filters={
                    "habit": habit_docname,
                    "student": student,
                    "log_date": ["between", [from_date, end_date]]
                },
                fields=["log_date", "status"]
            )

            # Convert logs into date-wise map
            log_map = {}
            for log in all_logs:
                log_day = getdate(log.log_date)
                log_map.setdefault(log_day, []).append(log)

            total_due = 0

            cur = getdate(from_date)
            end = getdate(end_date)

            # Prepare custom days list once
            custom_day_list = []
            if custom_days:
                custom_day_list = [d.strip() for d in custom_days.split(",")]

            while cur <= end:
                day_abbr = cur.strftime("%a")

                # DAILY → must have at least 1 log for that day
                if frequency == "Daily":
                    if cur in log_map:
                        total_due += 1

                # WEEKDAYS → only Mon-Fri and must have log
                elif frequency == "Weekdays":
                    if day_abbr not in ("Sat", "Sun") and cur in log_map:
                        total_due += 1

                # CUSTOM DAYS → check allowed days and count ALL logs
                elif frequency == "Custom Days":
                    if day_abbr in custom_day_list and cur in log_map:
                        total_due += len(log_map[cur])

                cur += timedelta(days=1)

            # Score: Done=1.0, Partial=0.5, Skipped=0.0
            score = 0.0
            for log in all_logs:
                if log.status == "Done":
                    score += 1.0
                elif log.status == "Partial":
                    score += 0.5
                # Skipped adds 0

            completion_rate = round((score / total_due) * 100, 2) if total_due else 0.0

            # ── Write all three fields in one db call ──────────────────────
            frappe.db.set_value("Habit", habit_docname, {
                "current_streak":  current_streak,
                "longest_streak":  final_longest,
                "completion_rate": completion_rate
            }, update_modified=False)

        except Exception as e:
            errors.append({
                "habit": habit_docname,
                "error": f"Streak update failed: {str(e)}"
            })

    frappe.db.commit()

    return {
        "logged":             logged,
        "skipped_duplicates": skipped,
        "errors":             errors
    }


@frappe.whitelist(allow_guest=True)
def update_log_status(log_name: str, status: str) -> dict:
    """Update status of an existing Habit Daily Log entry."""
    frappe.has_permission("Habit Daily Log", "write", throw=True)
    valid = ["Done", "Skipped", "Partial"]
    if status not in valid:
        frappe.throw(f"Invalid status. Must be one of: {', '.join(valid)}")
    frappe.db.set_value("Habit Daily Log", log_name, "status", status)
    frappe.db.commit()
    return {"success": True, "log_name": log_name, "new_status": status}


# ---------------------------------------------------------------------------
# 3. HABIT PLAN CRUD
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def create_habit_plan(student: str, plan_name: str, start_date: str,
                      habits: list, linked_path: str = None,
                      end_date: str = None, ai_generated: int = 0) -> dict:
    """
    Create a new Habit Plan with child Habit rows.
    habits: [{"habit_name": str, "habit_type": str, "frequency": str,
               "target_duration_min": int, "reminder_time": "HH:MM:SS",
               "linked_skill": str}]
    """
    frappe.has_permission("Habit Plan", "create", throw=True)
    _check_student_access(student)

    if isinstance(habits, str):
        import json
        habits = json.loads(habits)

    doc = frappe.get_doc({
        "doctype": "Habit Plan",
        "student": student,
        "plan_name": plan_name,
        "start_date": start_date,
        "end_date": end_date or None,
        "linked_path": linked_path,
        "status": "Active",
        "ai_generated": ai_generated,
        "habits": habits
    })
    doc.insert()
    frappe.db.commit()
    return {"plan_name": doc.name, "status": doc.status, "habits_count": len(doc.habits)}


@frappe.whitelist(allow_guest=True)
def get_student_plans(student: str, status: str = None) -> list:
    """Return all Habit Plans for a student, optionally filtered by status."""
    frappe.has_permission("Habit Plan", throw=True)
    _check_student_access(student)

    filters = {"student": student}
    if status:
        filters["status"] = status

    plans = frappe.get_all(
        "Habit Plan",
        filters=filters,
        fields=["name", "plan_name", "status", "start_date", "end_date", "ai_generated"]
    )

    for p in plans:
        p["habits"] = frappe.get_all(
            "Habit",
            filters={"parent": p["name"]},
            fields=["habit_name", "habit_type", "frequency", "current_streak",
                    "longest_streak", "completion_rate", "reminder_time"]
        )
    return plans


# ---------------------------------------------------------------------------
# 4. STREAK & ANALYTICS
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def get_habit_streaks(student: str) -> list:
    """
    Returns streak data for every habit across all active plans.
    [{"habit_name": str, "current_streak": int, "longest_streak": int,
      "completion_rate": float, "habit_type": str}]
    """
    frappe.has_permission("Habit Plan", throw=True)
    _check_student_access(student)

    plans = frappe.get_all(
        "Habit Plan",
        filters={"student": student, "status": "Active"},
        fields=["name"]
    )
    result = []
    for p in plans:
        habits = frappe.get_all(
            "Habit",
            filters={"parent": p.name},
            fields=["habit_name", "habit_type", "current_streak",
                    "longest_streak", "completion_rate"]
        )
        result.extend(habits)
    return result


@frappe.whitelist(allow_guest=True)
def get_habit_history(student: str, habit: str, days: int = 30) -> list:
    """
    Returns daily log history for a specific habit.
    [{"log_date": "YYYY-MM-DD", "status": str, "duration_actual_min": int, "notes": str}]
    """
    frappe.has_permission("Habit Daily Log", throw=True)
    _check_student_access(student)

    from_date = add_days(today(), -int(days))
    return frappe.get_all(
        "Habit Daily Log",
        filters={"student": student, "habit": habit, "log_date": [">=", from_date]},
        fields=["log_date", "status", "duration_actual_min", "notes", "logged_via"],
        order_by="log_date desc"
    )


@frappe.whitelist(allow_guest=True)
def get_todays_pending_habits(student: str) -> list:
    """
    Return habits that are scheduled for today but not yet logged.
    """
    frappe.has_permission("Habit Plan", throw=True)
    _check_student_access(student)

    plans = frappe.get_all(
        "Habit Plan",
        filters={"student": student, "status": "Active"},
        fields=["name"]
    )

    logged_habits = frappe.get_all(
        "Habit Daily Log",
        filters={
            "student": student,
            "log_date": today()
        },
        fields=["habit"]
    )

    already_logged = set()

    for log in logged_habits:

        habit_name = frappe.db.get_value(
            "Habit",
            log.habit,
            "habit_name"
        )

        if habit_name:
            already_logged.add(habit_name)

    pending = []
    for plan_ref in plans:
        plan = frappe.get_doc("Habit Plan", plan_ref.name)
        for row in plan.habits:
            if row.habit_name not in already_logged:
                from nexedu.habits_builder.doctype.habit.habit import Habit as HabitDoc
                h = frappe.get_doc("Habit", row.name)
                if h.is_due_today():
                    pending.append({
                        "habit_name": row.habit_name,
                        "habit_type": row.habit_type,
                        "target_duration_min": row.target_duration_min,
                        "reminder_time": row.reminder_time,
                        "current_streak": row.current_streak,
                        "plan_name": plan.plan_name
                    })
    return pending


# ---------------------------------------------------------------------------
# 5. AI AGENT ENDPOINT
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=False)
def ai_generate_habit_plan(student: str, path_name: str, learning_goal: str) -> dict:
    """
    Trigger AI agent to auto-generate a Habit Plan aligned to the student's path.
    Returns the created plan's name.
    """
    frappe.has_permission("Habit Plan", "create", throw=True)
    _check_student_access(student)

    # Enqueue the AI generation task (long-running)
    job = frappe.enqueue(
        "habit_builder.agents.habit_agent.generate_plan_for_student",
        student=student,
        path_name=path_name,
        learning_goal=learning_goal,
        queue="long",
        timeout=600
    )
    return {"status": "queued", "job_id": str(job.id) if job else None}


# ---------------------------------------------------------------------------
# INTERNAL HELPERS
# ---------------------------------------------------------------------------

def _check_student_access(student: str):
    """Ensure the logged-in user can access data for this student."""
    
    if frappe.session.user == "Administrator":
        return

    linked_user = frappe.db.get_value("Student", student, "email_id")

    if linked_user and linked_user != frappe.session.user:
        frappe.throw(_("Access denied."), frappe.PermissionError)


def _get_overall_streaks(student: str):
    """Compute max current streak and max longest streak across all active habits."""
    plans = frappe.get_all(
        "Habit Plan",
        filters={"student": student, "status": "Active"},
        fields=["name"]
    )
    max_current = 0
    max_longest = 0
    for p in plans:
        rows = frappe.get_all(
            "Habit",
            filters={"parent": p.name},
            fields=["current_streak", "longest_streak"]
        )
        for r in rows:
            max_current = max(max_current, r.current_streak or 0)
            max_longest = max(max_longest, r.longest_streak or 0)
    return max_current, max_longest


def _get_this_week_progress(student: str, logs: list) -> list:
    """Build this-week progress list with day labels."""
    days_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    today_date = getdate(today())
    # Find Monday of current week
    monday = today_date - timedelta(days=today_date.weekday())

    log_by_date = {}
    for l in logs:
        ds = str(getdate(l.log_date))
        if ds not in log_by_date:
            log_by_date[ds] = []
        log_by_date[ds].append(l.status)

    week = []
    for i, day_name in enumerate(days_order):
        d = str(monday + timedelta(days=i))
        statuses = log_by_date.get(d, [])
        if not statuses:
            cell_status = "none"
        elif all(s == "Done" for s in statuses):
            cell_status = "done"
        elif any(s == "Done" for s in statuses):
            cell_status = "partial"
        else:
            cell_status = "missed"
        total = len(statuses)
        done = sum(1 for s in statuses if s == "Done")
        progress = round((done / total) * 100) if total else 0
        week.append({"day": day_name, "date": d, "status": cell_status, "progress": progress})
    return week

@frappe.whitelist(allow_guest=True)
def get_student_habit_names(student: str) -> list:
    """
    Returns a flat list of habit_name strings from all active Habit Plans
    for a student. Used by Habit Daily Log form to filter the habit Link field
    so students can only select their own habits.
    """
    _check_student_access(student)

    plans = frappe.get_all(
        "Habit Plan",
        filters={"student": student, "status": "Active"},
        fields=["name"]
    )

    habit_names = []
    for plan in plans:
        rows = frappe.db.get_all(
            "Habit",
            filters={"parent": plan.name, "parenttype": "Habit Plan"},
            fields=["habit_name"]
        )
        habit_names.extend([r.habit_name for r in rows])

    return list(set(habit_names))   # deduplicate in case same habit name in multiple plans


@frappe.whitelist(allow_guest=True)
def complete_habit_plan_status(plan_name: str, habit_name: str, student: str):

    # Check Habit Plan exists
    habit_plan_name = frappe.db.get_value(
        "Habit Plan",
        {
            "plan_name": plan_name,
            "student": student
        },
        "name"
    )

    if not habit_plan_name:
        return {
            "status": "error",
            "message": "Habit Plan not found"
        }

    # Get Habit Plan document
    plan = frappe.get_doc("Habit Plan", habit_plan_name)

    # Find Habit document name using habit_name field
    # because Habit DocType uses naming series
    habit_doc_name = frappe.db.get_value(
        "Habit",
        {
            "habit_name": habit_name
        },
        "name"
    )

    if not habit_doc_name:
        return {
            "status": "error",
            "message": f"Habit not found for habit_name: {habit_name}"
        }

    # Check habit exists in child table
    selected_habit = None

    for row in plan.habits:

        # row.habit stores linked Habit document name
        if row.habit_name == habit_name:
            selected_habit = row
            break

    if not selected_habit:
        return {
            "status": "error",
            "message": "Habit not found in Habit Plan"
        }

    # Create Habit Daily Log
    log = frappe.get_doc({
        "doctype": "Habit Daily Log",
        "habit": habit_doc_name,
        "student": student,
        "habit_plan": plan.name,
        "log_date": today(),
        "status": "Done"
    })

    log.insert(ignore_permissions=True)

    frappe.db.commit()

    return {
        "status": "success",
        "message": "Habit Daily Log created successfully",
        "log_name": log.name
    }