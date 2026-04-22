// Copyright (c) 2026, Stride nex and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Habit Plan", {
// 	refresh(frm) {

// 	},
// });
frappe.ui.form.on("Habit Plan", {

    refresh(frm) {
        frm.trigger("set_status_indicators");
        frm.trigger("add_custom_buttons");
        frm.trigger("render_streak_summary");
    },

    // set_status_indicators(frm) {
    //     const colorMap = {
    //         "Active":    "green",
    //         "Paused":    "orange",
    //         "Completed": "blue"
    //     };
    //     frm.set_indicator_formatter(
    //         "plan_name",
    //         () => {
    //             if (!frm.doc.plan_name) return "grey";
    //             return colorMap[frm.doc.status] || "grey";
    //         }
    //     );
    // },

    add_custom_buttons(frm) {
        if (frm.doc.docstatus === 0 && !frm.is_new()) {
            if (frm.doc.status === "Active") {
                frm.add_custom_button(__("Pause Plan"), () => {
                    frappe.confirm(
                        __("Are you sure you want to pause this habit plan?"),
                        () => frm.call("pause_plan").then(() => frm.reload_doc())
                    );
                }, __("Actions"));

                frm.add_custom_button(__("Complete Plan"), () => {
                    frappe.confirm(
                        __("Mark this plan as completed?"),
                        () => frm.call("complete_plan").then(() => frm.reload_doc())
                    );
                }, __("Actions"));
            }

            if (frm.doc.status === "Paused") {
                frm.add_custom_button(__("Resume Plan"), () => {
                    frm.call("resume_plan").then(() => frm.reload_doc());
                }, __("Actions"));
            }

            frm.add_custom_button(__("View Habit Logs"), () => {
                frappe.set_route("List", "Habit Daily Log", {
                    student: frm.doc.student
                });
            });

            frm.add_custom_button(__("Log Today's Habits"), () => {
                frm.trigger("open_daily_log_dialog");
            }, __("Quick Actions"));
        }
    },

    open_daily_log_dialog(frm) {
        if (!frm.doc.habits || frm.doc.habits.length === 0) {
            frappe.msgprint(__("No habits found in this plan."));
            return;
        }

        const fields = frm.doc.habits.map(habit => ({
            fieldtype: "Select",
            fieldname: `status_${habit.name}`,
            label: habit.habit_name,
            options: "Done\nPartial\nSkipped",
            default: "Done"
        }));

        const d = new frappe.ui.Dialog({
            title: __("Log Today's Habits"),
            fields: fields,
            primary_action_label: __("Submit Logs"),
            primary_action(values) {

                const logs = frm.doc.habits.map(habit => ({
                    habit: habit.habit_name,
                    status: values[`status_${habit.name}`] || "Done"
                }));

                // console.log("Logs being sent:", logs); // ✅ debug check

                frappe.call({
                    method: "nexedu.habits_builder.api.log_daily_habits",
                    args: {
                        student: frm.doc.student,
                        logs: JSON.stringify(logs)   // ✅ FIX: send as array, NOT string
                    },
                    freeze: true,
                    freeze_message: __("Logging habits..."),
                    callback(r) {
                        if (!r.exc) {
                            const { logged, skipped_duplicates } = r.message;

                            frappe.show_alert({
                                message: __(`✅ ${logged} logged, ${skipped_duplicates} already done today.`),
                                indicator: "green"
                            }, 4);

                            d.hide();
                            frm.trigger("render_streak_summary");
                        }
                    }
                });
            }
        });

        d.show();
    },


    status(frm) {
        frm.trigger("set_status_indicators");
    },

    end_date(frm) {
        if (frm.doc.end_date && frm.doc.start_date) {
            if (frappe.datetime.str_to_obj(frm.doc.end_date) < frappe.datetime.str_to_obj(frm.doc.start_date)) {
                frappe.msgprint(__("End Date cannot be before Start Date."));
                frm.set_value("end_date", "");
            }
        }
    }
});