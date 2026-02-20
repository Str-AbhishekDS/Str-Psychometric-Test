frappe.ui.form.on("Student Test Screen", {

    refresh(frm) {
        if (!frm.doc.question_index) {
            frm.set_value("question_index", 0);
        }
    },

    test_type(frm) {
        frm.set_value("question_index", 0);
        frm.save().then(() => {
            load_question(frm);
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

        clear_all(frm);
        set_question(frm, r.message);

        // ✅ MOVE THIS INSIDE
        // if (r.message.is_last) {
        //     frm.set_value("is_last", 1);
        //     frm.toggle_display("next", false);
        //     frm.set_df_property("next","hidden",1);
        //     frm.refresh_field("next");
        // } else {
        //     frm.set_value("is_last", 0);
        //     frm.toggle_display("next", true);
        //     frm.set_df_property("next","hidden",0);
        // }

    });

},

    previous(frm) {

        frm.call("previous_question").then(r => {

            if (!r.message) return;

            set_question(frm, r.message);

            // Restore after render
            setTimeout(() => {

                let saved = r.message.saved_response;

                if (!saved) return;

                saved = saved.trim();

                for (let i = 1; i <= 10; i++) {

                    let option_text = frm.doc[`field_${i}`];

                    if (option_text && option_text.trim() === saved) {
                        frm.set_value(`is_selected_${i}`, 1);
                        break;
                    }
                }

                frm.refresh_fields();

            }, 100);

        });
    },


});


/* =========================
   LOAD QUESTION
========================= */

function load_question(frm) {

    frm.call("load_question").then(r => {
        if (!r.message) return;

        set_question(frm, r.message);

        // if (r.message.is_last) {
        //     frm.set_value("is_last", 1);
        //     frm.toggle_display("next", false);
        // } else {
        //     frm.set_value("is_last", 0);
        //     frm.toggle_display("next", true);
        // }
    });
}



/* =========================
   SET QUESTION
========================= */

function set_question(frm, data) {
    // 🔹 Clear all first
    clear_all(frm);

    // 🔹 Set options dynamically
    if (data.options) {

        data.options.forEach((opt, index) => {
            
            let i = index + 1;
            // frm.set_value(`option_${i}`, opt);
            
            // frm.set_value(`is_selected_${i}`, opt);
            frm.set_value(`field_${i}`, opt);

            // frm.toggle_display(`option_${i}`, true);
            frm.toggle_display(`field_${i}`, true);

            frm.toggle_display(`is_selected_${i}`, true);
        });
    }

    // 🔹 Hide unused options
    for (let i = data.options.length + 1; i <= 10; i++) {
        // frm.toggle_display(`option_${i}`, false);
        frm.toggle_display(`field_${i}`, false);
        frm.toggle_display(`is_selected_${i}`, false);
    }

    frm.set_value("question", data.question);
    frm.set_value("question_type", data.question_type);
    frm.set_value("no_of_options", data.no_of_options);
    frm.set_value("subject", data.subject);

    frm.refresh_fields();
}


/* =========================
   CLEAR ALL
========================= */

function clear_all(frm) {

    for (let i = 1; i <= 10; i++) {
        // frm.set_value(`option_${i}`, "");
        frm.set_value(`is_selected_${i}`, 0);
    }

    frm.set_value("user_input", "");
    frm.set_value("open_ended", "");
}


/* =========================
   SINGLE SELECT CHECKBOX CONTROL
========================= */

frappe.ui.form.on("Student Test Screen", {

    ...Array.from({ length: 10 }, (_, i) => i + 1).reduce((events, i) => {

        events[`is_selected_${i}`] = function(frm) {

            if (frm.doc[`is_selected_${i}`]) {

                for (let j = 1; j <= 10; j++) {
                    if (j !== i) {
                        frm.set_value(`is_selected_${j}`, 0);
                    }
                }
            }
        };

        return events;

    }, {})

});
