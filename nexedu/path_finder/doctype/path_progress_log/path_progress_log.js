// Copyright (c) 2026, Stride nex and contributors
// For license information, please see license.txt
//
// path_progress_log.js
// ─────────────────────────────────────────────────────────────────────────────
// Handles:
//  1. Milestone filter (only show milestones belonging to career_path)
//  2. Auto-fill milestone_order when milestone is selected
//  3. Sequential order warning if student tries to skip ahead
//  4. Status indicator on form header
//  5. "View All Milestones" dialog for this enrollment
// ─────────────────────────────────────────────────────────────────────────────

frappe.ui.form.on("Path Progress Log", {

    // ─────────────────────────────────────────────────────────────────────────
    // FORM EVENTS
    // ─────────────────────────────────────────────────────────────────────────

    refresh(frm) {
        _set_status_indicator(frm);
        _setup_buttons(frm);
    },

    enrollment(frm) {
        if (frm.doc.enrollment) {
            // Auto-fetch career_path from enrollment
            frappe.db.get_value(
                "Student Path Enrollment",
                frm.doc.enrollment,
                ["career_path", "student", "current_milestone_order"],
                function(data) {
                    if (data) {
                        frm.set_value("career_path", data.career_path);
                        frm.set_value("student",     data.student);
                        frm._enrollment_current_order = data.current_milestone_order;
                    }
                }
            );
        }

        // Re-apply milestone filter
        _apply_milestone_filter(frm);
    },

    career_path(frm) {
        // Re-apply filter and clear stale milestone
        _apply_milestone_filter(frm);
        frm.set_value("milestone", "");
    },

    milestone(frm) {
        if (!frm.doc.milestone || !frm.doc.career_path) return;

        // Fetch order from Path Milestone
        frappe.db.get_value(
            "Path Milestone",
            { name: frm.doc.milestone, parent: frm.doc.career_path },
            "order",
            function(data) {
                if (!data || !data.order) return;

                frm.set_value("milestone_order", data.order);

                // Warn if trying to log out-of-sequence
                const current = frm._enrollment_current_order
                    || frm.doc.__enrollment_current_order
                    || 0;

                if (current && parseInt(data.order) !== parseInt(current)) {
                    frappe.msgprint({
                        title    : "⚠️ Milestone Order Warning",
                        message  : `You selected Milestone Order <b>${data.order}</b>, 
                                    but the current expected order is <b>${current}</b>.<br>
                                    Please complete milestones in sequence.`,
                        indicator: "orange",
                    });
                }
            }
        );
    },

    // ─────────────────────────────────────────────────────────────────────────
    // STATUS INDICATOR
    // ─────────────────────────────────────────────────────────────────────────
});

// ─────────────────────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────────────────────

function _apply_milestone_filter(frm) {
    if (!frm.doc.career_path) return;

    frm.set_query("milestone", function() {
        return {
            filters: { parent: frm.doc.career_path },
        };
    });
}

function _set_status_indicator(frm) {
    // Visual indicator on form page header
    const enrollment_status = frm.doc.__enrollment_status;
    if (!enrollment_status) return;

    const color_map = {
        "Active"   : "blue",
        "Completed": "green",
        "Paused"   : "orange",
        "Abandoned": "red",
    };
    frm.page.set_indicator(
        enrollment_status,
        color_map[enrollment_status] || "grey"
    );
}

function _setup_buttons(frm) {
    if (frm.is_new() || !frm.doc.enrollment) return;

    frm.add_custom_button(__("View All Milestones"), () => {
        _show_all_milestones_dialog(frm);
    });
}

function _show_all_milestones_dialog(frm) {
    frappe.call({
        method  : "nexedu.path_finder.api.path_enrollment.get_milestone_overview",
        args    : { enrollment: frm.doc.enrollment },
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

            const pct = data.completion_percent || 0;

            const rows = data.milestones.map(m => {
                const is_this_log = m.milestone === frm.doc.milestone;
                return `
                <tr style="
                    ${m.is_current ? "background:#e6f7ff;" : ""}
                    ${is_this_log  ? "font-weight:700; outline:2px solid #1890ff;" : ""}
                    ${m.is_lock    ? "opacity:0.5;" : ""}
                ">
                    <td style="text-align:center;">${m.milestone_order}</td>
                    <td>
                        ${m.is_prereq
                            ? `<span style="background:#fff7e6; color:#d46b08; border-radius:3px;
                                font-size:10px; padding:1px 5px; margin-right:4px;">P</span>`
                            : ""}
                        ${m.milestone_title}
                        ${m.is_current  ? " 👈" : ""}
                        ${is_this_log   ? " ← this log" : ""}
                        ${m.is_lock     ? " 🔒" : ""}
                    </td>
                    <td>${m.milestone_type || "-"}</td>
                    <td>
                        <span style="color:${STATUS_COLORS[m.status] || "#bfbfbf"}; font-weight:600;">
                            ${STATUS_ICONS[m.status] || "⭕"} ${m.status}
                        </span>
                    </td>
                    <td>${m.score != null ? m.score : "-"}</td>
                    <td>${m.started_on   || "-"}</td>
                    <td>${m.completed_on || "-"}</td>
                </tr>`;
            }).join("");

            // Status summary
            const chips = Object.entries(data.status_counts || {}).map(([s, c]) => {
                const color = STATUS_COLORS[s] || "#bfbfbf";
                return `<span style="
                    background:#fafafa; color:${color}; border:1px solid ${color};
                    border-radius:10px; padding:1px 10px; font-size:12px;
                    font-weight:600; margin-right:6px;">
                    ${STATUS_ICONS[s] || ""} ${s}: ${c}
                </span>`;
            }).join("");

            const dialog = new frappe.ui.Dialog({
                title : `🗺️ All Milestones — ${frm.doc.enrollment}`,
                size  : "extra-large",
                fields: [{
                    fieldtype: "HTML",
                    options  : `
                    <div style="padding:10px;">
                        <!-- Progress bar -->
                        <div style="background:#f0f0f0; border-radius:8px; height:12px;
                                    margin-bottom:10px; overflow:hidden;">
                            <div style="width:${pct}%; background:#1890ff; height:12px;
                                        border-radius:8px; display:flex; align-items:center;
                                        justify-content:center; color:#fff; font-size:9px; font-weight:700;">
                                ${pct > 12 ? pct + "%" : ""}
                            </div>
                        </div>

                        <!-- Chips -->
                        <div style="margin-bottom:10px;">${chips}</div>

                        <!-- Table -->
                        <div style="max-height:430px; overflow-y:auto;">
                            <table class="table table-sm table-bordered table-hover"
                                   style="font-size:12px;">
                                <thead class="thead-light">
                                    <tr>
                                        <th>#</th><th>Milestone</th><th>Type</th>
                                        <th>Status</th><th>Score</th>
                                        <th>Started</th><th>Completed</th>
                                    </tr>
                                </thead>
                                <tbody>${rows}</tbody>
                            </table>
                        </div>
                        <p class="text-muted" style="font-size:11px; margin-top:6px;">
                            P = Prerequisite path milestone &nbsp;|&nbsp;
                            🔒 = Locked &nbsp;|&nbsp; 👈 = Current
                        </p>
                    </div>`,
                }],
            });

            dialog.show();
        },
    });
}