frappe.ui.form.on('Career Path', {

    setup: function(frm) {

        frm.set_query('topic', 'path_milestone', function(doc, cdt, cdn) {
            let row = locals[cdt][cdn];
            if (!row.category) return {};

            return {
                filters: {
                    category: row.category
                }
            };
        });

        frm.set_query('subtopic', 'path_milestone', function(doc, cdt, cdn) {
            let row = locals[cdt][cdn];
            if (!row.topic) return {};

            return {
                filters: {
                    topic: row.topic
                }
            };
        });

        frm.set_query('skill', 'path_milestone', function(doc, cdt, cdn) {
            let row = locals[cdt][cdn];
            if (!row.topic || !row.subtopic) return {};

            return {
                filters: {
                    topic: row.topic,
                    subtopic: row.subtopic
                }
            };
        });

    }
});

frappe.ui.form.on('Path Milestone', {

    category: function(frm, cdt, cdn) {
        frappe.model.set_value(cdt, cdn, 'topic', null);
        frappe.model.set_value(cdt, cdn, 'subtopic', null);
        frappe.model.set_value(cdt, cdn, 'skill', null);
    },

    topic: function(frm, cdt, cdn) {
        frappe.model.set_value(cdt, cdn, 'subtopic', null);
        frappe.model.set_value(cdt, cdn, 'skill', null);
    },

    subtopic: function(frm, cdt, cdn) {
        frappe.model.set_value(cdt, cdn, 'skill', null);
    }

});