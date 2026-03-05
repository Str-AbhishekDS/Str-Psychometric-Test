import frappe
import requests
import json


@frappe.whitelist()
def get_module_feedback_analytics(module=None, from_date=None, to_date=None):

    conditions = []
    values = []

    # -------------------------
    # Module filter
    # -------------------------
    if module:
        conditions.append("fr.module_type = %s")
        values.append(module)

    # -------------------------
    # Date filters
    # -------------------------
    if from_date:
        conditions.append("fr.submitted_date >= %s")
        values.append(from_date)

    if to_date:
        conditions.append("fr.submitted_date <= %s")
        values.append(to_date)

    # Always ensure question exists
    conditions.append("fa.question IS NOT NULL")

    where_clause = "WHERE " + " AND ".join(conditions)

    # -------------------------
    # Fetch questions in correct order
    # -------------------------
    questions = frappe.db.sql(f"""
        SELECT 
            MIN(fa.name) as row_id,
            fa.question,
            fa.idx
        FROM `tabFeedback Answer` fa
        JOIN `tabFeedback Response` fr
            ON fa.parent = fr.name
        {where_clause}
        GROUP BY fa.idx
        ORDER BY fa.idx
    """, values, as_dict=True)

    result = []

    # -------------------------
    # Calculate distributions
    # -------------------------
    for q in questions:

        responses = frappe.db.sql(f"""
            SELECT 
                fa.answer,
                COUNT(*) as total
            FROM `tabFeedback Answer` fa
            JOIN `tabFeedback Response` fr
                ON fa.parent = fr.name
            WHERE fa.idx = %s
            AND fa.answer IS NOT NULL
            AND fa.answer != ''
            GROUP BY fa.answer
        """, q.idx, as_dict=True)

        total_responses = sum([r.total for r in responses])

        data = []

        for r in responses:

            percent = 0

            # Detect rating answers (1–5)
            if str(r.answer).isdigit():

                rating_value = int(r.answer)

                if 1 <= rating_value <= 5:
                    percent = round((rating_value / 5) * 100, 2)

            else:

                if total_responses > 0:
                    percent = round((r.total / total_responses) * 100, 2)

            data.append({
                "answer": r.answer,
                "percent": percent
            })

        result.append({
            "question": q.question,
            "distribution": data
        })

    return result



# =========================================================
# AI FEEDBACK GENERATION
# =========================================================

@frappe.whitelist()
def generate_ai_feedback(module=None, from_date=None, to_date=None):

    if not module:
        frappe.throw("Please select module first.")

    analytics = get_module_feedback_analytics(module, from_date, to_date)

    prompt = f"""
Analyze the following feedback summary.

Return only:

What is working well:
- bullet points

What needs improvement:
- bullet points

Feedback Data:
{json.dumps(analytics)}
"""

    try:

        response = requests.post(
            "http://192.168.1.70:11434/api/generate",
            json={
                "model": "qwen2.5:3b",
                "prompt": prompt,
                "stream": False
            },
            timeout=120
        )

        data = response.json()

        if "response" in data:
            return data["response"]

        if "error" in data:
            return f"AI Error: {data['error']}"

        return "AI returned unexpected response."

    except requests.exceptions.ConnectionError:
        return "AI server not reachable."

    except Exception as e:
        frappe.log_error(str(e), "AI Feedback Error")
        return str(e)