# import frappe

# @frappe.whitelist()
# def get_active_tests():
#     return frappe.get_all(
#         "str psychometric test",
#         filters={"is_active": 1},
#         fields=["name", "test_name", "duration_minutes"]
#     )

import frappe
import re



@frappe.whitelist()
def load_question(screen_name):
    doc = frappe.get_doc("Student Test Screen", screen_name)
    return doc.load_question()


@frappe.whitelist()
def next_question(screen_name, selected_option=None, user_input=None, open_ended=None):
    doc = frappe.get_doc("Student Test Screen", screen_name)
    return doc.next_question(selected_option, user_input, open_ended)


# @frappe.whitelist()
# def previous_question(screen_name):
#     doc = frappe.get_doc("Student Test Screen", screen_name)
#     return doc.previous_question()


@frappe.whitelist()
def create_student_test_screen(test_type):
    # create new STS for current user
    doc = frappe.new_doc("Student Test Screen")
    doc.test_type = test_type
    doc.question_index = 0
    doc.insert(ignore_permissions=True)
    return doc.name


@frappe.whitelist()
def start_new_test(test_type):
    doc = frappe.new_doc("Student Test Screen")
    doc.test_type = test_type
    doc.question_index = 0
    doc.insert(ignore_permissions=True)
    return doc.name



@frappe.whitelist()
def submit_test(name):

    doc = frappe.get_doc("Student Test Screen", name)

    if doc.docstatus == 0:
        doc.flags.ignore_permissions = True
        doc.submit()

    return "Submitted"



@frappe.whitelist()
def get_tests():
    return frappe.get_all(
        "Str Psychometric Test",
        fields=["name"]
    )