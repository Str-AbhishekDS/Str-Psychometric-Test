import frappe
import requests
import json

@frappe.whitelist()
def get_module_feedback_analytics(module=None, from_date=None, to_date=None):

    conditions = []
    values = []

    if module:
        conditions.append("fr.module_type = %s")
        values.append(module)

    if from_date:
        conditions.append("fr.submitted_date >= %s")
        values.append(from_date)

    if to_date:
        conditions.append("fr.submitted_date <= %s")
        values.append(to_date)

    conditions.append("fa.question IS NOT NULL")

    where_clause = "WHERE " + " AND ".join(conditions)

    questions = frappe.db.sql(f"""
        SELECT 
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
            {"AND fr.module_type = %s" if module else ""}
            {"AND fr.submitted_date >= %s" if from_date else ""}
            {"AND fr.submitted_date <= %s" if to_date else ""}
            GROUP BY fa.answer
        """, [q.idx] + ([module] if module else []) + ([from_date] if from_date else []) + ([to_date] if to_date else []), as_dict=True)

        answers = [r.answer for r in responses]

        # Detect rating question
        rating_values = [int(a) for a in answers if str(a).isdigit() and 1 <= int(a) <= 5]

        if rating_values:

            avg_rating = sum(rating_values) / len(rating_values)
            percent = round((avg_rating / 5) * 100, 2)

            result.append({
                "question": q.question,
                "type": "rating",
                "distribution": [
                    {
                        "answer": "Rating",
                        "percent": percent
                    }
                ]
            })

            continue

        # yes/no or text
        counts = {}

        for ans in answers:
            counts[ans] = counts.get(ans, 0) + 1

        total = len(answers)

        data = []

        for ans, count in counts.items():

            percent = round((count / total) * 100, 2)

            data.append({
                "answer": ans,
                "percent": percent
            })

        result.append({
            "question": q.question,
            "type": "other",
            "distribution": data
        })

    return result


@frappe.whitelist()
def generate_ai_feedback(module=None, from_date=None, to_date=None):

    if not module:
        frappe.throw("Please select module first.")

    analytics = get_module_feedback_analytics(module, from_date, to_date)

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
            "http://192.168.1.70:11434/api/generate",
            json={
                "model": "qwen2.5:3b",
                "prompt": prompt,
                "stream": False
            },
            timeout=120
        )

        data = response.json()

        # Log raw AI response for debugging
        frappe.log_error(json.dumps(data, indent=2), "AI FEEDBACK RAW RESPONSE")

        result = data.get("response", "").strip()

        if not result:
            return "AI could not generate feedback."

        # Safety check to ensure both sections exist
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