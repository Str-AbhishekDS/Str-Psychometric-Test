// Copyright (c) 2026, Stride nex and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Str Psychometric Test", {
// 	refresh(frm) {

// 	},
// });

// frappe.msgprint("JS Loaded");
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


frappe.ui.form.on('Str Psychometric Test Question', {

    question: function(frm, cdt, cdn) {

        let row = locals[cdt][cdn];
        if (!row.question) return;

        frappe.db.get_doc("Str Question", row.question).then(q => {

            let max_marks = 0;

            if (q.multiple_correct_answers) {

                if (q.option_1_weightage)
                    max_marks = Math.max(max_marks, q.option_1_weightage || 0);

                if (q.option_2_weightage)
                    max_marks = Math.max(max_marks, q.option_2_weightage || 0);

                if (q.option_3_weightage)
                    max_marks = Math.max(max_marks, q.option_3_weightage || 0);

                if (q.option_4_weightage)
                    max_marks = Math.max(max_marks, q.option_4_weightage || 0);

                if (q.option_5_weightage)
                    max_marks = Math.max(max_marks, q.option_5_weightage || 0);

            } else {

                max_marks = q.default_marks || 1;
            }

            frappe.model.set_value(cdt, cdn, "marks", max_marks);

        });
    }

});
