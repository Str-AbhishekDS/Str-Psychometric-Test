// Copyright (c) 2026, Stride nex and contributors
// For license information, please see license.txt
//
// student_path_enrollment.js
// ─────────────────────────────────────────────────────────────────────────────
// Handles:
//  1. Prerequisite skill check on student / career_path change
//  2. Skill Gap dialog with readiness bar + recommended paths
//  3. "Enroll Anyway" flow → auto-prepends prereq milestones
//  4. Milestone Journey board (inline on the form)
//  5. Per-row color coding on milestone_progress grid
// ─────────────────────────────────────────────────────────────────────────────

const API = {
    ENROLL        : "nexedu.path_finder.api.path_enrollment.enroll_student",
    CHECK_PREREQS : "nexedu.path_finder.api.path_enrollment.check_prerequisite_skills",
    OVERVIEW      : "nexedu.path_finder.api.path_enrollment.get_milestone_overview",
    SKIP          : "nexedu.path_finder.api.path_enrollment.skip_milestone",
    GET_ENROLLMENT: "nexedu.path_finder.api.path_enrollment.get_enrollment_for_student_path",
};

// ─────────────────────────────────────────────────────────────────────────────
// FORM EVENTS
// ─────────────────────────────────────────────────────────────────────────────

frappe.ui.form.on("Student Path Enrollment", {

    setup(frm) {
        // Nothing here; moved to refresh for safety
    },

    refresh(frm) {
        _setup_custom_buttons(frm);
        _color_milestone_grid_rows(frm);
        _render_milestone_board(frm);
        _render_completion_header(frm);
    },

    career_path(frm) {
        _run_prerequisite_check(frm);
    },

    student(frm) {
        _run_prerequisite_check(frm);
    },

    // Color milestone_progress grid on child row change
    milestone_progress_on_form_rendered(frm) {
        _color_milestone_grid_rows(frm);
    },
});


// ─────────────────────────────────────────────────────────────────────────────
// PREREQUISITE CHECK
// ─────────────────────────────────────────────────────────────────────────────

function _run_prerequisite_check(frm) {
    if (!frm.doc.student || !frm.doc.career_path) return;
    // Only run on new unsaved docs to avoid annoying re-checks
    if (!frm.is_new()) return;

    frm.dashboard.clear_headline();
    frm.dashboard.set_headline_alert("🔍 Checking prerequisites...", "yellow");

    frappe.call({
        method  : API.CHECK_PREREQS,
        args    : { student: frm.doc.student, career_path: frm.doc.career_path },
        callback: function(r) {
            if (!r.message) return;
            const result = r.message;
            frm.dashboard.clear_headline();

            if (result.status === "clear") {
                frm.dashboard.set_headline_alert(
                    `✅ All prerequisites met — Readiness: ${result.readiness_percent}%`,
                    "green"
                );
            } else {
                _show_skill_gap_dialog(frm, result);
            }
        },
    });
}


// ─────────────────────────────────────────────────────────────────────────────
// SKILL GAP DIALOG
// ─────────────────────────────────────────────────────────────────────────────

function _show_skill_gap_dialog(frm, result) {

    // ── Build skill rows ─────────────────────────────────────────────────────
    function skill_row(s, type) {
        const color = type === "missing" ? "#ff4d4f" : "#fa8c16";
        const icon  = type === "missing" ? "❌" : "⚠️";

        let path_btn = s.recommended_path
            ? `<button
                   class="btn btn-xs btn-primary open-path-btn mt-1"
                   data-path="${s.recommended_path.path_name}">
                   📚 ${s.recommended_path.display_name || s.recommended_path.path_name}
                   ${s.recommended_path.duration_months ? ` · ${s.recommended_path.duration_months}mo` : ""}
                   ${s.recommended_path.difficulty      ? ` · ${s.recommended_path.difficulty}`       : ""}
               </button>`
            : `<span class="text-muted" style="font-size:11px">No recommended path linked yet</span>`;

        return `
        <li style="
            margin-bottom:10px; padding:10px;
            border-left:3px solid ${color};
            background:#fafafa; list-style:none; border-radius:4px;">
            <div>${icon} <b>${s.skill}</b>
                &nbsp;·&nbsp; Required: <b>${s.required_level}</b>
                &nbsp;·&nbsp; Current: <b>${s.current_level || "Not started"}</b>
            </div>
            <div>${path_btn}</div>
        </li>`;
    }

    let missing_html = "";
    if (result.missing_skills.length) {
        missing_html = `
            <h5 style="color:#ff4d4f; margin-top:10px">
                ❌ Missing Skills (${result.missing_skills.length})
            </h5>
            <ul style="padding:0">
                ${result.missing_skills.map(s => skill_row(s, "missing")).join("")}
            </ul>`;
    }

    let partial_html = "";
    if (result.partial_skills.length) {
        partial_html = `
            <h5 style="color:#fa8c16; margin-top:10px">
                ⚠️ Needs Improvement (${result.partial_skills.length})
            </h5>
            <ul style="padding:0">
                ${result.partial_skills.map(s => skill_row(s, "partial")).join("")}
            </ul>`;
    }

    const bar_color = result.readiness_percent >= 75 ? "#52c41a"
                    : result.readiness_percent >= 50 ? "#fa8c16"
                    :                                  "#ff4d4f";

    const can_enroll = result.readiness_percent >= 50;

    // Collect prereq path names from recommendations
    const all_gap_skills = [...result.missing_skills, ...result.partial_skills];
    const prereq_paths   = [...new Map(
        all_gap_skills
            .filter(s => s.recommended_path)
            .map(s => [s.recommended_path.path_name, s.recommended_path.path_name])
    ).values()];

    const dialog = new frappe.ui.Dialog({
        title : "📋 Skill Gap Analysis",
        size  : "large",
        fields: [{
            fieldtype: "HTML",
            options  : `
            <div style="padding:10px">
                <h4>
                    Readiness Score:
                    <span style="color:${bar_color}">${result.readiness_percent}%</span>
                    <small style="color:grey; font-size:13px">
                        (${result.matched} / ${result.total_prerequisites} matched)
                    </small>
                </h4>
                <div style="background:#e0e0e0; border-radius:10px; height:10px; margin-bottom:15px;">
                    <div style="
                        width:${result.readiness_percent}%; background:${bar_color};
                        height:10px; border-radius:10px; transition:width .4s;">
                    </div>
                </div>
                ${missing_html}
                ${partial_html}
                <hr>
                <div style="background:#fffbe6; border:1px solid #ffe58f; border-radius:6px; padding:10px; margin-top:8px;">
                    💡 Clicking <b>"Enroll Anyway"</b> will automatically add the
                    prerequisite path milestones <em>before</em> the main path milestones
                    in your learning journey.
                </div>
            </div>`,
        }],

        primary_action_label: can_enroll ? "Enroll Anyway" : "Go Back & Build Skills First",
        primary_action() {
            dialog.hide();
            if (!can_enroll) {
                frm.set_value("career_path", "");
                return;
            }
            // Trigger enrollment with prereq paths auto-prepended
            _do_enroll(frm, prereq_paths);
        },

        secondary_action_label: can_enroll ? "Go Back" : null,
        secondary_action() {
            frm.set_value("career_path", "");
            dialog.hide();
        },
    });

    dialog.show();

    // Attach path navigation buttons after DOM renders
    setTimeout(() => {
        dialog.$wrapper.find(".open-path-btn").on("click", function() {
            const path_name = $(this).data("path");
            if (path_name) {
                frappe.set_route("Form", "Career Path", path_name);
                dialog.hide();
            }
        });
    }, 250);
}


// ─────────────────────────────────────────────────────────────────────────────
// ENROLL (called when form is new, after skill gap dialog)
// ─────────────────────────────────────────────────────────────────────────────

function _do_enroll(frm, prereq_paths) {
    frappe.call({
        method  : API.ENROLL,
        args    : {
            student      : frm.doc.student,
            career_path  : frm.doc.career_path,
            force_enroll : 1,
            prereq_paths : JSON.stringify(prereq_paths),
        },
        freeze        : true,
        freeze_message: "Setting up your learning path…",
        callback(r) {
            if (r.message && r.message.status === "success") {
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
// CUSTOM BUTTONS
// ─────────────────────────────────────────────────────────────────────────────

function _setup_custom_buttons(frm) {
    if (frm.is_new()) {
        frm.add_custom_button(__("Enroll"), () => _handle_enroll_click(frm));
        return;
    }

    if (frm.doc.status === "Active") {
        frm.add_custom_button(__("View Journey"), () => _show_milestone_dialog(frm), __("Path"));
        frm.add_custom_button(__("Skip Current Milestone"), () => _skip_current(frm), __("Path"));
        frm.add_custom_button(__("Re-check Prerequisites"), () => {
            frm.doc.__islocal = true; // force re-check
            _run_prerequisite_check(frm);
            frm.doc.__islocal = false;
        }, __("Path"));
    }
}

function _handle_enroll_click(frm) {
    if (!frm.doc.student || !frm.doc.career_path) {
        frappe.msgprint("Please select both Student and Career Path first.");
        return;
    }

    // Check prereqs first, then enroll
    frappe.call({
        method  : API.CHECK_PREREQS,
        args    : { student: frm.doc.student, career_path: frm.doc.career_path },
        callback(r) {
            if (!r.message) return;
            const result = r.message;

            if (result.status === "clear") {
                _do_enroll(frm, []);
            } else {
                _show_skill_gap_dialog(frm, result);
            }
        },
    });
}


// ─────────────────────────────────────────────────────────────────────────────
// MILESTONE JOURNEY BOARD (inline on form)
// ─────────────────────────────────────────────────────────────────────────────

function _render_milestone_board(frm) {
    if (frm.is_new() || !frm.doc.career_path) return;

    // Find the HTML field to render into
    const $field = frm.fields_dict["milestone_board_html"];
    if (!$field) return;

    frappe.call({
        method  : API.OVERVIEW,
        args    : { enrollment: frm.doc.name },
        callback(r) {
            if (!r.message) return;
            const html = _build_board_html(r.message);
            $field.$wrapper.html(html);
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
        Learn: "📖", Build: "🏗️", Assess: "📝", Connect: "🤝", Apply: "🚀",
    };

    const pct       = data.completion_percent || 0;
    const bar_color = pct >= 100 ? "#52c41a" : pct >= 60 ? "#1890ff" : "#faad14";

    const cards = data.milestones.map(m => {
        const cfg  = STATUS[m.status] || STATUS["Not Started"];
        const lock = m.is_lock
            ? `<span title="Locked" style="color:#bfbfbf; font-size:12px;">🔒</span>`
            : "";
        const prereq_badge = m.is_prereq
            ? `<span style="
                background:#fff7e6; color:#d46b08; border:1px solid #ffd591;
                border-radius:4px; font-size:10px; padding:1px 5px; margin-left:4px;">
                Prereq</span>`
            : "";
        const current_badge = m.is_current
            ? `<span style="
                background:#e6f7ff; color:#096dd9; border:1px solid #91d5ff;
                border-radius:4px; font-size:10px; padding:1px 5px; margin-left:4px;">
                Current</span>`
            : "";
        const type_icon = TYPE_ICONS[m.milestone_type] || "📌";

        // Action buttons: only on unlocked, non-completed rows
        let actions = "";
        if (!m.is_lock && m.status !== "Completed") {
            actions = `
            <div style="display:flex; gap:6px; margin-top:6px; flex-wrap:wrap;">
                ${m.is_skippable
                    ? `<button class="btn btn-xs btn-warning board-skip-btn"
                          data-row="${m.row_name}" style="font-size:11px;">
                          ⏭️ Skip
                       </button>`
                    : ""}
            </div>`;
        }

        return `
        <div style="
            display:flex; align-items:flex-start; gap:10px;
            background:${cfg.bg}; border:1px solid ${cfg.border};
            border-radius:8px; padding:12px; margin-bottom:6px;
            ${m.is_current ? "border-left:4px solid #1890ff;" : ""}
        ">
            <div style="font-size:20px; min-width:28px; text-align:center; padding-top:2px;">
                ${m.is_lock ? "🔒" : cfg.icon}
            </div>
            <div style="flex:1; min-width:0;">
                <div style="display:flex; align-items:center; flex-wrap:wrap; gap:2px;">
                    <span style="font-weight:600; font-size:13px;">
                        ${m.milestone_order}. ${type_icon} ${m.milestone_title}
                    </span>
                    ${prereq_badge}${current_badge}
                </div>
                <div style="margin-top:4px; display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                    <span style="
                        color:${cfg.color}; font-weight:600; font-size:12px;
                        background:${cfg.bg}; border:1px solid ${cfg.border};
                        border-radius:10px; padding:1px 8px;">
                        ${cfg.icon} ${m.status}
                    </span>
                    ${m.milestone_type
                        ? `<span style="font-size:11px; color:#595959;">${m.milestone_type}</span>`
                        : ""}
                    ${m.score != null
                        ? `<span style="font-size:11px; color:#595959;">Score: ${m.score}</span>`
                        : ""}
                    ${m.completed_on
                        ? `<span style="font-size:11px; color:#8c8c8c;">Done: ${m.completed_on}</span>`
                        : ""}
                </div>
                ${actions}
            </div>
        </div>`;
    }).join("");

    // Status summary chips
    const chips = Object.entries(data.status_counts || {}).map(([s, c]) => {
        const cfg = STATUS[s] || STATUS["Not Started"];
        return `<span style="
            display:inline-flex; align-items:center; gap:4px;
            background:${cfg.bg}; color:${cfg.color}; border:1px solid ${cfg.border};
            border-radius:12px; padding:2px 10px; font-size:12px; font-weight:600;
            margin-right:6px; margin-bottom:4px;">
            ${cfg.icon} ${s}: ${c}
        </span>`;
    }).join("");

    return `
    <div style="padding:16px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; flex-wrap:wrap; gap:8px;">
            <span style="font-weight:700; font-size:14px;">🗺️ Milestone Journey</span>
            <span style="font-weight:700; color:${bar_color}; font-size:14px;">${pct}% Complete</span>
        </div>

        <!-- Progress Bar -->
        <div style="background:#f0f0f0; border-radius:10px; height:14px; margin-bottom:12px; overflow:hidden;">
            <div style="
                width:${pct}%; background:${bar_color};
                height:14px; border-radius:10px;
                font-size:10px; color:#fff; font-weight:700;
                display:flex; align-items:center; justify-content:center;
                transition:width .5s ease;">
                ${pct > 15 ? pct + "%" : ""}
            </div>
        </div>

        <!-- Summary Chips -->
        <div style="margin-bottom:14px;">${chips}</div>

        <!-- Milestone Cards -->
        <div>${cards}</div>
    </div>`;
}

function _bind_board_actions(frm, $wrapper) {
    $wrapper.find(".board-skip-btn").on("click", function() {
        const row_name = $(this).data("row");
        frappe.confirm(
            "Are you sure you want to skip this milestone?",
            () => _do_skip(frm, row_name)
        );
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
// MILESTONE JOURNEY DIALOG (full-screen table view)
// ─────────────────────────────────────────────────────────────────────────────

function _show_milestone_dialog(frm) {
    frappe.call({
        method  : API.OVERVIEW,
        args    : { enrollment: frm.doc.name },
        callback(r) {
            if (!r.message) return;
            const data = r.message;

            const STATUS_ICONS = {
                "Completed": "✅", "In Progress": "⏳",
                "Skipped": "⏭️", "Not Started": "⭕",
            };
            const STATUS_COLORS = {
                "Completed": "#52c41a", "In Progress": "#1890ff",
                "Skipped": "#8c8c8c", "Not Started": "#bfbfbf",
            };

            const rows = data.milestones.map(m => `
                <tr style="${m.is_current ? "background:#e6f7ff;" : ""}${m.is_lock ? "opacity:0.55;" : ""}">
                    <td style="text-align:center; font-weight:700;">${m.milestone_order}</td>
                    <td>
                        ${m.is_prereq
                            ? `<span style="background:#fff7e6; color:#d46b08; border-radius:3px;
                                           font-size:10px; padding:1px 5px; margin-right:4px;">P</span>`
                            : ""}
                        <strong>${m.milestone_title}</strong>
                        ${m.is_current ? " 👈" : ""}
                        ${m.is_lock ? " 🔒" : ""}
                    </td>
                    <td>${m.milestone_type || "-"}</td>
                    <td>
                        <span style="color:${STATUS_COLORS[m.status] || "#bfbfbf"}; font-weight:600;">
                            ${STATUS_ICONS[m.status] || "⭕"} ${m.status}
                        </span>
                    </td>
                    <td>${m.score != null ? m.score : "-"}</td>
                    <td>${m.started_on || "-"}</td>
                    <td>${m.completed_on || "-"}</td>
                    <td>
                        ${m.is_skippable && !m.is_lock && m.status !== "Completed"
                            ? `<button class="btn btn-xs btn-warning dlg-skip-btn"
                                  data-row="${m.row_name}">Skip</button>`
                            : "-"}
                    </td>
                </tr>`).join("");

            const dialog = new frappe.ui.Dialog({
                title : `🗺️ Milestone Journey — ${frm.doc.career_path}`,
                size  : "extra-large",
                fields: [{
                    fieldtype: "HTML",
                    options  : `
                    <div style="padding:10px;">
                        <div style="background:#f0f0f0; border-radius:10px; height:14px; margin-bottom:12px; overflow:hidden;">
                            <div style="width:${data.completion_percent}%; background:#1890ff; height:14px;
                                        border-radius:10px; display:flex; align-items:center;
                                        justify-content:center; color:#fff; font-size:10px; font-weight:700;">
                                ${data.completion_percent > 10 ? data.completion_percent + "%" : ""}
                            </div>
                        </div>
                        <div style="max-height:450px; overflow-y:auto;">
                            <table class="table table-sm table-bordered table-hover" style="font-size:12px;">
                                <thead class="thead-light">
                                    <tr>
                                        <th>#</th><th>Milestone</th><th>Type</th>
                                        <th>Status</th><th>Score</th>
                                        <th>Started</th><th>Completed</th><th>Action</th>
                                    </tr>
                                </thead>
                                <tbody>${rows}</tbody>
                            </table>
                        </div>
                        <p class="text-muted" style="font-size:11px; margin-top:6px;">
                            P = Prerequisite path milestone &nbsp;|&nbsp; 🔒 = Locked
                        </p>
                    </div>`,
                }],
            });

            dialog.show();

            // Bind skip buttons inside dialog
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
            const $row  = $(this);
            const text  = $row.text();
            let bg_color = "#ffffff";

            for (const [status, color] of Object.entries(STATUS_COLORS)) {
                if (text.includes(status)) {
                    bg_color = color;
                    break;
                }
            }
            $row.css("background-color", bg_color);

            // Extra: red left border for locked rows
            if (text.includes("🔒") || $row.find('[data-fieldname="is_lock"]').text().trim() === "1") {
                $row.css("border-left", "3px solid #ff4d4f");
            }
        });
}


// ─────────────────────────────────────────────────────────────────────────────
// COMPLETION HEADER BAR
// ─────────────────────────────────────────────────────────────────────────────

function _render_completion_header(frm) {
    if (frm.is_new()) return;

    const pct   = frm.doc.completion_percent || 0;
    const color = pct >= 100 ? "#52c41a" : pct >= 60 ? "#1890ff" : "#faad14";
    const label = pct >= 100 ? "🎉 Path Completed!" : `${pct}% Progress`;

    const $pct_field = frm.fields_dict["completion_percent"];
    if (!$pct_field) return;

    $pct_field.$wrapper.find(".progress-inline").remove();
    $pct_field.$wrapper.append(`
        <div class="progress-inline" style="margin-top:4px;">
            <div style="background:#f0f0f0; border-radius:8px; height:12px; overflow:hidden;">
                <div style="
                    width:${pct}%; background:${color}; height:12px;
                    border-radius:8px; transition:width .5s;
                    display:flex; align-items:center; justify-content:center;
                    font-size:9px; color:#fff; font-weight:700;">
                    ${pct > 20 ? label : ""}
                </div>
            </div>
            ${pct <= 20 ? `<small style="color:${color}; font-weight:600;">${label}</small>` : ""}
        </div>`);
}


// ─────────────────────────────────────────────────────────────────────────────
// SKIP CURRENT (button shortcut)
// ─────────────────────────────────────────────────────────────────────────────

function _skip_current(frm) {
    const current_order = frm.doc.current_milestone_order;

    frappe.call({
        method  : API.OVERVIEW,
        args    : { enrollment: frm.doc.name },
        callback(r) {
            if (!r.message) return;
            const current = r.message.milestones.find(m => m.is_current);
            if (!current) {
                frappe.msgprint("No active milestone found.");
                return;
            }
            if (!current.is_skippable) {
                frappe.msgprint({
                    title    : "Cannot Skip",
                    message  : `Milestone <b>${current.milestone_title}</b> is not skippable.`,
                    indicator: "red",
                });
                return;
            }
            frappe.confirm(
                `Skip milestone: <b>${current.milestone_title}</b>?`,
                () => _do_skip(frm, current.row_name)
            );
        },
    });
}