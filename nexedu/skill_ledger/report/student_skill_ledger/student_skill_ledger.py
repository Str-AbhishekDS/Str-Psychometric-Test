
import frappe

def execute(filters=None):
    filters = filters or {}

    columns = get_columns()
    data = get_data(filters)
    
    for row in data:
        if not row.get("verification_status"):
            row["verification_status"] = "Pending"

    return columns, data


# ✅ Columns
def get_columns():
    return [
        {
            "label": "Student Skill",
            "fieldname": "student_skill",
            "fieldtype": "Link",
            "options": "Student Skill",
            "width": 150,
        },
        {
            "label": "Skill",
            "fieldname": "skill",
            "fieldtype": "Link",
            "options": "Skill",
            "width": 150,
        },
        {
            "label": "Skill Level",
            "fieldname": "skill_level",
            "fieldtype": "Data",
            "width": 120,
        },  
        {
            "label": "Event Type",
            "fieldname": "event_type",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": "Verification Status",
            "fieldname": "verification_status",
            "fieldtype": "Data",
            "width": 140,
        },
        {
            "label": "Event Time",
            "fieldname": "event_time",
            "fieldtype": "Datetime",
            "width": 150,
        },
    ]


# ✅ Data Logic
def get_data(filters):
    conditions = ""
    values = {}

    # Mandatory student filter
    if filters.get("student"):
        conditions += " AND ss.student = %(student)s"
        values["student"] = filters["student"]
    else:
        frappe.throw("Student is required")

    # Optional filters
    if filters.get("skill"):
        conditions += " AND ss.skill = %(skill)s"
        values["skill"] = filters["skill"]

    if filters.get("skill_level"):
        conditions += " AND ss.current_level = %(skill_level)s"
        values["skill_level"] = filters["skill_level"]

    if filters.get("status"):
        conditions += " AND ss.status = %(status)s"
        values["status"] = filters["status"]

    # Event Type filter (from ledger)
    event_condition = ""
    if filters.get("event_type"):
        event_condition = " AND sle.event_type = %(event_type)s"
        values["event_type"] = filters["event_type"]

    # ✅ Main Query (Join Student Skill + Ledger)
    data = frappe.db.sql(f"""
        SELECT
            ss.name AS student_skill,
            ss.skill,
            ss.current_level AS skill_level,
            ss.status,

            -- Hide verification from event type
            CASE 
                WHEN sle.event_type = 'Verification' THEN NULL
                ELSE sle.event_type
            END AS event_type,

            sle.event_time,

            -- Compute verification status
            MAX(CASE 
                WHEN sle.event_type = 'Verification' AND sle.status = 'Verified' THEN 'Verified'
                WHEN sle.event_type = 'Verification' AND sle.status = 'Rejected' THEN 'Rejected'
                ELSE NULL
            END) OVER (PARTITION BY ss.name) AS verification_status

        FROM `tabStudent Skill` ss
        LEFT JOIN `tabStudent Skill Ledger` sle
            ON sle.student_skill = ss.name

        WHERE 1=1
            {conditions}
            {event_condition}

        ORDER BY sle.event_time DESC
    """, values, as_dict=True)

    return data