frappe.ui.form.on('Student Path Enrollment', {

     setup(frm) {
        frm.add_custom_button('Enroll', () => {
            handle_enroll_click(frm);
        });
    },

    refresh(frm) {
        render_milestone_status_colors(frm);

        if (!frm.doc.milestone_progress) return;

            frm.doc.milestone_progress.forEach(row => {

                if (row.status === "In Progress") {
                    frappe.show_alert({
                        message: "Current milestone: " + row.milestone_title,
                        indicator: "blue"
                    });
                }
            });
        
        frm.fields_dict.milestone_progress.grid.wrapper.find('.grid-row').each(function() {
            let row = $(this);

            if (row.text().includes("Completed")) {
                row.css("background-color", "#d4edda");
            }
            if (row.text().includes("Locked")) {
                row.css("background-color", "#f8d7da");
            }
        });
    },

    career_path: function(frm) {
        frm.trigger('run_prerequisite_check');
    },

    student: function(frm) {
        frm.trigger('run_prerequisite_check');
    },

    run_prerequisite_check: function(frm) {
        if (!frm.doc.student || !frm.doc.career_path) return;

        frm.dashboard.clear_headline();
        frm.dashboard.set_headline_alert(
            '🔍 Checking prerequisites...',
            'yellow'
        );

        frappe.call({
            method: 'nexedu.path_finder.doctype' +
                    '.student_path_enrollment' +
                    '.student_path_enrollment' +
                    '.check_prerequisite_skills',
            args: {
                student: frm.doc.student,
                career_path: frm.doc.career_path
            },
            callback: function(r) {
                if (!r.message) return;
                let result = r.message;

                frm.dashboard.clear_headline();

                if (result.status === 'clear') {
                    frm.dashboard.set_headline_alert(
                        `✅ All prerequisites met — 
                         Readiness: ${result.readiness_percent}%`,
                        'green'
                    );
                } else {
                    show_skill_gap_dialog(frm, result);
                }
            }
        });
    }
});


// ══════════════════════════════════════════
// BUILD SKILL ROW
// ✅ Use data attributes instead of onclick
// ══════════════════════════════════════════
function build_skill_row(skill_data, type) {
    let path_button = '';

    if (skill_data.recommended_path) {
        let path = skill_data.recommended_path;

        // ✅ Store path name in data-path attribute
        // No inline onclick — event listener added after render
        path_button = `
            <button
                class="btn btn-xs btn-primary open-path-btn"
                data-path="${path.path_name}"
                style="margin-top:6px">
                📚 ${path.display_name || path.path_name}
                ${path.duration_months
                    ? `&nbsp;·&nbsp;${path.duration_months} months`
                    : ''
                }
                ${path.difficulty
                    ? `&nbsp;·&nbsp;${path.difficulty}`
                    : ''
                }
            </button>`;
    } else {
        path_button = `
            <span style="
                color       : grey;
                font-size   : 11px;
                margin-top  : 5px;
                display     : block">
                No recommended path linked yet
            </span>`;
    }

    let color = type === 'missing' ? '#ff4d4f' : '#fa8c16';
    let icon  = type === 'missing' ? '❌' : '⚠️';

    return `
        <li style="
            margin-bottom : 10px;
            padding       : 10px;
            border-left   : 3px solid ${color};
            background    : #fafafa;
            list-style    : none;
            border-radius : 4px">
            <div>
                ${icon} <b>${skill_data.skill}</b>
                &nbsp;·&nbsp;
                Required: <b>${skill_data.required_level}</b>
                &nbsp;·&nbsp;
                Current:
                <b>${skill_data.current_level || 'Not started'}</b>
            </div>
            <div>${path_button}</div>
        </li>`;
}


// ══════════════════════════════════════════
// SHOW SKILL GAP DIALOG
// ══════════════════════════════════════════
function show_skill_gap_dialog(frm, result) {

    let missing_html = '';
    if (result.missing_skills.length) {
        missing_html += `
            <h5 style="color:#ff4d4f; margin-top:10px">
                ❌ Missing Skills (${result.missing_skills.length})
            </h5>
            <ul style="padding:0">`;
        result.missing_skills.forEach(s => {
            missing_html += build_skill_row(s, 'missing');
        });
        missing_html += '</ul>';
    }

    let partial_html = '';
    if (result.partial_skills.length) {
        partial_html += `
            <h5 style="color:#fa8c16; margin-top:10px">
                ⚠️ Needs Improvement (${result.partial_skills.length})
            </h5>
            <ul style="padding:0">`;
        result.partial_skills.forEach(s => {
            partial_html += build_skill_row(s, 'partial');
        });
        partial_html += '</ul>';
    }

    let bar_color =
        result.readiness_percent >= 75 ? '#52c41a' :
        result.readiness_percent >= 50 ? '#fa8c16' :
                                         '#ff4d4f';

    let can_enroll = result.readiness_percent >= 50;

    let dialog = new frappe.ui.Dialog({
        title : '📋 Skill Gap Analysis',
        size  : 'large',
        fields: [{
            fieldtype: 'HTML',
            options  : `
                <div style="padding:10px">
                    <h4>
                        Readiness Score:
                        <span style="color:${bar_color}">
                            ${result.readiness_percent}%
                        </span>
                        <small style="color:grey; font-size:13px">
                            (${result.matched} /
                             ${result.total_prerequisites} matched)
                        </small>
                    </h4>

                    <div style="
                        background    : #e0e0e0;
                        border-radius : 10px;
                        height        : 10px;
                        margin-bottom : 15px">
                        <div style="
                            width         : ${result.readiness_percent}%;
                            background    : ${bar_color};
                            height        : 10px;
                            border-radius : 10px">
                        </div>
                    </div>

                    ${missing_html}
                    ${partial_html}

                    <hr>
                    <p style="color:grey; font-size:12px">
                        💡 Click any path button to open that Career Path
                        and enroll to build the required skill first.
                    </p>
                </div>`
        }],

        primary_action_label: can_enroll
            ? 'Enroll Anyway'
            : 'Go Back & Complete Skills',

        primary_action: function() {
            if (!can_enroll) {
                frm.set_value('career_path', '');
            }
            dialog.hide();
        },

        secondary_action_label: can_enroll ? 'Go Back' : null,
        secondary_action: function() {
            frm.set_value('career_path', '');
            dialog.hide();
        }
    });

    dialog.show();

    // ✅ ATTACH EVENT LISTENERS AFTER DIALOG RENDERS
    // This is the key fix — buttons exist in DOM now
    // so we can safely attach click handlers
    setTimeout(() => {
        dialog.$wrapper
            .find('.open-path-btn')
            .on('click', function() {
                let path_name = $(this).data('path');

                if (path_name) {
                    // ✅ Navigate to Career Path form
                    frappe.set_route(
                        'Form',
                        'Career Path',
                        path_name
                    );
                    dialog.hide();
                }
            });
    }, 300); // Small delay ensures dialog HTML is fully rendered
}
// ```

// ---

// ## Why This Happens and Why This Fix Works

// | Approach | Problem |
// |---|---|
// | `onclick="open_career_path(...)"` | Function lives in script scope, not global `window` — HTML onclick can't find it |
// | `onclick="frappe.set_route(...)"` | Works but path name with spaces breaks inside HTML string |
// | ✅ `data-path` + `setTimeout` listener | Button renders first, then listener attaches — always works |

// ---

// ## Key Changes Summary
// ```
// BEFORE — broken
// <button onclick="open_career_path('${path.path_name}')">

// AFTER — fixed
// <button class="open-path-btn" data-path="${path.path_name}">

// // Then after dialog renders:
// dialog.$wrapper.find('.open-path-btn').on('click', function() {
//     let path_name = $(this).data('path');
//     frappe.set_route('Form', 'Career Path', path_name);
// });




// // ================================
// // ENROLL BUTTON
// // ================================
// async function handle_enroll_click(frm) {

//     if (!frm.doc.career_path) {
//         frappe.msgprint('Please select a Career Path first.');
//         return;
//     }

//     const gap = await frappe.call({
//         method: 'nexedu.path_finder.utils.enrollment_utils.check_skill_gap',
//         args: {
//             career_path: frm.doc.career_path,
//             student: frm.doc.student
//         }
//     });

//     const result = gap.message;

//     if (!result.has_gap) {
//         frm.save('Submit');
//         return;
//     }

//     await show_skill_gap_dialog(result, frm.doc.name, frm);
// }


// // ================================
// // SKILL GAP DIALOG
// // ================================
// async function show_skill_gap_dialog(gap_result, enrollment_name, frm) {

//     const { missing, match_percent, matched, total } = gap_result;

//     const previews = await Promise.all(
//         missing
//             .filter(s => s.learning_path)
//             .map(s =>
//                 frappe.call({
//                     method: 'nexedu.path_finder.utils.enrollment_utils.get_path_preview',
//                     args: { career_path: s.learning_path }
//                 }).then(r => ({ ...s, preview: r.message }))
//             )
//     );

//     let cards_html = '';

//     previews.forEach(item => {
//         const p = item.preview;

//         cards_html += `
//         <div style="border:1px solid #ddd;border-radius:8px;padding:12px;margin-bottom:10px">
//             <div style="font-weight:500">${p.title}</div>
//             <div style="font-size:12px;color:gray">
//                 ${p.milestone_count} milestones
//             </div>

//             <div style="font-size:12px;margin:8px 0">
//                 Required skill: <b>${item.skill_name}</b>
//             </div>

//             <button
//                 id="enroll-btn-${item.learning_path}"
//                 class="btn btn-xs btn-primary"
//                 onclick="window._enroll_prereq('${item.learning_path}',
//                 '${frm.doc.student}', '${enrollment_name}')">
//                 Enroll
//             </button>
//         </div>`;
//     });

//     const html = `
//         <h4>${match_percent}% Skill Match</h4>
//         <p>Missing prerequisites. Please enroll in below paths:</p>
//         ${cards_html}
//         <button class="btn btn-sm btn-default"
//             onclick="window._enroll_anyway('${frm.doc.name}')">
//             Enroll Anyway
//         </button>
//     `;

//     // GLOBAL FUNCTIONS
//     window._enroll_prereq = async function(career_path, student, from_enrollment) {

//         const btn = document.getElementById(`enroll-btn-${career_path}`);
//         if (btn) {
//             btn.innerText = "Enrolling...";
//             btn.disabled = true;
//         }

//         const r = await frappe.call({
//             method: 'nexedu.path_finder.utils.enrollment_utils.enroll_in_prerequisite_path',
//             args: {
//                 career_path,
//                 student,
//                 triggered_from_enrollment: from_enrollment
//             }
//         });

//         frappe.msgprint(r.message.message || "Done");
//     };

//     window._enroll_anyway = function(enrollment_name) {
//         frm.save('Submit');
//     };

//     frappe.msgprint({
//         title: "Skill Gap",
//         message: html,
//         wide: true
//     });
// }


// // ================================
// // STATUS COLORS
// // ================================
// function render_milestone_status_colors(frm) {

//     const STATUS_COLORS = {
//         'Completed': 'green',
//         'In Progress': 'blue',
//         'Skipped': 'orange',
//         'Not Started': 'gray',
//     };

//     setTimeout(() => {

//         // ⚠️ CHANGE THIS IF YOUR FIELD NAME IS DIFFERENT
//         let table = frm.doc.path_progress_log || frm.doc.milestone_progress;

//         if (!table) return;

//         table.forEach(row => {

//             const color = STATUS_COLORS[row.status] || 'gray';

//             const row_el = document.querySelector(
//                 `[data-name="${row.name}"] .col[data-fieldname="status"]`
//             );

//             if (row_el) {
//                 row_el.innerHTML = `<span class="indicator-pill ${color}">
//                     ${row.status}
//                 </span>`;
//             }
//         });

//     }, 500);
// }