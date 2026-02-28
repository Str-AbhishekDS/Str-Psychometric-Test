import frappe
import requests


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
        The student's dominant personality trait is {dominant_trait}.

        Write a professional personality report using this exact structure.

        Personality: {dominant_trait}

        Reason:
        Write 2 to 3 short lines explaining this personality clearly.

        Strengths:
        Write exactly 4 short bullet points.

        Recommendations:
        Write exactly 4 short bullet points.

        Do not repeat these instructions.
        Do not include brackets.
        Do not include example text.
        Do not leave placeholders.
        Start directly from 'Personality:'.
        """

    result = "AI could not generate result."

    try:
        response = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={
                "model": "tinyllama",
                "prompt": prompt,
                "stream": False
            },
            timeout=120
        )

        if response.status_code != 200:
            result = f"AI Server Error: {response.text}"
        else:
            data = response.json()
            result = data.get("response") or f"AI Error: {data.get('error')}"

    except requests.exceptions.Timeout:
        result = "AI Timeout: Model took too long to respond."

    except requests.exceptions.ConnectionError:
        result = "AI Connection Error: Ollama server not reachable."

    except Exception as e:
        result = f"Unexpected AI Error: {str(e)}"

    result = clean_ai_output(result, dominant_trait)

    doc.db_set("ai_result", result)

    return result



def clean_ai_output(text, dominant_trait):

    if not text:
        return "AI returned empty response."

    unwanted_phrases = [
        "Sure thing",
        "Here's an example",
        "Keep the output under",
        "Do NOT",
        "Note:",
        "In conclusion",
        "This personal opinion"
    ]

    for phrase in unwanted_phrases:
        text = text.replace(phrase, "")

    if "Personality:" in text:
        text = text[text.index("Personality:"):]

    if "Personality:" not in text:
        text = f"""Personality: {dominant_trait}

Reason:
This personality reflects the student's dominant psychometric trait.

Strengths:
- Self-aware
- Capable of growth
- Adaptable
- Motivated

Recommendations:
- Focus on skill development
- Seek mentorship
- Set clear goals
- Pursue suitable career paths
"""

    return text.strip()