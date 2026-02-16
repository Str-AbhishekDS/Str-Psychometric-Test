import frappe
from frappe.model.document import Document


class StudentTestScreen(Document):

    def on_submit(self):

        obtained_score = 0
        total_score = 0

        for row in self.str_test_response:
            obtained_score += row.mark or 0
            total_score += row.maximum_marks or 0

        percentage = 0
        if total_score > 0:
            percentage = (obtained_score / total_score) * 100

        submission = frappe.new_doc("Str Psychometric Test Submission")
        submission.member = frappe.session.user
        submission.psychometric_test = self.test_type
        submission.score = obtained_score
        submission.score_out_of = total_score
        submission.percentage = percentage
        submission.passing_percentage = 100

        for row in self.str_test_response:
            submission.append("str_test_response", {
                "question": row.question,
                "response": row.response,
                "correct_ans": row.correct_ans,
                "maximum_marks": row.maximum_marks,
                "mark": row.mark,
                "type": row.type
            })

        submission.insert(ignore_permissions=True)
        submission.submit()

        frappe.msgprint(f"Test Submitted Successfully! Score: {obtained_score}/{total_score}")



    @frappe.whitelist()
    def load_question(self):

        test = frappe.get_doc("Str Psychometric Test", self.test_type)
        questions = test.str_psychometric_test_question
  
        index = self.question_index or 0
        total = len(questions)

        if index >= total:
            # index -= 1
            return {"completed": True}

        question_row = questions[index]
        question_doc = frappe.get_doc("Str Question", question_row.question)

        return {
            "question": question_doc.question,
            "question_type": question_doc.type,
            "a": question_doc.option_1,
            "b": question_doc.option_2,
            "c": question_doc.option_3,
            "d": question_doc.option_4,
            "is_last": (index == total - 1),
            "completed": False
        }



    @frappe.whitelist()
    def next_question(self, selected_option=None, user_input=None, open_ended=None):

        test = frappe.get_doc("Str Psychometric Test", self.test_type)
        questions = test.str_psychometric_test_question
      
        
        
        index = self.question_index or 0
        total = len(questions)
      
        question_row = questions[index]
        question_doc = frappe.get_doc("Str Question", question_row.question)
        question_type = question_doc.type

        response = None
        correct_ans = None
        max_marks = 0
        mark = 0


        if question_type == "Choices":

            response = selected_option
            correct_ans = get_correct_answer(question_doc)
            max_marks = question_row.marks

            if response == correct_ans:
                mark = max_marks


        elif question_type == "User Input":

            response = user_input
            correct_ans = question_doc.possibility_1
            max_marks = question_row.marks

            if response and correct_ans:
                if response.strip().lower() == correct_ans.strip().lower():
                    mark = max_marks


        elif question_type == "Open Ended":

            response = open_ended
            correct_ans = None
            max_marks = 0
            mark = 0


        existing_row = None

        for d in self.str_test_response:
            if d.question == question_doc.question:
                existing_row = d
                break

        if existing_row:
            row = existing_row
        else:
            row = self.append("str_test_response", {})

        row.question = question_doc.question
        row.response = response
        row.correct_ans = correct_ans
        row.maximum_marks = max_marks
        row.mark = mark
        row.type = self.question_type
        
        if self.question_index < total - 1:
            self.question_index = index + 1
        else:
            self.question_index = total - 1

        # self.question_index = index + 1
        self.save(ignore_permissions=True)

        if self.question_index >= total:
            return {"completed": True}

        next_row = questions[self.question_index]
        next_doc = frappe.get_doc("Str Question", next_row.question)
    
        return {
            "question": next_doc.question,
            "question_type": next_doc.type,
            "a": next_doc.option_1,
            "b": next_doc.option_2,
            "c": next_doc.option_3,
            "d": next_doc.option_4,
            "is_last": (self.question_index == total - 1),
            "completed": False
        }
        


    @frappe.whitelist()
    def previous_question(self):

        if not self.question_index or self.question_index <= 0:
            return

        self.question_index -= 1

        test = frappe.get_doc("Str Psychometric Test", self.test_type)
        questions = test.str_psychometric_test_question

        question_row = questions[self.question_index]
        question_doc = frappe.get_doc("Str Question", question_row.question)

        saved_row = None
        for d in self.str_test_response:
            if d.question == question_doc.name:
                saved_row = d
                break

        response = saved_row.response if saved_row else None

        self.save(ignore_permissions=True)

        return {
            "question": question_doc.question,
            "question_type": question_doc.type,
            "a": question_doc.option_1,
            "b": question_doc.option_2,
            "c": question_doc.option_3,
            "d": question_doc.option_4,
            "saved_response": response
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
