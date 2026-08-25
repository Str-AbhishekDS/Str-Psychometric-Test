// Copyright (c) 2026, Stride nex and contributors
// For license information, please see license.txt
//
// student_path_enrollment.js
// ─────────────────────────────────────────────────────────────────────────────
// KEY CHANGES:
//   • order → idx everywhere (milestone_idx in API responses)
//   • current_milestone filtered to ONLY rows from selected career_path
//   • Skill gap dialog shows ALL skills (matched + partial + missing)
//     with ALWAYS-ENABLED enroll button regardless of readiness score
//   • Milestone count bar shows "4 Prereqs + 11 Milestones = 15 Total"
//   • Prerequisite skill rows auto-shown before path milestone rows in board
//   • Fit score shown in dashboard indicator on refresh
// ─────────────────────────────────────────────────────────────────────────────

const API = {
    ENROLL         : "nexedu.path_finder.api.path_enrollment.enroll_student",
    CHECK_PREREQS  : "nexedu.path_finder.app_api.check_prerequisite_skills",
    OVERVIEW       : "nexedu.path_finder.api.path_enrollment.get_milestone_overview",
    COUNT_SUMMARY  : "nexedu.path_finder.api.path_enrollment.get_milestone_count_summary",
    SKIP           : "nexedu.path_finder.api.path_enrollment.skip_milestone",
    SUGGESTIONS    : "nexedu.path_finder.api.path_enrollment.get_path_suggestions",
    GET_ENROLLMENT : "nexedu.path_finder.api.path_enrollment.get_enrollment_for_student_path",
};


// ─────────────────────────────────────────────────────────────────────────────
// FORM EVENTS
// ─────────────────────────────────────────────────────────────────────────────

frappe.ui.form.on("Student Path Enrollment", {

    refresh(frm) {
        // _filter_current_milestone_by_path(frm);
        _setup_custom_buttons(frm);
        _color_milestone_grid_rows(frm);
        _render_completion_header(frm);
        _render_count_bar(frm);
        _render_milestone_board(frm);
    },

    career_path(frm) {
        // Clear stale milestone selection whenever path changes
        // frm.set_value("current_milestone", "");
        // _filter_current_milestone_by_path(frm);
        _run_prerequisite_check(frm);
    },

    student(frm) {
        _run_prerequisite_check(frm);
    },

    milestone_progress_on_form_rendered(frm) {
        _color_milestone_grid_rows(frm);
    },
});


// ─────────────────────────────────────────────────────────────────────────────
// FIX: Filter current_milestone to ONLY show milestones from selected career_path
// The Path Milestone is a child table of Career Path (parentfield="path_milestone")
// Without this filter, ALL Path Milestone rows from ALL career paths appear.
// ─────────────────────────────────────────────────────────────────────────────

// function _filter_current_milestone_by_path(frm) {
//     if (!frm.doc.career_path) {
//         // Block all results when no path selected
//         frm.set_query("current_milestone", () => ({
//             filters: [["Path Milestone", "name", "=", "__none__"]],
//         }));
//         return;
//     }

//     frm.set_query("current_milestone", () => ({
//         filters: {
//             parent     : frm.doc.career_path,
//             parentfield: "path_milestone",
//         },
//     }));
// }


// ─────────────────────────────────────────────────────────────────────────────
// PREREQUISITE CHECK — runs on student/career_path change for new docs
// ─────────────────────────────────────────────────────────────────────────────

function _run_prerequisite_check(frm) {
    if (!frm.doc.student || !frm.doc.career_path) return;
    if (!frm.is_new()) return;

    frm.dashboard.clear_headline();
    frm.dashboard.set_headline_alert("🔍 Checking skill match…", "yellow");

    frappe.call({
        method  : API.CHECK_PREREQS,
        args    : { student: frm.doc.student, career_path: frm.doc.career_path },
        callback(r) {
            if (!r.message) return;
            const result = r.message;
            console.log(result);
            
            frm.dashboard.clear_headline();

            const color = result.readiness_percent >= 75 ? "green"
                        : result.readiness_percent >= 50 ? "orange"
                        :                                  "red";

            frm.dashboard.set_headline_alert(
                `Skill Match: ${result.readiness_percent}% — ` +
                `✅ ${result.matched_skills.length} matched, ` +
                `⚠️ ${result.partial_skills.length} partial, ` +
                `❌ ${result.missing_skills.length} missing`,
                color
            );
        },
    });
}


// ─────────────────────────────────────────────────────────────────────────────
// SKILL GAP DIALOG — shows ALL skills (matched + partial + missing)
//                    Enroll button is ALWAYS available
// ─────────────────────────────────────────────────────────────────────────────

function _show_skill_gap_dialog(frm, result) {

    function skill_row(s, type) {
        const CFG = {
            matched : { color:"#52c41a", bg:"#f6ffed", border:"#b7eb8f", icon:"✅", label:"Matched"  },
            partial : { color:"#fa8c16", bg:"#fff7e6", border:"#ffd591", icon:"⚠️", label:"Partial"  },
            missing : { color:"#ff4d4f", bg:"#fff1f0", border:"#ffa39e", icon:"❌", label:"Missing"  },
        }[type];

        const prereq_tag = s.is_prereq
            ? `<span style="background:#fff7e6;color:#d46b08;border:1px solid #ffd591;
                border-radius:10px;font-size:10px;padding:1px 6px;margin-left:4px;">Prereq</span>`
            : "";

        let path_btn = "";
        if (type !== "matched" && s.recommended_path) {
            path_btn = `<button class="btn btn-xs btn-primary open-path-btn mt-1"
                data-path="${s.recommended_path.path_name}" style="font-size:11px;margin-top:4px;">
                📚 ${s.recommended_path.display_name || s.recommended_path.path_name}
                ${s.recommended_path.duration_months ? ` · ${s.recommended_path.duration_months}mo` : ""}
                ${s.recommended_path.difficulty ? ` · ${s.recommended_path.difficulty}` : ""}
            </button>`;
        }

        return `
        <li style="margin-bottom:8px;padding:10px 12px;
            border-left:3px solid ${CFG.color};background:${CFG.bg};
            border:1px solid ${CFG.border};list-style:none;border-radius:6px;">
            <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:4px;">
                <span style="font-weight:600;font-size:13px;">
                    ${CFG.icon} ${s.skill} ${prereq_tag}
                </span>
                <span style="background:${CFG.bg};color:${CFG.color};border:1px solid ${CFG.border};
                    border-radius:10px;font-size:11px;font-weight:600;padding:1px 8px;">
                    ${CFG.label}
                </span>
            </div>
            <div style="margin-top:4px;font-size:11px;color:#595959;">
                Required: <b>${s.required_level}</b>
                &nbsp;→&nbsp;
                Current: <b style="color:${CFG.color}">${s.current_level || "Not started"}</b>
            </div>
            ${path_btn}
        </li>`;
    }

    const matched_skills = result.matched_skills || [];
    const partial_skills = result.partial_skills || [];
    const missing_skills = result.missing_skills || [];
    const total          = matched_skills.length + partial_skills.length + missing_skills.length;
    const pct            = result.readiness_percent || 0;
    const bar_color      = pct >= 75 ? "#52c41a" : pct >= 50 ? "#fa8c16" : "#ff4d4f";
    const bar_label      = pct >= 75 ? "Great fit!" : pct >= 50 ? "Moderate fit" : "Skill gaps present — you can still enroll";

    const matched_html = matched_skills.length ? `
        <h5 style="color:#52c41a;margin:12px 0 6px;">✅ Skills You Have (${matched_skills.length})</h5>
        <ul style="padding:0;margin:0;">${matched_skills.map(s => skill_row(s, "matched")).join("")}</ul>
    ` : "";

    const partial_html = partial_skills.length ? `
        <h5 style="color:#fa8c16;margin:12px 0 6px;">⚠️ Needs Improvement (${partial_skills.length})</h5>
        <ul style="padding:0;margin:0;">${partial_skills.map(s => skill_row(s, "partial")).join("")}</ul>
    ` : "";

    const missing_html = missing_skills.length ? `
        <h5 style="color:#ff4d4f;margin:12px 0 6px;">❌ Missing Skills (${missing_skills.length})</h5>
        <ul style="padding:0;margin:0;">${missing_skills.map(s => skill_row(s, "missing")).join("")}</ul>
    ` : "";

    // Collect prereq paths for auto-prepend
    const prereq_paths = [...new Map(
        [...partial_skills, ...missing_skills]
            .filter(s => s.recommended_path)
            .map(s => [s.recommended_path.path_name, s.recommended_path.path_name])
    ).values()];

    const dialog = new frappe.ui.Dialog({
        title : `📊 Skill Match — ${frm.doc.career_path || ""}`,
        size  : "large",
        fields: [{
            fieldtype: "HTML",
            options  : `
            <div style="padding:10px 4px;">
                <!-- Summary chips -->
                <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
                    <span style="background:#f6ffed;color:#52c41a;border:1px solid #b7eb8f;
                        border-radius:10px;font-size:12px;padding:2px 12px;font-weight:600;">
                        ✅ Matched: ${matched_skills.length}
                    </span>
                    <span style="background:#fff7e6;color:#fa8c16;border:1px solid #ffd591;
                        border-radius:10px;font-size:12px;padding:2px 12px;font-weight:600;">
                        ⚠️ Partial: ${partial_skills.length}
                    </span>
                    <span style="background:#fff1f0;color:#ff4d4f;border:1px solid #ffa39e;
                        border-radius:10px;font-size:12px;padding:2px 12px;font-weight:600;">
                        ❌ Missing: ${missing_skills.length}
                    </span>
                    <span style="background:#f5f5f5;color:#595959;border:1px solid #d9d9d9;
                        border-radius:10px;font-size:12px;padding:2px 12px;">
                        Total: ${total}
                    </span>
                </div>

                <!-- Readiness bar -->
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">
                    <span style="font-size:12px;color:#595959;">Skill Readiness</span>
                    <span style="font-weight:700;color:${bar_color};font-size:14px;">${pct}%</span>
                </div>
                <div style="background:#e0e0e0;border-radius:10px;height:10px;margin-bottom:4px;">
                    <div style="width:${pct}%;background:${bar_color};height:10px;border-radius:10px;transition:width .4s;"></div>
                </div>
                <p style="font-size:11px;color:${bar_color};font-weight:600;margin-bottom:12px;">${bar_label}</p>

                <hr style="margin:8px 0;">
                ${missing_html}
                ${partial_html}
                ${matched_html}
                <hr style="margin:12px 0 8px;">

                <!-- Always-visible enroll note -->
                <div style="background:#e6f7ff;border:1px solid #91d5ff;border-radius:6px;
                    padding:10px;font-size:12px;color:#0050b3;">
                    💡 You can <b>enroll regardless of readiness score</b>.<br>
                    Prerequisite skill milestones will be automatically added
                    <b>before</b> the main path milestones in your learning journey.
                </div>
            </div>`,
        }],

        // Always enabled — no blocking on readiness
        primary_action_label: "✅ Enroll in this Path",
        primary_action() {
            dialog.hide();
            _do_enroll(frm, prereq_paths);
        },

        secondary_action_label: "Go Back",
        secondary_action() {
            frm.set_value("career_path", "");
            dialog.hide();
        },
    });

    dialog.show();

    setTimeout(() => {
        dialog.$wrapper.find(".open-path-btn").on("click", function() {
            const pn = $(this).data("path");
            if (pn) { frappe.set_route("Form", "Career Path", pn); dialog.hide(); }
        });
    }, 250);
}


// ─────────────────────────────────────────────────────────────────────────────
// ENROLL
// ─────────────────────────────────────────────────────────────────────────────

function _do_enroll(frm, prereq_paths) {
    frappe.call({
        method        : API.ENROLL,
        args          : {
            student     : frm.doc.student,
            career_path : frm.doc.career_path,
            force_enroll: 1,
            prereq_paths: JSON.stringify(prereq_paths || []),
        },
        freeze        : true,
        freeze_message: "Setting up your learning path…",
        callback(r) {
            if (!r.message) return;
            if (r.message.status === "already_enrolled") {
                frappe.show_alert({
                    message  : "⚠️ Already enrolled in this path.",
                    indicator: "orange",
                });
                frappe.set_route("Form", "Student Path Enrollment", r.message.enrollment);
                return;
            }
            if (r.message.status === "success") {
                frappe.show_alert({
                    message  : "✅ Enrolled! Prerequisite milestones added automatically.",
                    indicator: "green",
                });
                frappe.set_route("Form", "Student Path Enrollment", r.message.enrollment);
            }
        },
    });
}


// ─────────────────────────────────────────────────────────────────────────────
// MILESTONE COUNT BAR
// Shows: "4 Prereqs + 11 Milestones = 15 Total | 5 Completed (33%)"
// ─────────────────────────────────────────────────────────────────────────────

function _render_count_bar(frm) {
    if (frm.is_new() || !frm.doc.career_path) return;

    const $field = frm.fields_dict["milestone_board_html"] || frm.fields_dict["count_bar_html"];
    if (!$field) return;

    frappe.call({
        method  : API.COUNT_SUMMARY,
        args    : { enrollment: frm.doc.name },
        callback(r) {
            if (!r.message) return;
            const d = r.message;

            const bar_pct   = d.completion_percent || 0;
            const bar_color = bar_pct >= 100 ? "#52c41a" : bar_pct >= 60 ? "#1890ff" : "#faad14";

            const count_html = `
            <div style="
                background:#fafafa;border:1px solid #e8e8e8;border-radius:8px;
                padding:12px 16px;margin-bottom:12px;">
                <div style="display:flex;justify-content:space-between;align-items:center;
                    flex-wrap:wrap;gap:8px;margin-bottom:8px;">
                    <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
                        <span style="background:#fff7e6;color:#d46b08;border:1px solid #ffd591;
                            border-radius:10px;font-size:12px;padding:3px 12px;font-weight:600;">
                            📋 Prereqs: ${d.prereq_completed}/${d.prereq_count}
                        </span>
                        <span style="color:#595959;font-size:14px;font-weight:600;">+</span>
                        <span style="background:#e6f7ff;color:#096dd9;border:1px solid #91d5ff;
                            border-radius:10px;font-size:12px;padding:3px 12px;font-weight:600;">
                            🗺️ Milestones: ${d.path_completed}/${d.path_count}
                        </span>
                        <span style="color:#595959;font-size:14px;font-weight:600;">=</span>
                        <span style="background:#f5f5f5;color:#262626;border:1px solid #d9d9d9;
                            border-radius:10px;font-size:12px;padding:3px 12px;font-weight:700;">
                            Total: ${d.completed_count}/${d.total_count}
                        </span>
                    </div>
                    <span style="font-weight:700;color:${bar_color};font-size:16px;">
                        ${bar_pct}%
                    </span>
                </div>
                <div style="background:#e0e0e0;border-radius:10px;height:10px;overflow:hidden;">
                    <div style="width:${bar_pct}%;background:${bar_color};height:10px;
                        border-radius:10px;transition:width .5s;"></div>
                </div>
            </div>`;

            // Prepend count bar, then board will render below
            $field.$wrapper.find(".count-bar-section").remove();
            $field.$wrapper.prepend(`<div class="count-bar-section">${count_html}</div>`);
        },
    });
}


// ─────────────────────────────────────────────────────────────────────────────
// CUSTOM BUTTONS
// ─────────────────────────────────────────────────────────────────────────────

function _setup_custom_buttons(frm) {
    if (frm.is_new()) {
        frm.add_custom_button(__("Check Skills & Enroll"), () => _handle_enroll_click(frm));
        return;
    }

    if (frm.doc.status === "Active") {
        frm.add_custom_button(__("View Journey"), () => _show_milestone_dialog(frm), __("Path"));
        frm.add_custom_button(__("Skip Current"), () => _skip_current(frm), __("Path"));
        frm.add_custom_button(__("Skill Match"), () => {
            frappe.call({
                method  : API.CHECK_PREREQS,
                args    : { student: frm.doc.student, career_path: frm.doc.career_path },
                callback(r) {
                    if (r.message) _show_skill_gap_dialog(frm, r.message);
                },
            });
        }, __("Path"));
        frm.add_custom_button(__("Path Suggestions"), () => _show_path_suggestions(frm), __("Path"));
    }
}

function _handle_enroll_click(frm) {
    if (!frm.doc.student || !frm.doc.career_path) {
        frappe.msgprint("Please select both Student and Career Path first.");
        return;
    }

    frappe.call({
        method  : API.CHECK_PREREQS,
        args    : { student: frm.doc.student, career_path: frm.doc.career_path },
        callback(r) {
            if (r.message) _show_skill_gap_dialog(frm, r.message);
        },
    });
}


// ─────────────────────────────────────────────────────────────────────────────
// PATH SUGGESTIONS DIALOG (Fit Score based top 5)
// ─────────────────────────────────────────────────────────────────────────────

function _show_path_suggestions(frm) {
    frappe.call({
        method  : API.SUGGESTIONS,
        args    : { student: frm.doc.student, limit: 5 },
        freeze  : true,
        freeze_message: "Calculating fit scores…",
        callback(r) {
            if (!r.message || !r.message.length) {
                frappe.msgprint("No path suggestions found.");
                return;
            }

            const cards = r.message.map((p, i) => {
                const score_color = p.fit_score >= 75 ? "#52c41a"
                                  : p.fit_score >= 50 ? "#fa8c16"
                                  :                    "#ff4d4f";
                const rank_emoji  = ["🥇","🥈","🥉","4️⃣","5️⃣"][i] || `#${i+1}`;

                const skill_chips = (p.skill_tags || []).map(t => {
                    const c = t.status === "matched" ? "#52c41a"
                            : t.status === "partial" ? "#fa8c16"
                            :                          "#ff4d4f";
                    return `<span style="background:#f5f5f5;color:${c};border:1px solid ${c};
                        border-radius:10px;font-size:10px;padding:1px 7px;margin:2px;">${t.skill}</span>`;
                }).join("");

                return `
                <div style="border:1px solid #e8e8e8;border-radius:8px;padding:14px;
                    margin-bottom:10px;background:#fafafa;
                    border-left:4px solid ${score_color};">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;flex-wrap:wrap;">
                        <div>
                            <span style="font-size:14px;font-weight:700;">
                                ${rank_emoji} ${p.path_name || p.career_path}
                            </span>
                            <span style="font-size:12px;color:#595959;margin-left:8px;">
                                ${p.target_role || ""}
                            </span>
                        </div>
                        <div style="text-align:right;">
                            <span style="font-size:20px;font-weight:800;color:${score_color};">
                                ${p.fit_score}%
                            </span>
                            <br>
                            <span style="font-size:10px;color:#8c8c8c;">Fit Score</span>
                        </div>
                    </div>
                    <div style="margin:6px 0;display:flex;gap:6px;flex-wrap:wrap;font-size:11px;color:#595959;">
                        ${p.difficulty_level ? `<span>⚡ ${p.difficulty_level}</span>` : ""}
                        ${p.estimated_duration ? `<span>⏱ ${p.estimated_duration}mo</span>` : ""}
                        ${p.average_salary ? `<span>💰 ₹${p.average_salary}L</span>` : ""}
                        <span>✅ ${p.matched_count} matched &nbsp; ⚠️ ${p.partial_count} partial &nbsp; ❌ ${p.missing_count} missing</span>
                    </div>
                    <div style="display:flex;flex-wrap:wrap;gap:2px;margin-top:6px;">${skill_chips}</div>
                    <div style="margin-top:8px;">
                        <button class="btn btn-xs btn-primary enroll-suggest-btn"
                            data-path="${p.career_path}" style="font-size:11px;">
                            Enroll in this Path
                        </button>
                    </div>
                </div>`;
            }).join("");

            const dialog = new frappe.ui.Dialog({
                title : `🎯 Career Path Suggestions for ${frm.doc.student}`,
                size  : "large",
                fields: [{
                    fieldtype: "HTML",
                    options  : `<div style="padding:8px;">${cards}</div>`,
                }],
            });
            dialog.show();

            setTimeout(() => {
                dialog.$wrapper.find(".enroll-suggest-btn").on("click", function() {
                    const path = $(this).data("path");
                    dialog.hide();
                    frm.set_value("career_path", path);
                    frappe.call({
                        method  : API.CHECK_PREREQS,
                        args    : { student: frm.doc.student, career_path: path },
                        callback(r) {
                            if (r.message) _show_skill_gap_dialog(frm, r.message);
                        },
                    });
                });
            }, 200);
        },
    });
}


// ─────────────────────────────────────────────────────────────────────────────
// MILESTONE JOURNEY BOARD (inline HTML field on form)
// Shows: Prereq section (collapsible) then Path Milestone section
// ─────────────────────────────────────────────────────────────────────────────

function _render_milestone_board(frm) {
    if (frm.is_new() || !frm.doc.career_path) return;

    const $field = frm.fields_dict["milestone_board_html"];
    if (!$field) return;

    frappe.call({
        method  : API.OVERVIEW,
        args    : { enrollment: frm.doc.name },
        callback(r) {
            if (!r.message) return;
            const html = _build_board_html(r.message);
            $field.$wrapper.find(".board-section").remove();
            $field.$wrapper.append(`<div class="board-section">${html}</div>`);
            _bind_board_actions(frm, $field.$wrapper);
        },
    });
}

function _build_board_html(data) {
    const STATUS = {
        "Completed"  : { icon: "✅", color: "#52c41a", bg: "#f6ffed", border: "#b7eb8f" },
        "In Progress": { icon: "⏳", color: "#1890ff", bg: "#e6f7ff", border: "#91d5ff" },
        "Skipped"    : { icon: "⏭️", color: "#8c8c8c", bg: "#f5f5f5", border: "#d9d9d9" },
        "Not Started": { icon: "⭕", color: "#bfbfbf", bg: "#fafafa", border: "#e8e8e8" },
    };

    const TYPE_ICONS = {
        Learn:"📖", Build:"🏗️", Assess:"📝", Connect:"🤝", Apply:"🚀",
    };

    const prereq_rows = data.milestones.filter(m => m.is_prereq);
    const path_rows   = data.milestones.filter(m => !m.is_prereq);

    function card(m, idx_label) {
        const cfg        = STATUS[m.status] || STATUS["Not Started"];
        const type_icon  = TYPE_ICONS[m.milestone_type] || "📌";
        const auto_badge = m.is_auto_skipped
            ? `<span style="background:#f9f0ff;color:#531dab;border:1px solid #d3adf7;
                border-radius:4px;font-size:10px;padding:1px 5px;margin-left:4px;">Auto ✓</span>`
            : "";
        const current_badge = m.is_current
            ? `<span style="background:#e6f7ff;color:#096dd9;border:1px solid #91d5ff;
                border-radius:4px;font-size:10px;padding:1px 5px;margin-left:4px;">Current</span>`
            : "";

        const actions = (!m.is_lock && m.status !== "Completed" && m.is_skippable)
            ? `<div style="margin-top:6px;">
                <button class="btn btn-xs btn-warning board-skip-btn"
                    data-row="${m.row_name}" style="font-size:11px;">⏭️ Skip</button>
               </div>`
            : "";

        return `
        <div style="display:flex;align-items:flex-start;gap:10px;
            background:${cfg.bg};border:1px solid ${cfg.border};border-radius:8px;
            padding:10px 12px;margin-bottom:6px;
            ${m.is_current ? "border-left:4px solid #1890ff;" : ""}">
            <div style="font-size:18px;min-width:26px;text-align:center;padding-top:2px;">
                ${m.is_lock ? "🔒" : cfg.icon}
            </div>
            <div style="flex:1;min-width:0;">
                <div style="display:flex;align-items:center;flex-wrap:wrap;gap:2px;">
                    <span style="font-weight:600;font-size:13px;">
                        ${idx_label}. ${type_icon} ${m.milestone_title}
                    </span>
                    ${auto_badge}${current_badge}
                </div>
                <div style="margin-top:4px;display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                    <span style="color:${cfg.color};font-weight:600;font-size:12px;
                        background:${cfg.bg};border:1px solid ${cfg.border};
                        border-radius:10px;padding:1px 8px;">
                        ${cfg.icon} ${m.status}
                    </span>
                    ${m.skill ? `<span style="font-size:11px;color:#595959;">🔧 ${m.skill}</span>` : ""}
                    ${m.required_skill_level ? `<span style="font-size:11px;color:#8c8c8c;">${m.required_skill_level}</span>` : ""}
                    ${m.score != null ? `<span style="font-size:11px;color:#595959;">Score: ${m.score}</span>` : ""}
                    ${m.completed_on ? `<span style="font-size:11px;color:#8c8c8c;">Done: ${m.completed_on}</span>` : ""}
                </div>
                ${actions}
            </div>
        </div>`;
    }

    // Prereq section
    let prereq_section = "";
    if (prereq_rows.length) {
        const prereq_cards = prereq_rows.map((m, i) => card(m, i + 1)).join("");
        const prereq_done  = prereq_rows.filter(m => m.status === "Completed").length;
        prereq_section = `
        <div style="margin-bottom:14px;">
            <div style="font-weight:700;font-size:13px;color:#d46b08;margin-bottom:8px;
                display:flex;align-items:center;gap:6px;">
                📋 Prerequisite Skills
                <span style="background:#fff7e6;color:#d46b08;border:1px solid #ffd591;
                    border-radius:10px;font-size:11px;padding:1px 8px;">
                    ${prereq_done}/${prereq_rows.length} completed
                </span>
            </div>
            ${prereq_cards}
        </div>`;
    }

    // Path milestones section
    let path_section = "";
    if (path_rows.length) {
        const path_cards = path_rows.map((m, i) => card(m, (prereq_rows.length) + i + 1)).join("");
        const path_done  = path_rows.filter(m => m.status === "Completed").length;
        path_section = `
        <div>
            <div style="font-weight:700;font-size:13px;color:#096dd9;margin-bottom:8px;
                display:flex;align-items:center;gap:6px;">
                🗺️ Path Milestones
                <span style="background:#e6f7ff;color:#096dd9;border:1px solid #91d5ff;
                    border-radius:10px;font-size:11px;padding:1px 8px;">
                    ${path_done}/${path_rows.length} completed
                </span>
            </div>
            ${path_cards}
        </div>`;
    }

    const chips = Object.entries(data.status_counts || {}).map(([s, c]) => {
        const cfg = STATUS[s] || STATUS["Not Started"];
        return `<span style="display:inline-flex;align-items:center;gap:4px;
            background:${cfg.bg};color:${cfg.color};border:1px solid ${cfg.border};
            border-radius:12px;padding:2px 10px;font-size:12px;font-weight:600;
            margin-right:6px;margin-bottom:4px;">
            ${cfg.icon} ${s}: ${c}
        </span>`;
    }).join("");

    return `
    <div style="padding:8px 0;">
        <div style="margin-bottom:10px;">${chips}</div>
        ${prereq_section}
        ${path_section}
    </div>`;
}

function _bind_board_actions(frm, $wrapper) {
    $wrapper.find(".board-skip-btn").on("click", function() {
        const row_name = $(this).data("row");
        frappe.confirm("Skip this milestone?", () => _do_skip(frm, row_name));
    });
}

function _do_skip(frm, row_name) {
    frappe.call({
        method  : API.SKIP,
        args    : { enrollment: frm.doc.name, row_name },
        callback(r) {
            if (r.message && r.message.success) {
                frappe.show_alert({ message: "Milestone skipped.", indicator: "orange" });
                frm.reload_doc();
            }
        },
    });
}


// ─────────────────────────────────────────────────────────────────────────────
// MILESTONE JOURNEY DIALOG (full table view)
// ─────────────────────────────────────────────────────────────────────────────

function _show_milestone_dialog(frm) {
    frappe.call({
        method  : API.OVERVIEW,
        args    : { enrollment: frm.doc.name },
        callback(r) {
            if (!r.message) return;
            const data = r.message;

            const S_ICON  = { "Completed":"✅","In Progress":"⏳","Skipped":"⏭️","Not Started":"⭕" };
            const S_COLOR = { "Completed":"#52c41a","In Progress":"#1890ff","Skipped":"#8c8c8c","Not Started":"#bfbfbf" };

            const rows = data.milestones.map((m, i) => `
                <tr style="${m.is_current?"background:#e6f7ff;":""}${m.is_lock?"opacity:0.55;":""}">
                    <td style="text-align:center;font-weight:700;">${i + 1}</td>
                    <td>
                        ${m.is_prereq
                            ? `<span style="background:#fff7e6;color:#d46b08;border-radius:3px;
                                font-size:10px;padding:1px 5px;margin-right:4px;">P</span>`
                            : ""}
                        <strong>${m.milestone_title}</strong>
                        ${m.is_current ? " 👈" : ""}${m.is_lock ? " 🔒" : ""}
                        ${m.is_auto_skipped ? " 🤖" : ""}
                    </td>
                    <td>${m.milestone_type || "-"}</td>
                    <td style="color:${S_COLOR[m.status]||"#bfbfbf"};font-weight:600;">
                        ${S_ICON[m.status]||"⭕"} ${m.status}
                    </td>
                    <td>${m.skill || "-"}</td>
                    <td>${m.score != null ? m.score : "-"}</td>
                    <td>${m.completed_on || "-"}</td>
                    <td>
                        ${m.is_skippable && !m.is_lock && m.status !== "Completed"
                            ? `<button class="btn btn-xs btn-warning dlg-skip-btn"
                                data-row="${m.row_name}">Skip</button>`
                            : "-"}
                    </td>
                </tr>`).join("");

            const pct = data.completion_percent || 0;
            const dialog = new frappe.ui.Dialog({
                title : `🗺️ Milestone Journey — ${frm.doc.career_path}`,
                size  : "extra-large",
                fields: [{
                    fieldtype: "HTML",
                    options  : `
                    <div style="padding:10px;">
                        <div style="background:#f0f0f0;border-radius:10px;height:12px;
                            margin-bottom:10px;overflow:hidden;">
                            <div style="width:${pct}%;background:#1890ff;height:12px;
                                border-radius:10px;display:flex;align-items:center;
                                justify-content:center;color:#fff;font-size:9px;font-weight:700;">
                                ${pct > 10 ? pct + "%" : ""}
                            </div>
                        </div>
                        <div style="margin-bottom:8px;font-size:12px;color:#595959;">
                            📋 Prereqs: ${data.prereq_completed}/${data.prereq_count} &nbsp;|&nbsp;
                            🗺️ Milestones: ${data.path_completed}/${data.path_count} &nbsp;|&nbsp;
                            Total: ${data.completed_count}/${data.total_count}
                            &nbsp;|&nbsp; 🤖 = Auto-completed (skill already verified)
                        </div>
                        <div style="max-height:450px;overflow-y:auto;">
                            <table class="table table-sm table-bordered table-hover" style="font-size:12px;">
                                <thead class="thead-light">
                                    <tr>
                                        <th>#</th><th>Milestone</th><th>Type</th>
                                        <th>Status</th><th>Skill</th><th>Score</th>
                                        <th>Completed</th><th>Action</th>
                                    </tr>
                                </thead>
                                <tbody>${rows}</tbody>
                            </table>
                        </div>
                        <p class="text-muted" style="font-size:11px;margin-top:6px;">
                            P = Prereq &nbsp;|&nbsp; 🔒 = Locked &nbsp;|&nbsp;
                            👈 = Current &nbsp;|&nbsp; 🤖 = Auto-completed
                        </p>
                    </div>`,
                }],
            });
            dialog.show();

            setTimeout(() => {
                dialog.$wrapper.find(".dlg-skip-btn").on("click", function() {
                    const row_name = $(this).data("row");
                    frappe.confirm("Skip this milestone?", () => {
                        dialog.hide();
                        _do_skip(frm, row_name);
                    });
                });
            }, 200);
        },
    });
}


// ─────────────────────────────────────────────────────────────────────────────
// MILESTONE GRID ROW COLORS
// ─────────────────────────────────────────────────────────────────────────────

function _color_milestone_grid_rows(frm) {
    const STATUS_COLORS = {
        "Completed"  : "#f6ffed",
        "In Progress": "#e6f7ff",
        "Skipped"    : "#f5f5f5",
        "Not Started": "#ffffff",
    };

    frm.fields_dict.milestone_progress?.grid?.wrapper
        .find(".grid-row")
        .each(function() {
            const $row = $(this);
            const text = $row.text();
            let bg     = "#ffffff";
            for (const [s, c] of Object.entries(STATUS_COLORS)) {
                if (text.includes(s)) { bg = c; break; }
            }
            $row.css("background-color", bg);
            if (text.includes("🔒")) $row.css("border-left", "3px solid #ff4d4f");
        });
}


// ─────────────────────────────────────────────────────────────────────────────
// COMPLETION HEADER BAR (inline progress on completion_percent field)
// ─────────────────────────────────────────────────────────────────────────────

function _render_completion_header(frm) {
    if (frm.is_new()) return;

    const pct   = frm.doc.completion_percent || 0;
    const color = pct >= 100 ? "#52c41a" : pct >= 60 ? "#1890ff" : "#faad14";
    const label = pct >= 100 ? "🎉 Path Completed!" : `${pct}% Progress`;

    const $f = frm.fields_dict["completion_percent"];
    if (!$f) return;

    $f.$wrapper.find(".progress-inline").remove();
    $f.$wrapper.append(`
        <div class="progress-inline" style="margin-top:4px;">
            <div style="background:#f0f0f0;border-radius:8px;height:10px;overflow:hidden;">
                <div style="width:${pct}%;background:${color};height:10px;border-radius:8px;
                    transition:width .5s;display:flex;align-items:center;
                    justify-content:center;font-size:9px;color:#fff;font-weight:700;">
                    ${pct > 20 ? label : ""}
                </div>
            </div>
            ${pct <= 20 ? `<small style="color:${color};font-weight:600;">${label}</small>` : ""}
        </div>`);
}


// ─────────────────────────────────────────────────────────────────────────────
// SKIP CURRENT MILESTONE (button shortcut)
// ─────────────────────────────────────────────────────────────────────────────

function _skip_current(frm) {
    frappe.call({
        method  : API.OVERVIEW,
        args    : { enrollment: frm.doc.name },
        callback(r) {
            if (!r.message) return;
            const current = r.message.milestones.find(m => m.is_current);
            if (!current) { frappe.msgprint("No active milestone found."); return; }
            if (!current.is_skippable) {
                frappe.msgprint({
                    title    : "Cannot Skip",
                    message  : `Milestone <b>${current.milestone_title}</b> is mandatory.`,
                    indicator: "red",
                });
                return;
            }
            frappe.confirm(
                `Skip: <b>${current.milestone_title}</b>?`,
                () => _do_skip(frm, current.row_name)
            );
        },
    });
}