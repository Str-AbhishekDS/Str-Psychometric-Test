// Copyright (c) 2026, Stride nex and contributors
// For license information, please see license.txt


frappe.ui.form.on('Path Progress Log', {

    enrollment: function(frm) {
        // Apply milestone filter when enrollment is selected
        frm.set_query('milestone', function() {
            return {
                filters: {
                    parent: frm.doc.career_path
                }
            };
        });
    },

    career_path: function(frm) {
        // Re-apply filter after career_path is fetched
        frm.set_query('milestone', function() {
            return {
                filters: {
                    parent: frm.doc.career_path
                }
            };
        });
        frm.set_value('milestone', '');
    },

    milestone: function(frm) {
        if (frm.doc.milestone && frm.doc.career_path) {

            // Fetch order from Path Milestone
            frappe.db.get_value(
                'Path Milestone',
                { name: frm.doc.milestone, parent: frm.doc.career_path },
                'order',
                function(value) {
                    if (value && value.order) {
                        frm.set_value('milestone_order', value.order);

                        // Warn if student is trying to skip a milestone
                        frappe.db.get_value(
                            'Student Path Enrollment',
                            frm.doc.enrollment,
                            'current_milestone_order',
                            function(enrollment_data) {
                                let current = enrollment_data.current_milestone_order || 0;
                                let selected = value.order;

                                if (selected > current + 1) {
                                    frappe.msgprint({
                                        title: 'Milestone Order Warning',
                                        message: `You are trying to log Milestone ${selected} 
                                                  but current progress is at ${current}. 
                                                  Make sure previous milestones are completed.`,
                                        indicator: 'orange'
                                    });
                                }
                            }
                        );
                    }
                }
            );
        }
    }

});