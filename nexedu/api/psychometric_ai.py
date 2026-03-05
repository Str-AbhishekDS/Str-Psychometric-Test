import frappe
import requests
import time


@frappe.whitelist()
def generate_personality(docname):

    doc = frappe.get_doc("Student Test Screen", docname)

    subject_scores = {}

    for row in doc.str_psychometric_group_submission:
        subject_scores[row.subject] = row.percentage or 0

    if not subject_scores:
        doc.db_set("ai_result", "No psychometric data found.")
        return "No psychometric data found."

    dominant_trait = max(subject_scores, key=subject_scores.get)

    prompt = f"""
Dominant Trait: {dominant_trait}

Write only this format:

Personality: {dominant_trait}

Reason:
Explain in 2 short lines how this personality appears in a student's academic behavior.

Strengths:
- 4 short strengths specifically useful for a student

Keep total under 100 words.
No introduction.
No conclusion.
Stop after Strengths.
"""

    result = "AI could not generate result."

    try:
        start_time = time.time()

        response = requests.post(
            "http://192.168.1.70:11434/api/generate",
            json={
                "model": "qwen2.5:3b",
                "prompt": prompt,
                "stream": False,
                "temperature": 0.2,
                "num_predict": 150
            },
            timeout=120
        )

        end_time = time.time()
        response_time = round(end_time - start_time, 2)

        frappe.log_error(f"\n🧠 AI Response Time: {response_time} seconds\n")

        if response.status_code != 200:
            result = f"AI Server Error: {response.text}"
        else:
            data = response.json()
            result = data.get("response") or f"AI Error: {data.get('error')}"

    except requests.exceptions.Timeout:
        result = "AI Timeout: Model took too long to respond."

    except Exception as e:
        result = f"Unexpected AI Error: {str(e)}"

    doc.db_set("ai_result", result)

    return result