// Copyright (c) 2026, Stride nex and contributors
// For license information, please see license.txt
//
// career_path.js
//
// FIX LOG
// ───────
// v2 fixes:
//   - set_query child table fieldname corrected to "path_milestone"
//     (was "milestones" — caused cascade filters to silently not apply)
//   - Path Milestone child row event fieldname also corrected to "path_milestone"
// ─────────────────────────────────────────────────────────────────────────────

frappe.ui.form.on("Career Path", {

    setup(frm) {
        // ✅ FIX: fieldname is "path_milestone" from Career Path JSON schema

        frm.set_query("topic", "path_milestone", function(doc, cdt, cdn) {
            const row = locals[cdt][cdn];
            return { filters: { category: row.category } };
        });

        frm.set_query("subtopic", "path_milestone", function(doc, cdt, cdn) {
            const row = locals[cdt][cdn];
            return { filters: { topic: row.topic } };
        });

        frm.set_query("skill", "path_milestone", function(doc, cdt, cdn) {
            const row = locals[cdt][cdn];
            return {
                filters: {
                    topic   : row.topic,
                    subtopic: row.subtopic,
                },
            };
        });
    },

    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__("Enroll a Student"), () => {
                _show_enroll_dialog(frm);
            }, __("Actions"));
        }
    },
});


// ✅ FIX: child table event registrations also use "path_milestone"
frappe.ui.form.on("Path Milestone", {

    category(frm, cdt, cdn) {
        const row    = locals[cdt][cdn];
        row.topic    = null;
        row.subtopic = null;
        row.skill    = null;
        frm.refresh_field("path_milestone");
    },

    topic(frm, cdt, cdn) {
        const row    = locals[cdt][cdn];
        row.subtopic = null;
        row.skill    = null;
        frm.refresh_field("path_milestone");
    },

    subtopic(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        row.skill = null;
        frm.refresh_field("path_milestone");
    },
});


// ─────────────────────────────────────────────────────────────────────────────
// ENROLL A STUDENT — quick dialog from Career Path form
// ─────────────────────────────────────────────────────────────────────────────

function _show_enroll_dialog(frm) {
    const dialog = new frappe.ui.Dialog({
        title : `Enroll Student in: ${frm.doc.path_name}`,
        fields: [
            {
                label    : "Student",
                fieldname: "student",
                fieldtype: "Link",
                options  : "Student Profile",
                reqd     : 1,
                onchange() {
                    const student = dialog.get_value("student");
                    if (!student) return;
                    _live_prereq_check(dialog, student, frm.doc.name);
                },
            },
            {
                fieldtype: "HTML",
                fieldname: "prereq_result_html",
                options  : `<div id="prereq-live-result"
                                 style="padding:4px 0; color:#8c8c8c; font-size:12px;">
                                Select a student to check prerequisites.
                            </div>`,
            },
        ],
        primary_action_label: "Check & Enroll",
        primary_action(values) {
            dialog.hide();
            frappe.call({
                method  : "nexedu.path_finder.api.enrollment_api.check_prerequisite_skills",
                args    : { student: values.student, career_path: frm.doc.name },
                callback(r) {
                    if (!r.message) return;
                    if (r.message.status === "clear") {
                        _do_direct_enroll(values.student, frm.doc.name);
                    } else {
                        // Open enrollment form pre-filled so gap dialog triggers
                        frappe.new_doc("Student Path Enrollment", {
                            student    : values.student,
                            career_path: frm.doc.name,
                        });
                    }
                },
            });
        },
    });

    dialog.show();
}

function _live_prereq_check(dialog, student, career_path) {
    frappe.call({
        method  : "nexedu.path_finder.api.enrollment_api.check_prerequisite_skills",
        args    : { student, career_path },
        callback(r) {
            if (!r.message) return;
            const result = r.message;
            const $div   = dialog.$wrapper.find("#prereq-live-result");

            if (result.status === "clear") {
                $div.html(`<div style="color:#52c41a; font-weight:600;">
                    ✅ All prerequisites met (${result.readiness_percent}%)</div>`);
            } else {
                const bar_color = result.readiness_percent >= 75 ? "#52c41a"
                                : result.readiness_percent >= 50 ? "#fa8c16"
                                :                                  "#ff4d4f";
                $div.html(`
                    <div>
                        <span style="color:${bar_color}; font-weight:600;">
                            ⚠️ Readiness: ${result.readiness_percent}%
                            (${result.matched}/${result.total_prerequisites} skills matched)
                        </span>
                        <div style="background:#e0e0e0; border-radius:6px; height:8px; margin-top:4px;">
                            <div style="width:${result.readiness_percent}%; background:${bar_color};
                                        height:8px; border-radius:6px;"></div>
                        </div>
                        <div style="margin-top:4px; font-size:11px; color:#8c8c8c;">
                            Missing: ${(result.missing_skills || []).map(s => s.skill).join(", ") || "None"}
                        </div>
                    </div>`);
            }
        },
    });
}

function _do_direct_enroll(student, career_path) {
    frappe.call({
        method        : "nexedu.path_finder.api.enrollment_api.enroll_student",
        args          : { student, career_path, force_enroll: 0, prereq_paths: "[]" },
        freeze        : true,
        freeze_message: "Setting up your learning path…",
        callback(r) {
            if (r.message && r.message.status === "success") {
                frappe.show_alert({ message: "✅ Enrolled successfully!", indicator: "green" });
                frappe.set_route("Form", "Student Path Enrollment", r.message.enrollment);
            }
        },
    });
}