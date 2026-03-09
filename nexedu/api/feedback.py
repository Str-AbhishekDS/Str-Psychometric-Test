import frappe
import requests
import json


@frappe.whitelist()
def get_module_feedback_analytics(module=None, doctype_name=None, feedback_form=None, user=None, from_date=None, to_date=None):

    conditions = []
    values = []

    if module:
        conditions.append("fr.module_type=%s")
        values.append(module)

    if doctype_name:
        conditions.append("fr.doctype_name=%s")
        values.append(doctype_name)

    if feedback_form:
        conditions.append("fr.feedback_form=%s")
        values.append(feedback_form)

    if user:
        conditions.append("fr.user=%s")
        values.append(user)

    if from_date:
        conditions.append("fr.submitted_date >= %s")
        values.append(from_date)

    if to_date:
        conditions.append("fr.submitted_date <= %s")
        values.append(to_date)

    where_clause = ""

    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)


    rows = frappe.db.sql(f"""
        SELECT
            fa.question,
            fa.idx,
            fa.answer
        FROM `tabFeedback Answer` fa
        JOIN `tabFeedback Response` fr
        ON fa.parent = fr.name
        {where_clause}
        ORDER BY fa.idx
    """, values, as_dict=True)


    if not rows:
        return []


    questions = {}

    for r in rows:

        q = r.question

        if q not in questions:
            questions[q] = []

        questions[q].append(r.answer)


    result = []

    for q, answers in questions.items():

        rating_values = [
            int(a) for a in answers
            if str(a).isdigit() and 1 <= int(a) <= 5
        ]


        # Rating type
        if rating_values:

            avg_rating = sum(rating_values) / len(rating_values)

            result.append({
                "question": q,
                "type": "rating",
                "distribution": [{
                    "answer": "Rating",
                    "percent": round((avg_rating / 5) * 100, 2)
                }]
            })

            continue


        # Yes/No/Text
        counts = {}

        for a in answers:
            counts[a] = counts.get(a, 0) + 1

        total = len(answers)

        dist = []

        for k, v in counts.items():
            dist.append({
                "answer": k,
                "percent": round((v / total) * 100, 2)
            })

        result.append({
            "question": q,
            "type": "other",
            "distribution": dist
        })


    return result


@frappe.whitelist()
def generate_ai_feedback(module=None, from_date=None, to_date=None, doctype_name=None, feedback_form=None, user=None):

    # if not module:
    #     frappe.throw("Please select module first.")

    analytics = get_module_feedback_analytics(
        module=module,
        doctype_name=doctype_name,
        feedback_form=feedback_form,
        user=user,
        from_date=from_date,
        to_date=to_date
    )

    prompt = f"""
You are an expert feedback analyst.

Analyze the following student feedback analytics data.

Return the result STRICTLY in this format:

Working Well:
- bullet point
- bullet point

Needs Improvement:
- bullet point
- bullet point

Rules:
1. Do NOT mix both sections.
2. If there are no positive points write:
Working Well:
None

3. If there are no improvements write:
Needs Improvement:
None

4. Keep answers short and clear.
5. Do NOT explain the data.
6. Only return the two sections.

Feedback Data:
{json.dumps(analytics)}
"""

    try:

        response = requests.post(
            "http://192.168.1.76:11434/api/generate",
            json={
                "model": "qwen2.5:3b",
                "prompt": prompt,
                "stream": False
            },
            timeout=120
        )

        data = response.json()

        frappe.log_error(json.dumps(data, indent=2), "AI FEEDBACK RAW RESPONSE")

        result = data.get("response", "").strip()

        if not result:
            return "AI could not generate feedback."

        if "Working Well:" not in result:
            result = "Working Well:\nNone\n\n" + result

        if "Needs Improvement:" not in result:
            result += "\n\nNeeds Improvement:\nNone"

        return result


    except requests.exceptions.ConnectionError:
        return "AI server not reachable."

    except requests.exceptions.Timeout:
        return "AI request timed out."

    except Exception as e:
        frappe.log_error(str(e), "AI Feedback Error")
        return "Unexpected AI error occurred."