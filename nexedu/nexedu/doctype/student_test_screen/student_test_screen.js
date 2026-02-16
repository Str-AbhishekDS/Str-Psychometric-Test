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

        let args = {};
        let qtype = frm.doc.question_type;

        if (qtype === "Choices") {

            let selected = null;

            if (frm.doc.is_correct_a) selected = frm.doc.a;
            if (frm.doc.is_correct_b) selected = frm.doc.b;
            if (frm.doc.is_correct_c) selected = frm.doc.c;
            if (frm.doc.is_correct_d) selected = frm.doc.d;

            if (!selected) {
                frappe.msgprint("Please select one option");
                return;
            }

            args.selected_option = selected;
        }

        if (qtype === "User Input") {

            if (!frm.doc.user_input) {
                frappe.msgprint("Please enter answer");
                return;
            }

            args.user_input = frm.doc.user_input;
        }

        if (qtype === "Open Ended") {

            if (!frm.doc.open_ended) {
                frappe.msgprint("Please enter answer");
                return;
            }

            args.open_ended = frm.doc.open_ended;
        }

        frm.call("next_question", args).then(r => {

            if (!r.message) return;

            // 🔥 THEN clear and load next
            clear_fields(frm);
            set_question(frm, r.message);
        });
    },

    previous(frm) {

        frm.call("previous_question").then(r => {

            if (!r.message) return;

            clear_fields(frm);
            set_question(frm, r.message);

            if (r.message.saved_response) {

                if (r.message.question_type === "Choices") {

                    if (r.message.saved_response === frm.doc.a)
                        frm.set_value("is_correct_a", 1);

                    if (r.message.saved_response === frm.doc.b)
                        frm.set_value("is_correct_b", 1);

                    if (r.message.saved_response === frm.doc.c)
                        frm.set_value("is_correct_c", 1);

                    if (r.message.saved_response === frm.doc.d)
                        frm.set_value("is_correct_d", 1);
                }

                if (r.message.question_type === "User Input") {
                    frm.set_value("user_input", r.message.saved_response);
                }

                if (r.message.question_type === "Open Ended") {
                    frm.set_value("open_ended", r.message.saved_response);
                }
            }

            frm.refresh_fields();
            
        });
    }

});


function handle_single_select(frm, selected_field) {

    let fields = ["is_correct_a", "is_correct_b", "is_correct_c", "is_correct_d"];

    fields.forEach(f => {
        if (f !== selected_field) {
            frm.set_value(f, 0);
        }
    });
}

frappe.ui.form.on("Student Test Screen", {

    is_correct_a(frm) {
        if (frm.doc.is_correct_a) {
            handle_single_select(frm, "is_correct_a");
        }
    },

    is_correct_b(frm) {
        if (frm.doc.is_correct_b) {
            handle_single_select(frm, "is_correct_b");
        }
    },

    is_correct_c(frm) {
        if (frm.doc.is_correct_c) {
            handle_single_select(frm, "is_correct_c");
        }
    },

    is_correct_d(frm) {
        if (frm.doc.is_correct_d) {
            handle_single_select(frm, "is_correct_d");
        }
    }

});



function load_question(frm) {

    frm.call("load_question").then(r => {
        set_question(frm, r.message);
    });
}


function set_question(frm, data) {

    // 1️⃣ Clear ALL checkboxes FIRST
    frm.set_value("is_correct_a", 0);
    frm.set_value("is_correct_b", 0);
    frm.set_value("is_correct_c", 0);
    frm.set_value("is_correct_d", 0);

    frm.set_value("question_type", data.question_type);

    // 2️⃣ Set question & options
    frm.set_value("question", data.question);
    frm.set_value("a", data.a);
    frm.set_value("b", data.b);
    frm.set_value("c", data.c);
    frm.set_value("d", data.d);

    // 3️⃣ Restore response from child table
    if (frm.doc.str_test_response) {

        frm.doc.str_test_response.forEach(row => {

            if (row.question === data.question) {

                if (row.response === data.a)
                    frm.set_value("is_correct_a", 1);

                if (row.response === data.b)
                    frm.set_value("is_correct_b", 1);

                if (row.response === data.c)
                    frm.set_value("is_correct_c", 1);

                if (row.response === data.d)
                    frm.set_value("is_correct_d", 1);
            }
        });
    }

    // 🔥 IMPORTANT FIX:
    // DO NOT hide next button anymore
    frm.toggle_display("next", true);

    frm.refresh_fields();
}


function clear_fields(frm) {

    frm.set_value("user_input", "");
    frm.set_value("open_ended", "");
}
