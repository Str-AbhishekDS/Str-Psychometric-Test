frappe.query_reports["Student Skill Ledger"] = {
    filters: [
        {
            fieldname: "student",
            label: "Student",
            fieldtype: "Link",
            options: "Student",
            reqd: 1
        },
        {
            fieldname: "skill",
            label: "Skill",
            fieldtype: "Link",
            options: "Skill"
        },
		{
            fieldname: "skill_level",
            label: "Skill Level",
            fieldtype: "Select",
            options: "Beginner\nIntermediate\nAdvanced\nExpert"
        },
		{
            fieldname: "event_type",
            label: "Event Type",
            fieldtype: "Select",
            options: "\nSelf Declared\nEvidence Added\nVerification\nEndorsement Added\nSkill Level Updated\nAI Assessment"
        },
        {
            fieldname: "status",
            label: "Status",
            fieldtype: "Select",
            options: "\nPending\nVerified\nRejected"
        }
		
    ]
};