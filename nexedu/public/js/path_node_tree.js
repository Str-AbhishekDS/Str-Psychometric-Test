frappe.treeview_settings["Path Node"] = {
    filters: [
        {
            fieldname: "career_path",
            fieldtype: "Link",
            options: "Career Path",
            label: "Career Path",
            reqd: 1
        }
    ],

    get_tree_root: false,

    // 🔥 KEY FIX
    on_add_node: function(node) {

        let career_path = frappe.treeview_settings["Path Node"].filters[0].value;

        if (!career_path) {
            frappe.throw("Select Career Path first");
        }

        return {
            parent_path_node: node.data.name,   // ✅ correct parent
            career_path: career_path
        };
    },

    get_query: function() {
        return {
            filters: {
                career_path: frappe.treeview_settings["Path Node"].filters[0].value
            }
        };
    }
};