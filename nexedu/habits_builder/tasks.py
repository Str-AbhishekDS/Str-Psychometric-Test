"""
tasks.py — Scheduled background tasks for Habit Builder
"""
from builtins import Exception, len, round, set, str, sum

import frappe
from frappe.utils import today, add_days, getdate

# Confirm this is the correct fieldname on Student doctype - see note below
STUDENT_EMAIL_FIELD = "email_id"  # change to "email_id" if that's the real fieldname


def get_student_user(student):
    """Resolve the User docname (login) linked to a Student record.
    Single source of truth - used by every task in this file."""
    email = frappe.db.get_value("Student", student, STUDENT_EMAIL_FIELD)
    if email and frappe.db.exists("User", email):
        return email
    return None


def send_morning_nudges():
    """
    Daily @ 8 AM: Send a system notification to students who have pending
    habits today and who have not already logged any habits today.
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

        logged_today = frappe.db.count(
            "Habit Daily Log",
            {"student": student, "log_date": today()}
        )
        if logged_today > 0:
            continue

        try:
            student_doc = frappe.get_doc("Student", student)
            student_user = get_student_user(student)
            if not student_user:
                frappe.log_error(f"No user found for Student {student}", "Habit Morning Nudge")
                continue

            pending = frappe.get_all(
                "Habit",
                filters={"parent": plan_ref.name},
                fields=["habit_name", "current_streak"]
            )
            if not pending:
                continue

            send_morning_nudge_notification(student_user, student_doc, plan_ref.name, pending)
            students_nudged.add(student)

        except Exception as e:
            frappe.log_error(f"Morning nudge failed for {student}: {str(e)}", "Habit Morning Nudge")


def send_morning_nudge_notification(student_user, student_doc, plan_name, pending_habits):
    habit_list_html = "".join(
        f"""<li style="margin-bottom:6px;color:#1E293B;font-size:14px;">
                {h.habit_name} <span style="color:#ff6b00;">🔥 {h.current_streak or 0}-day streak</span>
            </li>"""
        for h in pending_habits
    )

    subject = "⏰ Don't break your streak! Habits due today"

    content =f"🌤️ Hi {student_doc.first_name}, you have pending habits to complete today."

    frappe.get_doc({
        "doctype": "Notification Log",
        "subject": subject,
        "email_content": content,
        "for_user": student_user,
        "type": "Alert",
        "document_type": "Habit Plan",
        "document_name": plan_name,
    }).insert(ignore_permissions=True)


def check_broken_streaks():
    """
    Daily: Detect habits where yesterday had no log (streak broken).
    Sends a system notification recovery nudge.
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
                h_doc = frappe.get_doc("Habit", habit_row.name)
                # If not due yesterday, streak is not broken/affected
                if not h_doc.is_due_today(yesterday):
                    continue

                had_log_yesterday = frappe.db.exists(
                    "Habit Daily Log",
                    {"habit": habit_row.name, "student": plan_ref.student, "log_date": yesterday, "status": "Done"}
                )
                if not had_log_yesterday:
                    if h_doc.current_streak > 0:
                        broken_habits.append(habit_row.habit_name)
                        frappe.db.set_value("Habit", habit_row.name, "current_streak", 0)

            if broken_habits:
                student_user = get_student_user(plan_ref.student)
                if not student_user:
                    frappe.log_error(f"No user found for Student {plan_ref.student}", "Habit Streak Check")
                    continue

                student_doc = frappe.get_doc("Student", plan_ref.student)
                send_broken_streak_notification(student_user, student_doc, plan_ref.name, broken_habits)

        except Exception as e:
            frappe.log_error(f"Streak check failed for plan {plan_ref.name}: {str(e)}", "Habit Streak Check")


def send_broken_streak_notification(student_user, student_doc, plan_name, broken_habits):
    habit_list_html = "".join(
        f"""<li style="margin-bottom:6px;color:#1E293B;font-size:14px;">{h}</li>"""
        for h in broken_habits
    )

    subject = "💪 Your streak broke — time to bounce back!"

    content = f"""
<div style="margin:0;padding:0;background:#f6f6f8;font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f6f6f8;padding:20px 10px;">
        <tr>
            <td align="center">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
                    style="max-width:480px;background:#ffffff;border:1px solid #e2e8f0;border-radius:14px;overflow:hidden;">
                    <tr>
                        <td style="background:#dc2626;padding:20px;text-align:center;">
                            <p style="margin:0;color:#ffffff;font-size:18px;font-weight:700;">
                                Streak Broken 💔
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:22px;">
                            <p style="margin:0 0 14px;color:#1E293B;font-size:14px;line-height:1.7;">
                                Hi <strong>{student_doc.first_name}</strong>, you missed these habits yesterday:
                            </p>
                            <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:14px 18px;margin-bottom:16px;">
                                <ul style="margin:0;padding-left:18px;">
                                    {habit_list_html}
                                </ul>
                            </div>
                            <div style="background:#fee2e2;border-left:4px solid #dc2626;padding:12px 14px;border-radius:8px;">
                                <p style="margin:0;color:#7f1d1d;font-size:13px;line-height:1.6;">
                                    That's okay! Start fresh today. Every day is a new opportunity.
                                </p>
                            </div>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</div>
"""

    frappe.get_doc({
        "doctype": "Notification Log",
        "subject": subject,
        "email_content": content,
        "for_user": student_user,
        "type": "Alert",
        "document_type": "Habit Plan",
        "document_name": plan_name,
    }).insert(ignore_permissions=True)


def send_weekly_summary():
    """
    Weekly: Send each student a performance summary of the past 7 days
    as a system notification.
    """
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

            student_user = get_student_user(student)
            if not student_user:
                frappe.log_error(f"No user found for Student {student}", "Habit Weekly Summary")
                continue

            student_doc = frappe.get_doc("Student", student)
            send_weekly_summary_notification(student_user, student_doc, done, total, rate)

        except Exception as e:
            frappe.log_error(f"Weekly summary failed for {row.student}: {str(e)}", "Habit Weekly Summary")


def send_weekly_summary_notification(student_user, student_doc, done, total, rate):
    subject = "📊 Your Weekly Habit Summary"

    content = f"""
<div style="margin:0;padding:0;background:#f6f6f8;font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f6f6f8;padding:20px 10px;">
        <tr>
            <td align="center">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
                    style="max-width:480px;background:#ffffff;border:1px solid #e2e8f0;border-radius:14px;overflow:hidden;">
                    <tr>
                        <td style="background:#0891b2;padding:20px;text-align:center;">
                            <p style="margin:0;color:#ffffff;font-size:18px;font-weight:700;">
                                Weekly Habit Summary 📊
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:22px;">
                            <p style="margin:0 0 14px;color:#1E293B;font-size:14px;line-height:1.7;">
                                Hi <strong>{student_doc.first_name}</strong>, here's your progress this week:
                            </p>
                            <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:14px 18px;margin-bottom:16px;">
                                <table width="100%" style="border-collapse:collapse;">
                                    <tr>
                                        <td style="padding:6px 0;color:#64748B;font-size:14px;"><strong>Logs Completed</strong></td>
                                        <td style="padding:6px 0;color:#1E293B;font-size:14px;text-align:right;">{done}/{total}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding:6px 0;color:#64748B;font-size:14px;"><strong>Completion Rate</strong></td>
                                        <td style="padding:6px 0;color:#0891b2;font-size:14px;font-weight:600;text-align:right;">{rate}%</td>
                                    </tr>
                                </table>
                            </div>
                            <div style="background:#cffafe;border-left:4px solid #0891b2;padding:12px 14px;border-radius:8px;">
                                <p style="margin:0;color:#164e63;font-size:13px;line-height:1.6;">
                                    Keep it up next week!
                                </p>
                            </div>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</div>
"""

    frappe.get_doc({
        "doctype": "Notification Log",
        "subject": subject,
        "email_content": content,
        "for_user": student_user,
        "type": "Alert",
        "document_type": "Habit Plan",
        "document_name": student_user,  # weekly summary has no single plan; using student_user as ref
    }).insert(ignore_permissions=True)


def auto_complete_ended_plans():
    """Mark plans whose end_date has passed as Completed."""
    expired = frappe.get_all(
        "Habit Plan",
        filters={"status": "Active", "end_date": ["<", today()]},
        fields=["name"]
    )
    for p in expired:
        frappe.db.set_value("Habit Plan", p.name, "status", "Completed")
    if expired:
        frappe.db.commit()
        frappe.logger().info(f"Auto-completed {len(expired)} expired habit plans.")


STATUS_STYLE = {
    "accent": "#ff6b00",
    "badge_color": "#ff6b00",
    "badge_bg": "#ffedd5",
}


def check_incomplete_habits():
    """Runs daily. For every Active Habit Plan whose start_date/end_date
    window includes today, checks which habits have NOT been logged as
    'Done' today and sends a system notification to the student."""

    active_plans = frappe.get_all(
        "Habit Plan",
        filters={"status": "Active"},
        fields=["name", "student", "plan_name", "start_date", "end_date"],
    )

    today_date = getdate(today())

    for plan in active_plans:
        if not is_within_date_range(plan.start_date, plan.end_date, today_date):
            continue

        if already_notified_today(plan.name):
            continue

        habit_rows = frappe.get_all(
            "Habit",
            filters={"parent": plan.name},
            fields=["name", "habit_name"],
        )

        if not habit_rows:
            continue

        incomplete_habits = []
        for h in habit_rows:
            h_doc = frappe.get_doc("Habit", h.name)
            if not h_doc.is_due_today(today_date):
                continue

            completed = frappe.db.exists(
                "Habit Daily Log",
                {"student": plan.student, "log_date": today_date, "habit": h.name, "status": "Done"}
            )
            if not completed:
                incomplete_habits.append(h.habit_name)

        if not incomplete_habits:
            continue

        student_user = get_student_user(plan.student)
        if not student_user:
            frappe.log_error(f"No user/email found for Student {plan.student}", "Habit Plan Reminder")
            continue

        send_incomplete_habit_notification(student_user, plan, incomplete_habits)


def is_within_date_range(start_date, end_date, today_date):
    if start_date and getdate(start_date) > today_date:
        return False
    if end_date and getdate(end_date) < today_date:
        return False
    return True


def already_notified_today(plan_name):
    return frappe.db.exists(
        "Notification Log",
        {"document_type": "Habit Plan", "document_name": plan_name, "creation": [">=", today()]},
    )


def send_incomplete_habit_notification(student_user, plan, incomplete_habits):
    habit_list_html = "".join(
        f"""<li style="margin-bottom:6px;color:#1E293B;font-size:14px;">{h}</li>"""
        for h in incomplete_habits
    )

    subject = f"Habits Pending Today — {plan.plan_name}"

    content = f"""
<div style="margin:0;padding:0;background:#f6f6f8;font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f6f6f8;padding:20px 10px;">
        <tr>
            <td align="center">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
                    style="max-width:480px;background:#ffffff;border:1px solid #e2e8f0;border-radius:14px;overflow:hidden;">
                    <tr>
                        <td style="background:{STATUS_STYLE['accent']};padding:20px;text-align:center;">
                            <p style="margin:0;color:#ffffff;font-size:18px;font-weight:700;">
                                Habits Pending Today ⏰
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:22px;">
                            <p style="margin:0 0 14px;color:#1E293B;font-size:14px;line-height:1.7;">
                                You still have <strong>{len(incomplete_habits)}</strong> habit(s) not marked done
                                today for your plan <strong>{plan.plan_name}</strong>:
                            </p>
                            <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:14px 18px;margin-bottom:16px;">
                                <ul style="margin:0;padding-left:18px;">
                                    {habit_list_html}
                                </ul>
                            </div>
                            <div style="background:#fff7ed;border-left:4px solid {STATUS_STYLE['accent']};padding:12px 14px;border-radius:8px;">
                                <p style="margin:0;color:#9a3412;font-size:13px;line-height:1.6;">
                                    Log today's progress before the day ends to keep your streak alive!
                                </p>
                            </div>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</div>
"""

    frappe.get_doc({
        "doctype": "Notification Log",
        "subject": subject,
        "email_content": content,
        "for_user": student_user,
        "type": "Alert",
        "document_type": "Habit Plan",
        "document_name": plan.name,
    }).insert(ignore_permissions=True)