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
                            frm.refresh_field("habits");
                            // frm.trigger("render_streak_summary");
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

     render_streak_summary(frm) {
        if (frm.is_new() || !frm.doc.student) return;
 
        // Remove any previously rendered summary panel
        frm.layout.wrapper.find(".habit-streak-summary").remove();
 
        frappe.call({
            method: "nexedu.habits_builder.api.get_plan_summary",
            args: { plan_name: frm.doc.name },
            callback(r) {
                if (!r.message) return;
 
                const { done, partial, missed, rate, streak, longest_streak } = r.message;
 
                // const html = `
                //     <div class="habit-streak-summary frappe-card"
                //          style="margin:8px 0 16px 0; padding:12px 20px;">
                //         <div style="display:flex; gap:32px; flex-wrap:wrap; align-items:center;">
                //             <div style="text-align:center;">
                //                 <div style="font-size:26px;font-weight:700;color:#ff6b35;">
                //                     🔥 ${streak}
                //                 </div>
                //                 <div style="font-size:11px;color:#888;margin-top:2px;">
                //                     Current Streak
                //                 </div>
                //             </div>
                //             <div style="text-align:center;">
                //                 <div style="font-size:26px;font-weight:700;color:#fd7e14;">
                //                     ${longest_streak}
                //                 </div>
                //                 <div style="font-size:11px;color:#888;margin-top:2px;">
                //                     Longest Streak
                //                 </div>
                //             </div>
                //             <div style="width:1px;background:#eee;height:40px;"></div>
                //             <div style="text-align:center;">
                //                 <div style="font-size:26px;font-weight:700;color:#28a745;">
                //                     ${done}
                //                 </div>
                //                 <div style="font-size:11px;color:#888;margin-top:2px;">
                //                     Done (30d)
                //                 </div>
                //             </div>
                //             <div style="text-align:center;">
                //                 <div style="font-size:26px;font-weight:700;color:#ffa500;">
                //                     ${partial}
                //                 </div>
                //                 <div style="font-size:11px;color:#888;margin-top:2px;">
                //                     Partial (30d)
                //                 </div>
                //             </div>
                //             <div style="text-align:center;">
                //                 <div style="font-size:26px;font-weight:700;color:#dc3545;">
                //                     ${missed}
                //                 </div>
                //                 <div style="font-size:11px;color:#888;margin-top:2px;">
                //                     Missed (30d)
                //                 </div>
                //             </div>
                //             <div style="width:1px;background:#eee;height:40px;"></div>
                //             <div style="text-align:center;">
                //                 <div style="font-size:26px;font-weight:700;color:#007bff;">
                //                     ${rate}%
                //                 </div>
                //                 <div style="font-size:11px;color:#888;margin-top:2px;">
                //                     Completion Rate
                //                 </div>
                //             </div>
                //         </div>
                //     </div>`;
 
                // // Insert after the form's first section (below plan_name field)
                // frm.layout.wrapper.find(".form-page").prepend(html);
            }
        });
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