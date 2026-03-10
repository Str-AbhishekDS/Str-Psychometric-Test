frappe.pages['feedback-analytics'].on_page_load = function(wrapper) {

    let page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Feedback Analytics',
        single_column: true
    });

    /* ---------------- Filters ---------------- */

    let module_field = page.add_field({
        label: "Module",
        fieldtype: "Link",
        options: "Module Def",
        fieldname: "module",
        change() {
            load_feedback_data(page);
        }
    });

    let doctype_field = page.add_field({
        label: "DocType",
        fieldtype: "Link",
        options: "DocType",
        fieldname: "doctype_name",
        change() {
            load_feedback_data(page);
        }
    });

    let form_field = page.add_field({
        label: "Feedback Form",
        fieldtype: "Link",
        options: "Feedback Form",
        fieldname: "feedback_form",
        change() {
            load_feedback_data(page);
        }
    });

    let user_field = page.add_field({
        label: "User",
        fieldtype: "Link",
        options: "User",
        fieldname: "user",
        change() {
            load_feedback_data(page);
        }
    });

    let from_date = page.add_field({
        label: "From Date",
        fieldtype: "Date",
        fieldname: "from_date",
        change() {
            load_feedback_data(page);
        }
    });

    let to_date = page.add_field({
        label: "To Date",
        fieldtype: "Date",
        fieldname: "to_date",
        change() {
            load_feedback_data(page);
        }
    });


    /* ---------------- Buttons ---------------- */

    page.add_inner_button("Clear Filters", () => {

        module_field.set_value("");
        doctype_field.set_value("");
        form_field.set_value("");
        user_field.set_value("");
        from_date.set_value("");
        to_date.set_value("");

        clear_chart();

        $("#ai_feedback_box").hide();

    });


    page.add_inner_button("Fetch AI Feedback", () => {

        let module = module_field.get_value();

        // if(!module){
        //     frappe.msgprint("Please select module first.");
        //     return;
        // }

        frappe.call({

            method: "nexedu.api.feedback.generate_ai_feedback",

            args:{
                module: module,
                doctype_name: doctype_field.get_value(),
                feedback_form: form_field.get_value(),
                user: user_field.get_value(),
                from_date: from_date.get_value(),
                to_date: to_date.get_value()
            },

            freeze:true,
            freeze_message:"Generating AI Feedback...",

            callback:function(r){

                if(!r.message) return;

                $("#ai_feedback_text").html(format_ai(r.message));

                $("#ai_feedback_box").show();

            }

        });

    });


    /* ---------------- Chart Area ---------------- */

    $(wrapper).append(`
        <div style="padding:20px; max-width:1100px; margin:auto">
            <canvas id="feedback_chart" height="260"></canvas>
        </div>

        <div id="ai_feedback_box"
        style="display:none;margin-top:20px;padding:20px;border:1px solid #ddd;
        border-radius:8px;background:#f9f9f9;max-width:1100px;margin:auto">

            <h4>AI Feedback Summary</h4>

            <div id="ai_feedback_text"></div>

        </div>
    `);

};


/* ================= AI TEXT FORMAT ================= */

function format_ai(text){

    let lines = text.split("\n");

    let html = "<ul>";

    lines.forEach(l=>{

        l = l.trim();

        if(l){
            html += `<li>${l}</li>`;
        }

    });

    html += "</ul>";

    return html;

}


/* ================= LOAD DATA ================= */

function load_feedback_data(page){

    frappe.call({

        method: "nexedu.api.feedback.get_module_feedback_analytics",

        args:{
            module: page.fields_dict.module.get_value(),
            doctype_name: page.fields_dict.doctype_name?.get_value(),
            feedback_form: page.fields_dict.feedback_form?.get_value(),
            user: page.fields_dict.user?.get_value(),
            from_date: page.fields_dict.from_date.get_value(),
            to_date: page.fields_dict.to_date.get_value()
        },

        callback:function(r){

            if(!r.message || r.message.length === 0){
                clear_chart();
                return;
            }

            render_charts(r.message);

        }

    });

}


/* ================= RENDER CHART ================= */

function render_charts(data){


    if(!data || data.length === 0){
        clear_chart();
        return;
    }

    if(typeof Chart === "undefined"){
        console.error("ChartJS not loaded");
        return;
    }

    let labels = [];
    let datasets_map = {};

    window.feedback_questions = [];

    data.forEach((q,index)=>{

        labels.push("Q" + (index + 1));

        window.feedback_questions.push(q.question);

        if(!q.distribution){
            return;
        }

        q.distribution.forEach(d=>{

            if(!datasets_map[d.answer]){
                datasets_map[d.answer] = new Array(data.length).fill(0);
            }

        });

    });


    data.forEach((q,index)=>{

        if(!q.distribution){
            return;
        }

        q.distribution.forEach(d=>{
            datasets_map[d.answer][index] = d.percent;
        });

    });


    let datasets = [];

    Object.keys(datasets_map).forEach(ans=>{

        datasets.push({
            label: ans,
            data: datasets_map[ans],
            backgroundColor: get_color(ans)
        });

    });


    clear_chart();

    const ctx = document.getElementById("feedback_chart").getContext("2d");

    window.feedback_chart = new Chart(ctx, {

        type: "bar",

        data: {
            labels: labels,
            datasets: datasets
        },

        options: {

            responsive: true,
            maintainAspectRatio: false,

            plugins: {

                legend: {
                    position: "top"
                },

                tooltip: {

                    callbacks: {

                        title: function(context){

                            let index = context[0].dataIndex;
                            return window.feedback_questions[index];

                        },

                        label: function(context){

                            return context.dataset.label + " : " + context.raw + "%";

                        }

                    }

                }

            },

            scales: {

                x: { stacked: true },

                y: {
                    stacked: true,
                    max: 100,
                    ticks:{
                        stepSize:20,
                        callback: value => value + "%"
                    }
                }

            }

        }

    });

}


/* ================= CLEAR CHART ================= */

function clear_chart(){

    try{

        if(window.feedback_chart){

            if(typeof window.feedback_chart.destroy === "function"){
                window.feedback_chart.destroy();
            }

            window.feedback_chart = null;
        }

    }catch(e){
        console.warn("Chart destroy skipped", e);
        window.feedback_chart = null;
    }

}

/* ================= COLORS ================= */

function get_color(answer){

    answer = String(answer).toLowerCase().trim();

    if(answer === "yes") return "#4CAF50";
    if(answer === "no") return "#F44336";
    if(answer === "rating") return "#2196F3";

    return random_color();

}


function random_color(){

    const colors=[
        "#5E64FF",
        "#9C27B0",
        "#03A9F4",
        "#26A69A",
        "#FF7043",
        "#795548"
    ];

    return colors[Math.floor(Math.random()*colors.length)];

}