// Copyright (c) 2026, Stride nex and contributors
// For license information, please see license.txt

frappe.ui.form.on("Skill Endorsement", {

    refresh: function(frm) {
        set_endorsed_level(frm);
    },

    student_skill: function(frm) {
        set_endorsed_level(frm);
    }
});

function set_endorsed_level(frm) {
    let level = frm.doc.current_level;

    if (!level) return;

    const level_map = {
        "Beginner": ["Beginner"],
        "Intermediate": ["Beginner", "Intermediate"],
        "Advanced": ["Beginner", "Intermediate", "Advanced"],
        "Expert": ["Beginner", "Intermediate", "Advanced", "Expert"]
    };

    let options = level_map[level] || [];

    frm.set_df_property(
        'endorsed_level',
        'options',
        options.join('\n')
    );

    // Clear invalid value
    if (!options.includes(frm.doc.endorsed_level)) {
        frm.set_value('endorsed_level', '');
    }
}