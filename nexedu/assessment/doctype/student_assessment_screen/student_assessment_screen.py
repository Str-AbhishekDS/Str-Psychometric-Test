# Copyright (c) 2026, Stride nex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class StudentAssessmentScreen(Document):

    def validate(self):
        if not self.assessment:
            frappe.throw("Please select an Assessment")

    def on_submit(self):
        obtained_score = 0
        total_score = 0

        for row in self.str_test_response:
            obtained_score += row.mark or 0
            total_score += row.maximum_marks or 0

        percentage = (obtained_score / total_score * 100) if total_score > 0 else 0

        assessment = frappe.get_doc("Assessment", self.assessment)

        # Calculate grade
        grade = get_grade(percentage, assessment.grade_config)

        # Pass or Fail based on passing_marks
        result = "Pass" if obtained_score >= (assessment.passing_marks or 0) else "Fail"

        # Show result to student
        frappe.msgprint(f"""
            <b>Assessment Result</b><br><br>
            ✅ Score: {obtained_score}/{total_score}<br>
            📊 Percentage: {round(percentage, 2)}%<br>
            🏅 Grade: {grade}<br>
            🎯 Result: {result}
        """)

        # Create Assessment Submission
        doc = frappe.new_doc("Assessment Submission")
        doc.assessment = self.assessment
        doc.student_assessment_screen = self.name
        doc.member = frappe.session.user
        doc.score = obtained_score
        doc.score_out_of = total_score
        doc.percentage = round(percentage, 2)
        doc.passing_marks = assessment.passing_marks
        doc.grade = grade
        doc.result = result

        for row in self.str_test_response:
            doc.append("str_test_response", {
                "question": row.question,
                "question_link": row.question_link,
                "response": row.response,
                "correct_ans": row.correct_ans,
                "mark": row.mark,
                "maximum_marks": row.maximum_marks,
                "type": row.type,
                "subject": row.subject
            })

        doc.insert(ignore_permissions=True)

    @frappe.whitelist()
    def load_question(self):
        assessment = frappe.get_doc("Assessment", self.assessment)
        questions = assessment.assessment_question

        index = self.question_index or 0
        total = len(questions)

        if index >= total:
            return {"completed": True}

        question_row = questions[index]
        question_doc = frappe.get_doc("Str Question", question_row.question)

        options = []
        for i in range(1, 11):
            opt = question_doc.get(f"option_{i}")
            if opt:
                options.append(opt)

        saved_row = next(
            (d for d in self.str_test_response
             if str(d.question_link) == str(question_doc.name)),
            None
        )

        return {
            "question": question_doc.question,
            "question_type": question_doc.type,
            "subject": question_doc.test_subject or "General",
            "options": options,
            "multiple_correct": question_doc.multiple_correct_answers,
            "is_last": (index == total - 1),
            "no_of_options": question_doc.no_of_options,
            "saved_response": saved_row.response if saved_row else None,
            "completed": False
        }

    @frappe.whitelist()
    def next_question(self, selected_option=None, user_input=None, open_ended=None):
        assessment = frappe.get_doc("Assessment", self.assessment)
        questions = assessment.assessment_question

        index = self.question_index or 0
        total = len(questions)

        if index >= total:
            return {"completed": True}

        question_row = questions[index]
        question_doc = frappe.get_doc("Str Question", question_row.question)
        question_type = question_doc.type

        response = None
        correct_ans = None
        max_marks = question_row.marks or 0
        mark = 0

        if question_type == "Choices":
            if not question_doc.multiple_correct_answers:
                response = selected_option
                correct_ans = get_correct_answer(question_doc)
                mark = max_marks if response == correct_ans else 0
            else:
                if isinstance(selected_option, str):
                    selected_option = [selected_option]
                response = ", ".join(selected_option) if selected_option else ""
                for i in range(1, 11):
                    opt = question_doc.get(f"option_{i}")
                    weight = question_doc.get(f"option_{i}_weightage") or 0
                    if opt and question_doc.get(f"is_correct_{i}") and selected_option and opt in selected_option:
                        mark = weight

        elif question_type == "User Input":
            response = user_input
            correct_ans = question_doc.possibility_1
            if response and correct_ans:
                if response.strip().lower() == correct_ans.strip().lower():
                    mark = max_marks

        elif question_type == "Open Ended":
            response = open_ended
            correct_ans = None
            mark = 0
            max_marks = 0

        # Save response
        existing_row = next(
            (d for d in self.str_test_response
             if str(d.question_link) == str(question_doc.name)),
            None
        )
        if not existing_row:
            existing_row = self.append("str_test_response", {})

        existing_row.question = question_doc.question
        existing_row.question_link = question_doc.name
        existing_row.response = response
        existing_row.correct_ans = correct_ans
        existing_row.maximum_marks = max_marks
        existing_row.mark = mark
        existing_row.subject = question_doc.test_subject
        existing_row.type = question_type

        self.question_index += 1
        self.save(ignore_permissions=True)

        if self.question_index >= total:
            return {"completed": True}

        # Load next question
        next_row = questions[self.question_index]
        next_doc = frappe.get_doc("Str Question", next_row.question)

        options = []
        for i in range(1, 11):
            opt = next_doc.get(f"option_{i}")
            if opt:
                options.append(opt)

        return {
            "question": next_doc.question,
            "question_type": next_doc.type,
            "options": options,
            "multiple_correct": next_doc.multiple_correct_answers,
            "is_last": (self.question_index == total - 1),
            "subject": next_doc.test_subject or "General",
            "completed": False
        }

    @frappe.whitelist()
    def previous_question(self):
        if not self.question_index or self.question_index <= 0:
            return

        self.question_index -= 1
        assessment = frappe.get_doc("Assessment", self.assessment)
        questions = assessment.assessment_question

        question_row = questions[self.question_index]
        question_doc = frappe.get_doc("Str Question", question_row.question)

        saved_row = next(
            (d for d in self.str_test_response
             if d.question_link == question_doc.name),
            None
        )

        options = []
        for i in range(1, 11):
            opt = question_doc.get(f"option_{i}")
            if opt:
                options.append(opt)

        self.save(ignore_permissions=True)

        return {
            "question": question_doc.question,
            "question_type": question_doc.type,
            "options": options,
            "saved_response": saved_row.response if saved_row else None,
            "multiple_correct": question_doc.multiple_correct_answers,
            "no_of_options": question_doc.no_of_options,
            "subject": question_doc.test_subject or "General",
            "is_last": False,
            "completed": False
        }


def get_correct_answer(doc):
    for i in range(1, 11):
        if doc.get(f"is_correct_{i}"):
            return doc.get(f"option_{i}")
    return None


def get_grade(percentage, grade_config):
    for row in grade_config:
        if row.min_percent <= percentage <= row.max_percent:
            return row.grade
    return "F"