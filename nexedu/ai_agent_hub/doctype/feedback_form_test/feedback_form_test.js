frappe.ui.form.on("Feedback Form Test", {

    refresh: function(frm) {
        frm.current_question_index = 0;
        frm.questions = [];
    },

    onload: function(frm) {

        frm.set_query("feedback_form", function() {
            return {
                filters: {
                    is_active: 1
                }
            };
        });

    },

    feedback_form: function(frm) {

        if (!frm.doc.feedback_form) return;

        frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: "Feedback Form",
                name: frm.doc.feedback_form
            },
            callback: function(r) {

                if (r.message) {

                    frm.questions = r.message.feedback_question || [];
                    frm.current_question_index = 0;

                    load_question(frm);
                }

            }
        });

    },

    next: function(frm){

        save_current_answer(frm);

        frm.current_question_index++;

        if(frm.current_question_index >= frm.questions.length){

            frappe.msgprint("All questions completed. Please submit the test.");
            return;
        }

        load_question(frm);
    }

});


function load_question(frm){

    let q = frm.questions[frm.current_question_index];

    if(!q) return;

    frm.set_value("question", q.question);
    frm.set_value("question_type", q.question_type);

    frm.set_value("rate", "");
    frm.set_value("answer", "");
    frm.set_value("response", "");

    frm.toggle_display("rate", q.question_type === "Rating (1-5)");
    frm.toggle_display("answer", q.question_type === "Yes/No");
    frm.toggle_display("response", q.question_type === "Text");

}


function save_current_answer(frm){

    let q = frm.questions[frm.current_question_index];

    if(!q) return;

    let value = "";

    if(q.question_type === "Rating (1-5)"){

        let rate = frm.doc.rate;

        if(!rate || rate < 1 || rate > 5){
            frappe.throw("Please enter rating between 1 and 5");
        }

        value = rate;

    }
    else if(q.question_type === "Yes/No"){

        if(!frm.doc.answer){
            frappe.throw("Please select Yes or No");
        }

        value = frm.doc.answer;

    }
    else{

        if(!frm.doc.response){
            frappe.throw("Please enter your response");
        }

        value = frm.doc.response;

    }

    let row = frm.add_child("feedback_answer");

    row.question = frm.doc.question;
    row.answer = value;

    frm.refresh_field("feedback_answer");
}