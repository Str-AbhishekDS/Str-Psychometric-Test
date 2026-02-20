import frappe
from frappe.model.document import Document


class StudentTestScreen(Document):
    def on_submit(self):

        is_psychometric = False

        # ---------------------------------
        # 🔎 Detect Test Type
        # ---------------------------------
        for row in self.str_test_response:
            question_doc = frappe.get_doc("Str Question", row.question_link)

            if question_doc.multiple_correct_answers:
                is_psychometric = True
                break

        # ---------------------------------
        # ✅ NORMAL MCQ TEST
        # ---------------------------------
        if not is_psychometric:

            obtained_score = 0
            total_score = 0

            for row in self.str_test_response:
                obtained_score += row.mark or 0
                total_score += row.maximum_marks or 0

            percentage = 0
            if total_score > 0:
                percentage = (obtained_score / total_score) * 100

            frappe.msgprint(f"""
                <b>Test Result</b><br><br>
                ✅ Score: {obtained_score}/{total_score}<br>
                📊 Percentage: {round(percentage, 2)}%
            """)

        # ---------------------------------
        # ✅ PSYCHOMETRIC TEST
        # ---------------------------------
        else:

            subject_scores = {}

            for row in self.str_test_response:

                subject = row.subject or "General"

                if subject not in subject_scores:
                    subject_scores[subject] = {
                        "obtained": 0,
                        "maximum": 0
                    }

                subject_scores[subject]["obtained"] += row.mark or 0
                subject_scores[subject]["maximum"] += row.maximum_marks or 0

            subject_percentage_map = {}

            for subject, data in subject_scores.items():
                percentage = 0
                if data["maximum"] > 0:
                    percentage = (data["obtained"] / data["maximum"]) * 100

                subject_percentage_map[subject] = percentage

            C = subject_percentage_map.get("Conscientiousness", 0)
            E = subject_percentage_map.get("Extraversion", 0)
            ES = subject_percentage_map.get("Emotional Stability", 0)
            O = subject_percentage_map.get("Openness to Experience", 0)

            job_score = (C * 0.4) + (E * 0.2) + (ES * 0.2) + (O * 0.2)
            startup_score = (O * 0.3) + (E * 0.3) + (ES * 0.3) + (C * 0.1)
            higher_ed_score = (O * 0.4) + (C * 0.4) + (ES * 0.1) + (E * 0.1)

            highest = max(job_score, startup_score, higher_ed_score)

            if highest == job_score:
                result = "💼 Job Oriented"
            elif highest == startup_score:
                result = "🚀 Startup Oriented"
            else:
                result = "🎓 Higher Education Oriented"

            frappe.msgprint(f"""
                <b>Psychometric Result</b><br><br>
                💼 Job Score: {round(job_score, 2)}<br>
                🚀 Startup Score: {round(startup_score, 2)}<br>
                🎓 Higher Education Score: {round(higher_ed_score, 2)}<br><br>
                <b>Final Result: {result}</b>
            """)
        
    def before_save(self):
        subject_scores = {}

        for row in self.str_test_response:

            subject = row.subject or "General"

            if subject not in subject_scores:
                subject_scores[subject] = {
                    "obtained": 0,
                    "maximum": 0
                }

            subject_scores[subject]["obtained"] += row.mark or 0
            subject_scores[subject]["maximum"] += row.maximum_marks or 0
            


        submission = []

        for subject, data in subject_scores.items():
            percentage = 0
            if data["maximum"] > 0:
                percentage = (data["obtained"] / data["maximum"]) * 100

            submission.append({
                "subject": subject,
                "obtained_marks": data["obtained"],
                "maximum_marks": data["maximum"],
                "percentage": percentage
            })
        
        self.set("str_psychometric_group_submission", {})
        self.set("str_psychometric_group_submission", submission)


    @frappe.whitelist()
    def load_question(self):

        test = frappe.get_doc("Str Psychometric Test", self.test_type)
        questions = test.str_psychometric_test_question

        index = self.question_index or 0
        total = len(questions)

        if index >= total:
            return {"completed": True}

        question_row = questions[index]
        question_doc = frappe.get_doc("Str Question", question_row.question)

        # Get subject
        question_sub = frappe.get_value(
            "Str Psychometric Test Question",
            {"question_detail": question_doc.question, "parent": self.test_type},
            "psychometric_test_subject"
        )

        # Get options
        options = []
        for i in range(1, 11):
            opt = question_doc.get(f"option_{i}")
            if opt:
                options.append(opt)

        # Get saved response
        saved_row = next(
            (d for d in self.str_test_response
            if str(d.question_link) == str(question_doc.name)),
            None
        )

        saved_response = saved_row.response if saved_row else None

        return {
            "question": question_doc.question,
            "question_type": question_doc.type,
            "subject": question_sub,
            "options": options,
            "multiple_correct": question_doc.multiple_correct_answers,
            "is_last": (index == total - 1),
            "no_of_options": question_doc.no_of_options,
            "saved_response": saved_response,
            "completed": False
        }
    
    
    @frappe.whitelist()
    def next_question(self, selected_option=None, user_input=None, open_ended=None):

        test = frappe.get_doc("Str Psychometric Test", self.test_type)
        questions = test.str_psychometric_test_question

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

        # ----------------------------
        # MCQ TYPE
        # ----------------------------
        if question_type == "Choices":

            # 🔹 SINGLE CORRECT
            if not question_doc.multiple_correct_answers:

                response = selected_option
                correct_ans = get_correct_answer(question_doc)

                if response == correct_ans:
                    mark = max_marks
                else:
                    mark = 0

            # 🔹 MULTIPLE CORRECT
            else:
                
                # selected_option will come as list
                if isinstance(selected_option, str):
                    selected_option = [selected_option]
                    correct_ans = None

                response = ", ".join(selected_option) if selected_option else ""

                for i in range(1, 11):
                    opt = question_doc.get(f"option_{i}")
                    is_correct = question_doc.get(f"is_correct_{i}")
                    weight = question_doc.get(f"option_{i}_weightage") or 0

                    if opt and is_correct and selected_option and opt in selected_option:
                        mark = weight

        # ----------------------------
        # USER INPUT
        # ----------------------------
        elif question_type == "User Input":

            response = user_input
            correct_ans = question_doc.possibility_1

            if response and correct_ans:
                if response.strip().lower() == correct_ans.strip().lower():
                    mark = max_marks

        # ----------------------------
        # OPEN ENDED
        # ----------------------------
        elif question_type == "Open Ended":

            response = open_ended
            correct_ans = None
            mark = 0
            max_marks = 0

        # ----------------------------
        # SAVE RESPONSE (Child Table)
        # ----------------------------

# ----------------------------
# SAVE RESPONSE (Child Table)
# ----------------------------

        existing_row = next(
            (d for d in self.str_test_response if str(d.question) == str(question_doc.name)),
            None
        )

        if not existing_row:
            existing_row = self.append("str_test_response", {})

        row = existing_row
        
        question_sub = frappe.get_value("Str Psychometric Test Question", {"question_detail": question_doc.question, "parent": self.test_type}, "psychometric_test_subject")
        # frappe.throw(str(question_sub))
        row.question = question_doc.question
        row.question_link = question_doc.name
        row.response = response
        row.correct_ans = correct_ans
        row.maximum_marks = max_marks
        row.mark = mark
        row.subject = question_sub
        row.type = question_type

        # ----------------------------
        # MOVE TO NEXT QUESTION
        # ----------------------------

        if self.question_index < total - 1:
            self.question_index += 1

        self.save(ignore_permissions=True)

        if self.question_index >= total:
            return {"completed": True}

        next_row = questions[self.question_index]
        next_doc = frappe.get_doc("Str Question", next_row.question)

        # Dynamic options
        options = []
        for i in range(1, 11):
            opt = next_doc.get(f"option_{i}")
            if opt:
                options.append(opt)
                
        #     is_last = False
        # total_count = total + 1
        # if self.question_index >= total_count:
        #     is_last = True

        # # ✅ SET FIELD VALUE IN DOC
        # self.is_last = is_last
        # self.save(ignore_permissions=True)

        return {
            "question": next_doc.question,
            "question_type": next_doc.type,
            "options": options,
            "multiple_correct": next_doc.multiple_correct_answers,
            "is_last": (self.question_index == total - 1),
            "subject": question_sub,
            "completed": False
        }

        


    @frappe.whitelist()
    def previous_question(self):

        if not self.question_index or self.question_index <= 0:
            return

        # Move back
        self.question_index -= 1

        test = frappe.get_doc("Str Psychometric Test", self.test_type)
        questions = test.str_psychometric_test_question

        question_row = questions[self.question_index]
        question_doc = frappe.get_doc("Str Question", question_row.question)

        # Get saved response
        saved_row = None
        for d in self.str_test_response:
            if d.question == question_doc.name:
                saved_row = d
                break

        response = saved_row.response if saved_row else None

        # Get dynamic options
        options = []
        for i in range(1, 11):
            opt = question_doc.get(f"option_{i}")
            if opt:
                options.append(opt)

        question_sub = frappe.get_value("Str Psychometric Test Question", {"question_detail": question_doc.question, "parent": self.test_type}, "psychometric_test_subject")
        self.save(ignore_permissions=True)

        return {
            "question": question_doc.question,
            "question_type": question_doc.type,
            "options": options,
            "saved_response": response,
            "multiple_correct": question_doc.multiple_correct_answers,
            "no_of_options": question_doc.no_of_options,
            "subject": question_sub,
            "is_last": False,
            "completed": False
        }




def get_correct_answer(doc):

    if doc.is_correct_1:
        return doc.option_1
    if doc.is_correct_2:
        return doc.option_2
    if doc.is_correct_3:
        return doc.option_3
    if doc.is_correct_4:
        return doc.option_4

    return None
