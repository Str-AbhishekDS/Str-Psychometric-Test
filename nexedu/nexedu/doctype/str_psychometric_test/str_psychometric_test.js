// Copyright (c) 2026, Stride nex and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Str Psychometric Test", {
// 	refresh(frm) {

// 	},
// });

frappe.msgprint("JS Loaded");
frappe.ui.form.on('Str Psychometric Test Subject Detail', {

    subject: function(frm, cdt, cdn) {

        let row = locals[cdt][cdn];
        let subjects = [];

        if (frm.doc.psychometric_test_subject) {

            frm.doc.psychometric_test_subject.forEach(function(d) {

                if (d.name !== row.name && d.subject) {
                    subjects.push(d.subject);
                }

            });
        }

        if (subjects.includes(row.subject)) {
            frappe.msgprint("Duplicate Subject not allowed");
            frappe.model.set_value(cdt, cdn, "subject", "");
        }
    }

});



frappe.ui.form.on('Str Psychometric Test', {

    refresh: function(frm) {

        frm.set_query("question", "str_psychometric_test_question", function() {

            let subjects = [];

            // ✅ Correct fieldname
            if (frm.doc.psychometric_test_subject) {

                frm.doc.psychometric_test_subject.forEach(function(row) {

                    if (row.subject) {
                        subjects.push(row.subject);
                    }

                });
            }

            console.log("Selected Subjects:", subjects);

            if (!subjects.length) {
                return {
                    filters: [['name', '=', '']]
                };
            }

            return {
                filters: [
                    ['test_subject', 'in', subjects]
                ]
            };
        });

    }

});
