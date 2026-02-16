// Copyright (c) 2026, Stride nex and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Str Program D", {
// 	refresh(frm) {

// 	},
// });
frappe.ui.form.on('Str Program D', {

    university: function (frm) {

        // Filter College based on selected University
        frm.set_query('college', function () {
            return {
                filters: {
                    university: frm.doc.university
                }
            };
        });

        // Clear college if university changes
        frm.set_value('college', null);
    }
});
