frappe.ui.form.on('Str Psychometric Test Subject Detail', {

    subject: function(frm, cdt, cdn) {

        frappe.msgprint("Child JS Triggered");

        let row = locals[cdt][cdn];
        let subjects = [];

        if (frm.doc.psychometric_test_subjects) {

            frm.doc.psychometric_test_subjects.forEach(function(d) {

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
