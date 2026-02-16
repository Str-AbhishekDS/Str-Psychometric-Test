// Copyright (c) 2026, Stride nex and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Str Course", {
// 	refresh(frm) {

// 	},
// });



// frappe.ui.form.on("Course", {
//     setup(frm) {
//         frm.set_query("program", function () {
//             return {
//                 filters: {
//                     is_active: 1
//                 }
//             };
//         });
//     }
// });



frappe.ui.form.on('Str Course', {

    program: function (frm) {

        // Clear semester if program changes
        frm.set_value('semester', null);

        if (!frm.doc.program) return;

        frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: "Str Program D",
                name: frm.doc.program
            },
            callback: function (r) {

                if (!r.message) return;

                let total = r.message.total_semesters;
                if (!total) return;

                let options = [];
                for (let i = 1; i <= total; i++) {
                    options.push(i.toString());
                }

                frm.set_df_property(
                    'semester',
                    'options',
                    options.join('\n')
                );
            }
        });
    }
});
