// Copyright (c) 2026, Stride nex and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Habit Daily Log", {
// 	refresh(frm) {

// 	},
// });
frappe.ui.form.on("Habit Daily Log", {

    refresh(frm) {
        if (!frm.is_new()) {
            frm.trigger("set_status_color");
        }
        frm.set_value("logged_at", frappe.datetime.now_datetime());
    },

    set_status_color(frm) {
        const colorMap = { Done: "green", Partial: "orange", Skipped: "red" };
        const color = colorMap[frm.doc.status] || "grey";
        frm.page.set_indicator(frm.doc.status, color);
    },

    status(frm) {
        frm.trigger("set_status_color");
        if (frm.doc.status === "Done") {
            frappe.show_alert({ message: "✅ Great job! Habit marked as Done.", indicator: "green" }, 3);
        }
    },

    habit(frm) {
        if (frm.doc.habit) {
            // Auto-fill student if not set
            if (!frm.doc.student) {
                frappe.session.user && frappe.db.get_value(
                    "Student",
                    { user: frappe.session.user },
                    "name",
                    (r) => r && frm.set_value("student", r.name)
                );
            }
        }
    },

    log_date(frm) {
        if (frm.doc.log_date) {
            const today = frappe.datetime.get_today();
            if (frm.doc.log_date > today) {
                frappe.msgprint(__("Cannot log for a future date."));
                frm.set_value("log_date", today);
            }
        }
    }
});