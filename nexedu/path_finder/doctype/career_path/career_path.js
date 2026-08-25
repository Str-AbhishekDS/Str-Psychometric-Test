// Copyright (c) 2026, Stride nex and contributors
// For license information, please see license.txt
//
// career_path.js
// ─────────────────────────────────────────────────────────────────────────────
// CHANGES:
//   - setup: topic/subtopic filters use "path_milestone" (correct fieldname)
//   - refresh: "Enroll a Student" button triggers full skill match dialog
//   - live prereq check in enroll dialog now shows matched + partial + missing
//   - Fit score computed and shown in enroll dialog
//   - order field removed from before_save (controller handles idx)
// ─────────────────────────────────────────────────────────────────────────────

const CAREER_API = {
    CHECK_PREREQS : "nexedu.path_finder.api.path_enrollment.check_prerequisite_skills",
    ENROLL        : "nexedu.path_finder.api.path_enrollment.enroll_student",
    SUGGESTIONS   : "nexedu.path_finder.api.path_enrollment.get_path_suggestions",
};

frappe.ui.form.on("Career Path", {

    setup(frm) {
        // Cascade filters on path_milestone child table
        // parentfield is "path_milestone" as defined in Career Path JSON schema

        frm.set_query("topic", "path_milestone", function(doc, cdt, cdn) {
            const row = locals[cdt][cdn];
            return { filters: { category: row.category } };
        });

        frm.set_query("subtopic", "path_milestone", function(doc, cdt, cdn) {
            const row = locals[cdt][cdn];
            return { filters: { topic: row.topic } };
        });

        // frm.set_query("skill", "path_milestone", function(doc, cdt, cdn) {
        //     const row = locals[cdt][cdn];
        //     if (!row.category) return {};
        //     return { filters: { category: row.category } };
        // });

        // Cascade on prerequisite_skills child table
        frm.set_query("skill", "prerequisite_skills", function() {
            return {};  // No filter needed — all skills available
        });
    },

    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__("Enroll a Student"), () => {
                _show_enroll_dialog(frm);
            }, __("Actions"));

            frm.add_custom_button(__("View Path Suggestions"), () => {
                _show_student_suggestions_dialog(frm);
            }, __("Actions"));
        }

        // Show prerequisite count in dashboard
        _show_prereq_summary(frm);
    },
});


// ─────────────────────────────────────────────────────────────────────────────
// SHOW PREREQ SUMMARY ON CAREER PATH FORM
// ─────────────────────────────────────────────────────────────────────────────

function _show_prereq_summary(frm) {
    if (frm.is_new()) return;

    const prereq_count    = (frm.doc.prerequisite_skills || []).length;
    const milestone_count = (frm.doc.path_milestone || []).length;
    const total           = prereq_count + milestone_count;

    if (total === 0) return;

    frm.dashboard.clear_headline();
    frm.dashboard.set_headline_alert(
        `📋 ${prereq_count} Prerequisite Skills  +  🗺️ ${milestone_count} Path Milestones  =  ${total} Total`,
        "blue"
    );
}


// ─────────────────────────────────────────────────────────────────────────────
// ENROLL A STUDENT DIALOG — from Career Path form
// Shows live fit score + full skill breakdown before enrollment
// ─────────────────────────────────────────────────────────────────────────────

function _show_enroll_dialog(frm) {
    let _last_student = null;
    let _last_result  = null;

    const dialog = new frappe.ui.Dialog({
        title : `Enroll Student — ${frm.doc.path_name || frm.doc.name}`,
        fields: [
            {
                label    : "Student",
                fieldname: "student",
                fieldtype: "Link",
                options  : "Student",
                reqd     : 1,
                onchange() {
                    const student = dialog.get_value("student");
                    if (!student || student === _last_student) return;
                    _last_student = student;
                    _live_prereq_check(dialog, student, frm.doc.name, function(result) {
                        _last_result = result;
                    });
                },
            },
            {
                fieldtype: "HTML",
                fieldname: "prereq_result_html",
                options  : `<div id="prereq-live-result" style="padding:4px 0;
                    color:#8c8c8c;font-size:12px;">
                    Select a student to check skill match…
                </div>`,
            },
        ],
        primary_action_label: "Check & Enroll",
        primary_action(values) {
            dialog.hide();
            if (_last_result) {
                // Show full skill gap dialog (always-enable enroll)
                _show_full_skill_dialog(frm, values.student, _last_result);
            } else {
                // Fallback direct enroll
                _do_direct_enroll(values.student, frm.doc.name);
            }
        },
    });

    dialog.show();
}


function _live_prereq_check(dialog, student, career_path, callback) {
    const $div = dialog.$wrapper.find("#prereq-live-result");
    $div.html(`<div style="color:#8c8c8c;font-size:12px;">🔍 Checking skill match…</div>`);

    frappe.call({
        method  : CAREER_API.CHECK_PREREQS,
        args    : { student, career_path },
        callback(r) {
            if (!r.message) return;
            const result = r.message;
            if (callback) callback(result);

            const bar_color = result.readiness_percent >= 75 ? "#52c41a"
                            : result.readiness_percent >= 50 ? "#fa8c16"
                            :                                  "#ff4d4f";

            const status_html = result.status === "clear"
                ? `<div style="color:#52c41a;font-weight:600;font-size:13px;">
                       ✅ All skills matched (${result.readiness_percent}%)
                   </div>`
                : `<div style="font-size:13px;">
                       <span style="color:${bar_color};font-weight:700;">${result.readiness_percent}% match</span>
                       &nbsp;·&nbsp;
                       <span style="color:#52c41a;">✅ ${result.matched_skills.length} matched</span>
                       &nbsp;·&nbsp;
                       <span style="color:#fa8c16;">⚠️ ${result.partial_skills.length} partial</span>
                       &nbsp;·&nbsp;
                       <span style="color:#ff4d4f;">❌ ${result.missing_skills.length} missing</span>
                   </div>`;

            $div.html(`
                <div style="margin-top:6px;">
                    ${status_html}
                    <div style="background:#e0e0e0;border-radius:6px;height:8px;margin-top:6px;">
                        <div style="width:${result.readiness_percent}%;background:${bar_color};
                            height:8px;border-radius:6px;"></div>
                    </div>
                    ${result.missing_skills.length
                        ? `<div style="font-size:11px;color:#ff4d4f;margin-top:4px;">
                               Missing: ${result.missing_skills.map(s => s.skill).join(", ")}
                           </div>`
                        : ""}
                    <div style="font-size:11px;color:#8c8c8c;margin-top:4px;">
                        Click "Check &amp; Enroll" to see full breakdown and enroll.
                    </div>
                </div>`);
        },
    });
}


function _show_full_skill_dialog(frm, student, result) {
    // Build a synthetic frm-like object so we can reuse the skill dialog
    // which needs frm.doc.student and frm.doc.career_path
    const pseudo_frm = {
        doc: { student: student, career_path: frm.doc.name },
        set_value: () => {},
    };

    // Inline the skill gap dialog (duplicate here to avoid cross-file dependency)
    function skill_row(s, type) {
        const CFG = {
            matched : { color:"#52c41a", bg:"#f6ffed", border:"#b7eb8f", icon:"✅", label:"Matched" },
            partial : { color:"#fa8c16", bg:"#fff7e6", border:"#ffd591", icon:"⚠️", label:"Partial" },
            missing : { color:"#ff4d4f", bg:"#fff1f0", border:"#ffa39e", icon:"❌", label:"Missing" },
        }[type];

        return `
        <li style="margin-bottom:6px;padding:8px 12px;border-left:3px solid ${CFG.color};
            background:${CFG.bg};border:1px solid ${CFG.border};list-style:none;border-radius:6px;">
            <div style="display:flex;align-items:center;justify-content:space-between;">
                <span style="font-weight:600;font-size:12px;">${CFG.icon} ${s.skill}</span>
                <span style="color:${CFG.color};font-size:11px;font-weight:600;">${CFG.label}</span>
            </div>
            <div style="font-size:11px;color:#595959;margin-top:2px;">
                Required: <b>${s.required_level}</b>
                → Current: <b style="color:${CFG.color}">${s.current_level || "None"}</b>
            </div>
        </li>`;
    }

    const m_html = result.matched_skills.length
        ? `<h5 style="color:#52c41a;margin:10px 0 6px;">✅ Matched (${result.matched_skills.length})</h5>
           <ul style="padding:0;">${result.matched_skills.map(s => skill_row(s,"matched")).join("")}</ul>`
        : "";
    const p_html = result.partial_skills.length
        ? `<h5 style="color:#fa8c16;margin:10px 0 6px;">⚠️ Partial (${result.partial_skills.length})</h5>
           <ul style="padding:0;">${result.partial_skills.map(s => skill_row(s,"partial")).join("")}</ul>`
        : "";
    const x_html = result.missing_skills.length
        ? `<h5 style="color:#ff4d4f;margin:10px 0 6px;">❌ Missing (${result.missing_skills.length})</h5>
           <ul style="padding:0;">${result.missing_skills.map(s => skill_row(s,"missing")).join("")}</ul>`
        : "";

    const pct       = result.readiness_percent || 0;
    const bar_color = pct >= 75 ? "#52c41a" : pct >= 50 ? "#fa8c16" : "#ff4d4f";

    const prereq_paths = [...new Map(
        [...result.partial_skills, ...result.missing_skills]
            .filter(s => s.recommended_path)
            .map(s => [s.recommended_path.path_name, s.recommended_path.path_name])
    ).values()];

    const dlg = new frappe.ui.Dialog({
        title : `📊 Skill Match — ${student}`,
        size  : "large",
        fields: [{
            fieldtype: "HTML",
            options  : `
            <div style="padding:8px 4px;">
                <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
                    <span style="background:#f6ffed;color:#52c41a;border:1px solid #b7eb8f;
                        border-radius:10px;font-size:12px;padding:2px 10px;font-weight:600;">
                        ✅ ${result.matched_skills.length}
                    </span>
                    <span style="background:#fff7e6;color:#fa8c16;border:1px solid #ffd591;
                        border-radius:10px;font-size:12px;padding:2px 10px;font-weight:600;">
                        ⚠️ ${result.partial_skills.length}
                    </span>
                    <span style="background:#fff1f0;color:#ff4d4f;border:1px solid #ffa39e;
                        border-radius:10px;font-size:12px;padding:2px 10px;font-weight:600;">
                        ❌ ${result.missing_skills.length}
                    </span>
                    <span style="color:${bar_color};font-weight:700;font-size:14px;margin-left:8px;">
                        ${pct}% Fit Score
                    </span>
                </div>
                <div style="background:#e0e0e0;border-radius:10px;height:10px;margin-bottom:12px;">
                    <div style="width:${pct}%;background:${bar_color};height:10px;border-radius:10px;"></div>
                </div>
                ${x_html}${p_html}${m_html}
                <hr style="margin:12px 0 8px;">
                <div style="background:#e6f7ff;border:1px solid #91d5ff;border-radius:6px;
                    padding:10px;font-size:12px;color:#0050b3;">
                    💡 Prerequisite skill milestones are automatically added before the
                    main path milestones on enrollment.
                </div>
            </div>`,
        }],
        primary_action_label: "✅ Enroll Now",
        primary_action() {
            dlg.hide();
            frappe.call({
                method        : CAREER_API.ENROLL,
                args          : {
                    student     : student,
                    career_path : frm.doc.name,
                    force_enroll: 1,
                    prereq_paths: JSON.stringify(prereq_paths),
                },
                freeze        : true,
                freeze_message: "Setting up learning path…",
                callback(r) {
                    if (!r.message) return;
                    if (r.message.status === "already_enrolled") {
                        frappe.show_alert({ message: "Already enrolled.", indicator: "orange" });
                        frappe.set_route("Form", "Student Path Enrollment", r.message.enrollment);
                        return;
                    }
                    if (r.message.status === "success") {
                        frappe.show_alert({ message: "✅ Enrolled!", indicator: "green" });
                        frappe.set_route("Form", "Student Path Enrollment", r.message.enrollment);
                    }
                },
            });
        },
        secondary_action_label: "Cancel",
        secondary_action() { dlg.hide(); },
    });
    dlg.show();
}


// ─────────────────────────────────────────────────────────────────────────────
// VIEW PATH SUGGESTIONS FOR A STUDENT (from Career Path form)
// ─────────────────────────────────────────────────────────────────────────────

function _show_student_suggestions_dialog(frm) {
    const dialog = new frappe.ui.Dialog({
        title : "Find Best Path Matches for a Student",
        fields: [
            {
                label    : "Student",
                fieldname: "student",
                fieldtype: "Link",
                options  : "Student",
                reqd     : 1,
            },
            {
                label    : "Top N paths",
                fieldname: "limit",
                fieldtype: "Int",
                default  : 5,
            },
        ],
        primary_action_label: "Get Suggestions",
        primary_action(values) {
            dialog.hide();
            frappe.call({
                method  : CAREER_API.SUGGESTIONS,
                args    : { student: values.student, limit: values.limit || 5 },
                freeze  : true,
                freeze_message: "Calculating fit scores…",
                callback(r) {
                    if (!r.message) return;
                    _render_suggestions_dialog(values.student, r.message);
                },
            });
        },
    });
    dialog.show();
}

function _render_suggestions_dialog(student, suggestions) {
    if (!suggestions.length) {
        frappe.msgprint("No published career paths found.");
        return;
    }

    const cards = suggestions.map((p, i) => {
        const score_color = p.fit_score >= 75 ? "#52c41a"
                          : p.fit_score >= 50 ? "#fa8c16"
                          :                    "#ff4d4f";
        const rank_emoji  = ["🥇","🥈","🥉","4️⃣","5️⃣"][i] || `#${i+1}`;

        const chips = (p.skill_tags || []).map(t => {
            const c = t.status === "matched" ? "#52c41a"
                    : t.status === "partial" ? "#fa8c16"
                    :                          "#ff4d4f";
            return `<span style="background:#f5f5f5;color:${c};border:1px solid ${c};
                border-radius:10px;font-size:10px;padding:1px 7px;margin:2px;">${t.skill}</span>`;
        }).join("");

        return `
        <div style="border:1px solid #e8e8e8;border-radius:8px;padding:14px;
            margin-bottom:10px;border-left:4px solid ${score_color};">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
                <div>
                    <span style="font-size:14px;font-weight:700;">${rank_emoji} ${p.path_name}</span>
                    <span style="font-size:12px;color:#595959;margin-left:6px;">${p.target_role||""}</span>
                </div>
                <span style="font-size:20px;font-weight:800;color:${score_color};">${p.fit_score}%</span>
            </div>
            <div style="margin:6px 0;font-size:11px;color:#595959;display:flex;gap:8px;flex-wrap:wrap;">
                ${p.difficulty_level ? `<span>⚡ ${p.difficulty_level}</span>` : ""}
                ${p.estimated_duration ? `<span>⏱ ${p.estimated_duration}mo</span>` : ""}
                ${p.average_salary ? `<span>💰 ₹${p.average_salary}L</span>` : ""}
                <span>✅${p.matched_count} ⚠️${p.partial_count} ❌${p.missing_count}</span>
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:2px;">${chips}</div>
        </div>`;
    }).join("");

    new frappe.ui.Dialog({
        title : `🎯 Top Path Matches — ${student}`,
        size  : "large",
        fields: [{
            fieldtype: "HTML",
            options  : `<div style="padding:8px;">${cards}</div>`,
        }],
    }).show();
}