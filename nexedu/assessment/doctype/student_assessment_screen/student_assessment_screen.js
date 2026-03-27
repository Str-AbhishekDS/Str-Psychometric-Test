// Copyright (c) 2026, Stride nex and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Student Assessment Screen", {
// 	refresh(frm) {

// 	},
// });
frappe.ui.form.on("Student Assessment Screen", {

    refresh(frm) {
        if (!frm.doc.question_index) {
            frm.set_value("question_index", 0);
        }
    },

    assessment(frm) {
        if (!frm.doc.assessment) return;
        frm.set_value("question_index", 0);

        // Validate schedule before starting
        frappe.call({
            method: "frappe.client.get_value",
            args: {
                doctype: "Assessment",
                filters: { name: frm.doc.assessment },
                fieldname: ["valid_from", "valid_to", "duration_minutes"]
            },
            callback(r) {
                if (!r.message) return;

                const now = new Date();
                const valid_from = new Date(r.message.valid_from);
                const valid_to = new Date(r.message.valid_to);

                if (now < valid_from) {
                    frappe.msgprint("⏳ Assessment has not started yet.");
                    frm.set_value("assessment", "");
                    return;
                }

                if (now > valid_to) {
                    frappe.msgprint("❌ Assessment window has closed.");
                    frm.set_value("assessment", "");
                    return;
                }

                // Start timer
                start_timer(frm, r.message.duration_minutes);

                frm.save().then(() => {
                    load_question(frm);
                });
            }
        });
    },

    next(frm) {
        let qtype = frm.doc.question_type;
        let selected_option = null;

        if (qtype === "Choices") {
            for (let i = 1; i <= 10; i++) {
                if (frm.doc[`is_selected_${i}`]) {
                    selected_option = frm.doc[`field_${i}`];
                }
            }
            if (!selected_option) {
                frappe.msgprint("Please select one option");
                return;
            }
        }

        frm.call("next_question", {
            selected_option: selected_option,
            user_input: frm.doc.user_input,
            open_ended: frm.doc.open_ended
        }).then(r => {
            if (!r.message) return;

            if (r.message.completed) {
                frappe.msgprint("✅ Assessment Completed! Please submit.");
                clear_all(frm);
                frm.set_value("question", "");
                frm.set_value("question_type", "");
                for (let i = 1; i <= 10; i++) {
                    frm.toggle_display(`field_${i}`, false);
                    frm.toggle_display(`is_selected_${i}`, false);
                }
                frm.refresh_fields();
                return;
            }

            clear_all(frm);
            set_question(frm, r.message);
        });
    },

    previous(frm) {
        frm.call("previous_question").then(r => {
            if (!r.message) return;
            set_question(frm, r.message);

            setTimeout(() => {
                let saved = r.message.saved_response;
                if (!saved) return;
                saved = saved.trim();
                for (let i = 1; i <= 10; i++) {
                    let opt = frm.doc[`field_${i}`];
                    frm.set_value(`is_selected_${i}`,
                        opt && opt.trim() === saved ? 1 : 0);
                }
                frm.refresh_fields();
            }, 100);
        });
    }
});

// ── Timer ─────────────────────────────────────────────
let _timer_interval = null;

function start_timer(frm, duration_minutes) {
    if (_timer_interval) clearInterval(_timer_interval);

    let seconds_left = (duration_minutes || 0) * 60;

    _timer_interval = setInterval(() => {
        seconds_left--;
        const m = Math.floor(seconds_left / 60);
        const s = seconds_left % 60;
        frm.set_value("time_remaining",
            `${m}:${s.toString().padStart(2, "0")}`);

        if (seconds_left <= 0) {
            clearInterval(_timer_interval);
            frappe.msgprint("⏰ Time is up! Auto-submitting...");
            frm.savesubmit();
        }
    }, 1000);
}

// ── Question helpers ──────────────────────────────────
function load_question(frm) {
    frm.call("load_question").then(r => {
        if (!r.message) return;
        set_question(frm, r.message);
    });
}

function set_question(frm, data) {
    if (data.options) {
        data.options.forEach((opt, index) => {
            let i = index + 1;
            frm.set_value(`field_${i}`, opt);
            frm.toggle_display(`field_${i}`, true);
            frm.toggle_display(`is_selected_${i}`, true);
        });
    }

    for (let i = (data.options ? data.options.length : 0) + 1; i <= 10; i++) {
        frm.toggle_display(`field_${i}`, false);
        frm.toggle_display(`is_selected_${i}`, false);
    }

    frm.set_value("question", data.question);
    frm.set_value("question_type", data.question_type);
    frm.set_value("no_of_options", data.no_of_options);
    frm.set_value("subject", data.subject);
    frm.refresh_fields();
}

function clear_all(frm) {
    for (let i = 1; i <= 10; i++) {
        frm.set_value(`is_selected_${i}`, 0);
    }
    frm.set_value("user_input", "");
    frm.set_value("open_ended", "");
}

// ── Single select enforcement ─────────────────────────
frappe.ui.form.on("Student Assessment Screen", {
    ...Array.from({ length: 10 }, (_, i) => i + 1).reduce((events, i) => {
        events[`is_selected_${i}`] = function(frm) {
            if (frm.doc[`is_selected_${i}`]) {
                for (let j = 1; j <= 10; j++) {
                    if (j !== i) frm.set_value(`is_selected_${j}`, 0);
                }
            }
        };
        return events;
    }, {})
});