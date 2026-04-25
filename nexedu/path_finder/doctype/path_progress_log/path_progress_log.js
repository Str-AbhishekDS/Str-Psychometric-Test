// Copyright (c) 2026, Stride nex and contributors
// For license information, please see license.txt
//
// path_progress_log.js
// ─────────────────────────────────────────────────────────────────────────────
// CORE DESIGN CHANGE:
//   The `milestone` field on Path Progress Log now represents a ROW in the
//   Student Path Enrollment's milestone_progress child table.
//   Each row of that child table IS the milestone — identified by its `name`
//   (Frappe child row name) and displayed as its idx.
//
//   Flow:
//     1. User selects Enrollment ID
//        → career_path auto-fills from enrollment (read-only)
//        → milestone dropdown is populated with rows from that enrollment's
//          milestone_progress child table (not from Path Milestone doctype)
//     2. User picks a milestone row (shown as "1 - Python Basics", "2 - DSA", …)
//        → idx and title are shown in the form
//        → sequential warning fires if not the current milestone
//     3. On save → that child row is marked Completed in enrollment
//        → current_milestone_order advances to the next row's idx
// ─────────────────────────────────────────────────────────────────────────────

const PPL_API = {
    OVERVIEW      : "nexedu.path_finder.api.get_milestone_overview",
    GET_MILESTONES: "nexedu.path_finder.api.get_enrollment_milestones_for_select",
};

// ─────────────────────────────────────────────────────────────────────────────
// FORM EVENTS
// ─────────────────────────────────────────────────────────────────────────────

frappe.ui.form.on("Path Progress Log", {

    refresh(frm) {
        _set_status_indicator(frm);
        _setup_buttons(frm);

        // On saved record — show which milestone row this log belongs to
        if (!frm.is_new() && frm.doc.milestone) {
            _render_milestone_info_banner(frm);
        }
    },

    // ── Step 1: Enrollment selected ──────────────────────────────────────────
    enrollment(frm) {
        if (!frm.doc.enrollment) {
            frm.set_value("career_path", "");
            frm.set_value("milestone", "");
            _clear_milestone_select(frm);
            return;
        }

        // Auto-fill career_path from enrollment (field should be read_only on form)
        frappe.db.get_value(
            "Student Path Enrollment",
            frm.doc.enrollment,
            ["career_path", "student", "current_milestone_order", "status"],
            function(data) {
                if (!data) return;

                frm.set_value("career_path", data.career_path);
                frm._enrollment_current_idx    = parseInt(data.current_milestone_order) || 1;
                frm._enrollment_student        = data.student;
                frm._enrollment_status         = data.status;

                // Show enrollment status on page header
                const color_map = {
                    "Active": "blue", "Completed": "green",
                    "Paused": "orange", "Abandoned": "red",
                };
                frm.page.set_indicator(data.status, color_map[data.status] || "grey");

                // Clear stale milestone, then load fresh select options
                frm.set_value("milestone", "");
                _load_milestone_select(frm);
            }
        );
    },

    // ── Step 2: Milestone row selected ───────────────────────────────────────
    milestone(frm) {
        if (!frm.doc.milestone || !frm.doc.enrollment) return;

        // The milestone field stores the child row `name` (e.g. "abc123xyz")
        // Find its details in our cached overview
        const row = (frm._milestone_rows || []).find(m => m.row_name === frm.doc.milestone);
        if (!row) return;

        // Show position info in the form headline
        frm.dashboard.clear_headline();
        frm.dashboard.set_headline_alert(
            `Selected: #${row.milestone_idx} — ${row.milestone_title}` +
            (row.is_prereq ? "  [Prereq]" : "") +
            `  |  Status: ${row.status}`,
            row.status === "Completed" ? "green"
            : row.status === "In Progress" ? "blue"
            : "orange"
        );

        // Warn if out of sequence
        const current_idx = frm._enrollment_current_idx || 0;
        if (current_idx && row.milestone_idx !== current_idx) {
            frappe.msgprint({
                title    : "⚠️ Sequence Warning",
                message  : `You selected milestone <b>#${row.milestone_idx} (${row.milestone_title})</b>, `
                         + `but the current expected milestone is <b>#${current_idx}</b>.<br>`
                         + "Please complete milestones in sequence.",
                indicator: "orange",
            });
        }
    },
});


// ─────────────────────────────────────────────────────────────────────────────
// LOAD MILESTONE ROWS INTO SELECT
// Fetches the enrollment's milestone_progress child rows via API,
// builds a Select or Link-style dropdown showing idx + title.
// ─────────────────────────────────────────────────────────────────────────────

function _load_milestone_select(frm) {
    if (!frm.doc.enrollment) return;

    frappe.call({
        method  : PPL_API.GET_MILESTONES,
        args    : { enrollment: frm.doc.enrollment },
        callback(r) {
            if (!r.message) return;

            const rows = r.message;
            frm._milestone_rows = rows;   // cache for milestone event

            // Build options for the milestone Select field
            // Format: "row_name::idx - title (status)"
            // We set the options on the field so user picks from a list
            const options = rows.map(m => {
                const done_icon = m.status === "Completed" ? " ✅"
                                : m.status === "In Progress" ? " ⏳"
                                : m.status === "Skipped" ? " ⏭️"
                                : "";
                const prereq    = m.is_prereq ? " [P]" : "";
                return {
                    label: `${m.milestone_idx}${prereq} — ${m.milestone_title}${done_icon}`,
                    value: m.row_name,
                };
            });

            // Render a custom Select widget inside the milestone field wrapper
            _render_milestone_dropdown(frm, options, rows);
        },
    });
}

function _render_milestone_dropdown(frm, options, rows) {
    // Use Frappe's set_df_property to convert the field to a Select on-the-fly
    // This avoids needing a schema change — the field stores the row `name`
    const $wrapper = frm.fields_dict["milestone"]?.$wrapper;
    if (!$wrapper) return;

    // Remove any previous custom select
    $wrapper.find(".milestone-custom-select").remove();

    // Hide the default link input
    $wrapper.find(".link-field").hide();

    const select_html = `
    <div class="milestone-custom-select" style="margin-top:2px;">
        <select class="form-control" id="milestone-row-select" style="height:32px;font-size:13px;">
            <option value="">— Select Milestone —</option>
            ${options.map(o => `<option value="${o.value}">${o.label}</option>`).join("")}
        </select>
        <div id="milestone-row-detail" style="
            margin-top:6px;padding:8px 12px;border-radius:6px;
            background:#f0f5ff;border:1px solid #adc6ff;display:none;
            font-size:12px;color:#1d39c4;">
        </div>
    </div>`;

    $wrapper.append(select_html);

    // If editing an existing record, pre-select saved value
    if (frm.doc.milestone) {
        $wrapper.find("#milestone-row-select").val(frm.doc.milestone);
        _show_row_detail($wrapper, rows, frm.doc.milestone);
    }

    $wrapper.find("#milestone-row-select").on("change", function() {
        const selected_row_name = $(this).val();
        frm.set_value("milestone", selected_row_name);
        _show_row_detail($wrapper, rows, selected_row_name);
    });
}

function _show_row_detail($wrapper, rows, row_name) {
    const row    = rows.find(m => m.row_name === row_name);
    const $detail = $wrapper.find("#milestone-row-detail");
    if (!row) { $detail.hide(); return; }

    const status_color = row.status === "Completed" ? "#52c41a"
                       : row.status === "In Progress" ? "#1890ff"
                       : "#8c8c8c";

    $detail.html(`
        <b>#${row.milestone_idx}</b> — ${row.milestone_title}
        &nbsp;·&nbsp;
        <span style="color:${status_color};font-weight:600;">${row.status}</span>
        ${row.is_prereq ? `&nbsp;·&nbsp;<span style="color:#d46b08;">[Prereq]</span>` : ""}
        ${row.skill ? `&nbsp;·&nbsp; 🔧 ${row.skill}` : ""}
        ${row.milestone_type ? `&nbsp;·&nbsp; ${row.milestone_type}` : ""}
    `).show();
}

function _clear_milestone_select(frm) {
    const $wrapper = frm.fields_dict["milestone"]?.$wrapper;
    if (!$wrapper) return;
    $wrapper.find(".milestone-custom-select").remove();
    $wrapper.find(".link-field").show();
}


// ─────────────────────────────────────────────────────────────────────────────
// MILESTONE INFO BANNER (on saved records)
// ─────────────────────────────────────────────────────────────────────────────

function _render_milestone_info_banner(frm) {
    frappe.call({
        method  : PPL_API.GET_MILESTONES,
        args    : { enrollment: frm.doc.enrollment },
        callback(r) {
            if (!r.message) return;
            frm._milestone_rows = r.message;
            const row = r.message.find(m => m.row_name === frm.doc.milestone);
            if (!row) return;

            frm.dashboard.clear_headline();
            frm.dashboard.set_headline_alert(
                `Milestone #${row.milestone_idx} — ${row.milestone_title}  |  ${row.status}`,
                row.status === "Completed" ? "green" : "blue"
            );
        },
    });
}


// ─────────────────────────────────────────────────────────────────────────────
// STATUS INDICATOR
// ─────────────────────────────────────────────────────────────────────────────

function _set_status_indicator(frm) {
    if (!frm.doc.enrollment) return;

    frappe.db.get_value(
        "Student Path Enrollment",
        frm.doc.enrollment,
        "status",
        function(data) {
            if (!data || !data.status) return;
            const color_map = {
                "Active": "blue", "Completed": "green",
                "Paused": "orange", "Abandoned": "red",
            };
            frm.page.set_indicator(data.status, color_map[data.status] || "grey");
        }
    );
}


// ─────────────────────────────────────────────────────────────────────────────
// BUTTONS
// ─────────────────────────────────────────────────────────────────────────────

function _setup_buttons(frm) {
    if (frm.is_new() || !frm.doc.enrollment) return;

    frm.add_custom_button(__("View All Milestones"), () => {
        _show_all_milestones_dialog(frm);
    });
}


// ─────────────────────────────────────────────────────────────────────────────
// VIEW ALL MILESTONES DIALOG
// ─────────────────────────────────────────────────────────────────────────────

function _show_all_milestones_dialog(frm) {
    frappe.call({
        method  : PPL_API.OVERVIEW,
        args    : { enrollment: frm.doc.enrollment },
        callback(r) {
            if (!r.message) return;
            const data = r.message;

            const S_ICON  = { "Completed":"✅","In Progress":"⏳","Skipped":"⏭️","Not Started":"⭕" };
            const S_COLOR = { "Completed":"#52c41a","In Progress":"#1890ff","Skipped":"#8c8c8c","Not Started":"#bfbfbf" };

            const pct  = data.completion_percent || 0;
            const rows = data.milestones.map((m, i) => {
                const is_this_log = m.row_name === frm.doc.milestone;
                return `
                <tr style="
                    ${m.is_current  ? "background:#e6f7ff;" : ""}
                    ${is_this_log   ? "font-weight:700;border:2px solid #1890ff;" : ""}
                    ${m.is_lock     ? "opacity:0.5;" : ""}
                ">
                    <td style="text-align:center;font-weight:700;">${m.milestone_idx}</td>
                    <td>
                        ${m.is_prereq
                            ? `<span style="background:#fff7e6;color:#d46b08;border-radius:3px;
                                font-size:10px;padding:1px 5px;margin-right:4px;">P</span>`
                            : ""}
                        ${m.milestone_title}
                        ${m.is_current     ? " 👈" : ""}
                        ${is_this_log      ? " ← this log" : ""}
                        ${m.is_auto_skipped ? " 🤖" : ""}
                    </td>
                    <td>${m.milestone_type || "-"}</td>
                    <td style="color:${S_COLOR[m.status]||"#bfbfbf"};font-weight:600;">
                        ${S_ICON[m.status]||"⭕"} ${m.status}
                    </td>
                    <td>${m.skill || "-"}</td>
                    <td style="text-align:center;">${m.score != null ? m.score : "-"}</td>
                    <td>${m.completed_on || "-"}</td>
                </tr>`;
            }).join("");

            const chips = Object.entries(data.status_counts || {}).map(([s, c]) => {
                const color = S_COLOR[s] || "#bfbfbf";
                return `<span style="background:#fafafa;color:${color};border:1px solid ${color};
                    border-radius:10px;padding:2px 10px;font-size:12px;font-weight:600;
                    margin-right:6px;margin-bottom:4px;">
                    ${S_ICON[s] || ""} ${s}: ${c}
                </span>`;
            }).join("");

            new frappe.ui.Dialog({
                title : `🗺️ All Milestones — ${frm.doc.enrollment}`,
                size  : "extra-large",
                fields: [{
                    fieldtype: "HTML",
                    options  : `
                    <div style="padding:10px;">
                        <!-- Progress bar -->
                        <div style="background:#f0f0f0;border-radius:8px;height:12px;
                            margin-bottom:8px;overflow:hidden;">
                            <div style="width:${pct}%;background:#1890ff;height:12px;
                                border-radius:8px;display:flex;align-items:center;
                                justify-content:center;color:#fff;font-size:9px;font-weight:700;">
                                ${pct > 12 ? pct + "%" : ""}
                            </div>
                        </div>

                        <!-- Summary -->
                        <div style="margin-bottom:8px;font-size:12px;color:#595959;">
                            📋 Prereqs: ${data.prereq_completed}/${data.prereq_count}
                            &nbsp;|&nbsp;
                            🗺️ Path: ${data.path_completed}/${data.path_count}
                            &nbsp;|&nbsp;
                            Total: ${data.completed_count}/${data.total_count}
                        </div>

                        <div style="margin-bottom:10px;">${chips}</div>

                        <div style="max-height:430px;overflow-y:auto;">
                            <table class="table table-sm table-bordered table-hover"
                                style="font-size:12px;">
                                <thead class="thead-light">
                                    <tr>
                                        <th>#</th>
                                        <th>Milestone</th>
                                        <th>Type</th>
                                        <th>Status</th>
                                        <th>Skill</th>
                                        <th>Score</th>
                                        <th>Completed</th>
                                    </tr>
                                </thead>
                                <tbody>${rows}</tbody>
                            </table>
                        </div>

                        <p class="text-muted" style="font-size:11px;margin-top:6px;">
                            P = Prereq &nbsp;|&nbsp;
                            👈 = Current &nbsp;|&nbsp;
                            🤖 = Auto-completed (skill already verified)
                        </p>
                    </div>`,
                }],
            }).show();
        },
    });
}