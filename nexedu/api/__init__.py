import frappe


@frappe.whitelist(allow_guest=True)
def load_question(screen_name):
    doc = frappe.get_doc("Student Test Screen", screen_name)
    return doc.load_question()


@frappe.whitelist(allow_guest=True)
def next_question(screen_name, selected_option=None, user_input=None, open_ended=None):
    doc = frappe.get_doc("Student Test Screen", screen_name)
    return doc.next_question(selected_option, user_input, open_ended)


@frappe.whitelist(allow_guest=True)
def previous_question(screen_name):
    doc = frappe.get_doc("Student Test Screen", screen_name)
    return doc.previous_question()


@frappe.whitelist(allow_guest=True)
def create_student_test_screen(test_type, email=None):
    doc = frappe.new_doc("Student Test Screen")
    doc.test_type = test_type
    doc.test = test_type
    doc.question_index = 0
    user_email = email or (frappe.session.user if frappe.session.user != "Guest" else None)
    if user_email:
        doc.owner = user_email
    doc.insert(ignore_permissions=True)
    return doc.name


@frappe.whitelist(allow_guest=True)
def start_new_test(test_type, email=None):
    doc = frappe.new_doc("Student Test Screen")
    doc.test_type = test_type
    doc.test = test_type
    doc.question_index = 0
    user_email = email or (frappe.session.user if frappe.session.user != "Guest" else None)
    if user_email:
        doc.owner = user_email
    doc.insert(ignore_permissions=True)
    return doc.name


@frappe.whitelist(allow_guest=True)
def submit_test(name, email=None):
    doc = frappe.get_doc("Student Test Screen", name)

    if doc.docstatus == 0:
        doc.flags.ignore_permissions = True
        doc.submit()

    # Ensure member in Str Psychometric Test Submission has user_email if provided
    user_email = email or (frappe.session.user if frappe.session.user != "Guest" else None) or doc.owner
    if user_email and user_email != "Guest":
        sub_name = frappe.db.get_value("Str Psychometric Test Submission", {"student_test_screen": doc.name})
        if sub_name:
            frappe.db.set_value("Str Psychometric Test Submission", sub_name, "member", user_email)

        # Update Student DocType is_first_login field to 0 (False)
        student_name = frappe.db.get_value("Student", {"email_id": user_email})
        if not student_name and frappe.db.exists("Student", user_email):
            student_name = user_email
        if student_name:
            frappe.db.set_value("Student", student_name, "is_first_login", 0)

    # Calculate subject breakdown and scores
    subject_scores = {}
    for row in doc.str_test_response:
        subject = row.subject or "General"
        if subject not in subject_scores:
            subject_scores[subject] = {"obtained": 0, "maximum": 0}
        subject_scores[subject]["obtained"] += row.mark or 0
        subject_scores[subject]["maximum"] += row.maximum_marks or 0

    subject_percentage_map = {}
    for subject, data in subject_scores.items():
        pct = 0
        if data["maximum"] > 0:
            pct = (data["obtained"] / data["maximum"]) * 100
        subject_percentage_map[subject] = round(pct, 1)

    C = subject_percentage_map.get("Conscientiousness", 0)
    E = subject_percentage_map.get("Extraversion", 0)
    ES = subject_percentage_map.get("Emotional Stability", 0)
    O = subject_percentage_map.get("Openness to Experience", 0)

    job_score = round((C * 0.4) + (E * 0.2) + (ES * 0.2) + (O * 0.2), 1)
    startup_score = round((O * 0.3) + (E * 0.3) + (ES * 0.3) + (C * 0.1), 1)
    higher_ed_score = round((O * 0.4) + (C * 0.4) + (ES * 0.1) + (E * 0.1), 1)

    highest = max(job_score, startup_score, higher_ed_score)
    if highest == job_score:
        result = "💼 Job Oriented"
    elif highest == startup_score:
        result = "🚀 Startup Oriented"
    else:
        result = "🎓 Higher Education Oriented"

    return {
        "status": "Submitted",
        "result": result,
        "job_score": job_score,
        "startup_score": startup_score,
        "higher_ed_score": higher_ed_score,
        "subject_scores": subject_percentage_map,
        "ai_result": getattr(doc, "ai_result", None)
    }


@frappe.whitelist(allow_guest=True)
def get_tests():
    return frappe.get_all(
        "Str Psychometric Test",
        fields=["name"]
    )


@frappe.whitelist(allow_guest=True)
def check_test_status(email=None):
    user = email or (frappe.session.user if frappe.session.user != "Guest" else None)
    if not user or user == "Guest":
        return {
            "has_completed_test": False,
            "submission": None
        }

    submission = frappe.db.get_value(
        "Str Psychometric Test Submission",
        {"member": user},
        ["name", "psychometric_test", "creation"],
        as_dict=True
    )
    if not submission:
        submission = frappe.db.get_value(
            "Str Psychometric Test Submission",
            {"owner": user},
            ["name", "psychometric_test", "creation"],
            as_dict=True
        )

    return {
        "has_completed_test": bool(submission),
        "submission": submission
    }


@frappe.whitelist(allow_guest=True)
def check_onboarding_status(email=None):
    user = email or (frappe.session.user if frappe.session.user != "Guest" else None)
    
    if not user or user == "Guest":
        return {
            "is_first_login": False,
            "is_onboarded": False,
            "test_completed": False,
            "has_completed_test": False,
            "requires_test": False,
            "submission": None,
            "test_screen": None
        }

    # Fetch Student DocType field `is_first_login`
    student_name = frappe.db.get_value("Student", {"email_id": user})
    if not student_name and frappe.db.exists("Student", user):
        student_name = user

    student_is_first_login = None
    if student_name:
        student_is_first_login = frappe.db.get_value("Student", student_name, "is_first_login")

    submission = frappe.db.get_value(
        "Str Psychometric Test Submission",
        {"member": user},
        ["name", "psychometric_test", "creation", "score", "percentage"],
        as_dict=True
    )
    if not submission:
        submission = frappe.db.get_value(
            "Str Psychometric Test Submission",
            {"owner": user},
            ["name", "psychometric_test", "creation", "score", "percentage"],
            as_dict=True
        )
    
    test_screen = frappe.db.get_value(
        "Student Test Screen",
        {"owner": user, "docstatus": 1},
        ["name", "creation", "docstatus"],
        as_dict=True
    )
    
    has_completed = bool(submission or test_screen)

    # Respect Student.is_first_login if present:
    # 1. If student_is_first_login == 1 (or True): test MUST open (is_first_login = True)
    # 2. If student_is_first_login == 0 (or False): test MUST NOT open (is_first_login = False)
    # 3. If student_is_first_login is None: fallback to not has_completed
    if student_is_first_login is not None:
        is_first_login = bool(student_is_first_login)
    else:
        is_first_login = not has_completed

    requires_test = is_first_login
    is_onboarded = has_completed and not is_first_login
    
    return {
        "is_first_login": is_first_login,
        "is_onboarded": is_onboarded,
        "test_completed": has_completed,
        "has_completed_test": has_completed,
        "requires_test": requires_test,
        "submission": submission,
        "test_screen": test_screen
    }
