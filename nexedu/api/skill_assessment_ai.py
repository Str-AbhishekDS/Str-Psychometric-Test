import json
import uuid
from pathlib import Path
from urllib import error, request

import frappe
from frappe.utils import cint, now_datetime

from nexedu.api.skill_assessment_config import (
    CACHE_TTL_SECONDS,
    MODEL_NAME,
    OLLAMA_BASE_URL,
    PASS_SCORE,
    QUESTION_COUNT,
    REQUEST_TIMEOUT_SECONDS,
)


PROMPTS_FILE = Path(__file__).with_name("skill_assessment_skills.md")
VALID_LEVELS = {"Beginner", "Intermediate", "Advanced", "Expert"}
ANSWER_KEYS = {"A": 0, "B": 1, "C": 2, "D": 3}
QUESTION_TYPES = {"mcq", "short_answer", "long_answer", "problem_solving"}


def _prompt_section(name):
    text = PROMPTS_FILE.read_text(encoding="utf-8")
    marker = "## {0}\n\n```text\n".format(name)
    return text.split(marker, 1)[1].split("\n```", 1)[0].strip()


def _fill_prompt(template, **values):
    for name, value in values.items():
        template = template.replace("{" + name + "}", str(value))
    return template


def _parse_json(raw):
    raw = (raw or "").replace("```json", "").replace("```", "").strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Model did not return JSON")
    return json.loads(raw[start : end + 1], strict=False)


def _ollama_chat(prompt, system="JSON only.", max_tokens=1200):
    base_url = OLLAMA_BASE_URL.rstrip("/")
    payload = json.dumps(
        {
            "model": MODEL_NAME,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "think": False,
            "options": {"temperature": 0.2, "num_predict": max_tokens},
        }
    ).encode("utf-8")
    api_request = request.Request(
        "{0}/api/chat".format(base_url),
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(api_request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:300]
        raise RuntimeError("Ollama API error ({0}): {1}".format(exc.code, detail))
    except error.URLError as exc:
        raise RuntimeError("Could not connect to Ollama at {0}: {1}".format(base_url, exc.reason))
    except TimeoutError:
        raise RuntimeError("Ollama took too long to respond. Please try again.")

    content = (data.get("message") or {}).get("content")
    if not content:
        raise RuntimeError("Ollama returned an empty response.")
    return content.strip()


def _normalise_level(level):
    level = (level or "").strip()
    if level.lower() == "exper":
        level = "Expert"
    if level not in VALID_LEVELS:
        frappe.throw("Level must be one of: Beginner, Intermediate, Advanced, Expert")
    return level


def _load_json_value(value, default):
    if value is None:
        return default
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return default
        return json.loads(value)
    return value


def _cache_key(session_id):
    return "skill_assessment_session:{0}".format(session_id)


def _set_cached_session(session_id, session):
    cache = frappe.cache()
    value = json.dumps(session)
    try:
        cache.set_value(_cache_key(session_id), value, expires_in_sec=CACHE_TTL_SECONDS)
    except TypeError:
        cache.set_value(_cache_key(session_id), value)


def _get_cached_session(session_id):
    if not session_id:
        return None
    value = frappe.cache().get_value(_cache_key(session_id))
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if not value:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


def _safe_questions(questions):
    hidden_keys = {"answer", "rubric"}
    return [{key: value for key, value in question.items() if key not in hidden_keys} for question in questions]


def _skill_prompt_name(skill, level):
    return "{0} level {1}".format(level, skill)


def _normalise_answer(answer, options):
    answer = str(answer or "").strip()
    upper_answer = answer.upper()
    if upper_answer in ANSWER_KEYS:
        return upper_answer

    for index, option in enumerate(options):
        if answer.lower() == str(option).strip().lower():
            return "ABCD"[index]

    return ""


def _generate_questions(skill, level):
    prompt = _fill_prompt(
        _prompt_section("Quiz prompt"),
        skill=skill,
        level=level,
        question_count=QUESTION_COUNT,
    )
    data = _parse_json(_ollama_chat(prompt, max_tokens=1400))
    questions = data.get("questions")
    if not isinstance(questions, list) or len(questions) != QUESTION_COUNT:
        count = len(questions) if isinstance(questions, list) else 0
        raise ValueError("Model returned {0} questions; expected {1}".format(count, QUESTION_COUNT))

    normalised = []
    for index, item in enumerate(questions, 1):
        question_text = item.get("q") or item.get("question") or item.get("text")
        options = item.get("o") or item.get("options") or item.get("choices")
        question_type = str(item.get("type") or item.get("question_type") or "mcq").strip().lower()
        question_type = question_type.replace(" ", "_").replace("-", "_")
        if question_type not in QUESTION_TYPES:
            question_type = "mcq" if options else "short_answer"
        if options is None:
            options = []
        answer = _normalise_answer(item.get("a") or item.get("answer") or item.get("correct_answer"), options or [])
        rubric = item.get("rubric") or item.get("expected_answer") or item.get("answer_key") or ""
        difficulty = item.get("d") or item.get("difficulty") or "medium"
        if not isinstance(question_text, str) or not isinstance(options, list):
            raise ValueError("Model returned an invalid question at index {0}".format(index))
        if question_type == "mcq" and (len(options) != 4 or not answer):
            raise ValueError("Model returned an invalid MCQ at index {0}".format(index))
        if question_type != "mcq" and not str(rubric).strip():
            raise ValueError("Model returned an invalid question at index {0}".format(index))
        normalised.append(
            {
                "index": index,
                "type": question_type,
                "question": question_text.strip(),
                "options": [str(option).strip() for option in options],
                "answer": answer,
                "rubric": str(rubric).strip(),
                "difficulty": str(difficulty).strip().lower(),
                "source": "ollama",
            }
        )
    return normalised


def _answers_to_list(answers, total):
    answers = _load_json_value(answers, [])
    if isinstance(answers, dict):
        values = []
        for index in range(1, total + 1):
            values.append(answers.get(str(index), answers.get(index, answers.get(index - 1, ""))))
        return values
    if isinstance(answers, list):
        return answers
    frappe.throw("Answers must be a list or dict.")


def _evaluate_written_answer(session, question, selected):
    prompt = _fill_prompt(
        _prompt_section("Evaluation prompt"),
        skill=session["skill"],
        level=session["level"],
        question_type=question["type"],
        question=question["question"],
        rubric=question.get("rubric") or "",
        student_answer=selected,
        pass_score=PASS_SCORE,
    )
    data = _parse_json(_ollama_chat(prompt, max_tokens=300))
    score = float(data.get("score", 0) or 0)
    score = max(0, min(100, score))
    is_correct = data.get("is_correct")
    if isinstance(is_correct, str):
        is_correct = is_correct.strip().lower() == "true"
    return {
        "answer_score": score,
        "is_correct": bool(is_correct) and score >= PASS_SCORE,
        "evaluation_comment": str(data.get("comment") or "").strip(),
    }


def _score_questions(session, answers):
    questions = session["questions"]
    answers = _answers_to_list(answers, len(questions))
    if len(answers) != len(questions):
        frappe.throw("Expected {0} answers.".format(len(questions)))

    breakdown = []
    for question, answer in zip(questions, answers):
        selected = str(answer or "").strip()
        if question.get("type") == "mcq":
            selected = selected.upper()
            answer_score = 100 if selected == question["answer"] else 0
            correct = answer_score == 100
            evaluation_comment = ""
        else:
            evaluation = _evaluate_written_answer(session, question, selected)
            answer_score = evaluation["answer_score"]
            correct = evaluation["is_correct"]
            evaluation_comment = evaluation["evaluation_comment"]
        breakdown.append(
            {
                "index": question.get("index"),
                "type": question.get("type"),
                "question": question["question"],
                "selected_answer": selected,
                "correct_answer": question["answer"] if question.get("type") == "mcq" else "",
                "answer_score": answer_score,
                "is_correct": correct,
                "evaluation_comment": evaluation_comment,
                "difficulty": question.get("difficulty"),
            }
        )

    total_correct = sum(1 for item in breakdown if item["is_correct"])
    score = round(sum(item["answer_score"] for item in breakdown) / len(questions), 2) if questions else 0
    passed = score >= PASS_SCORE
    return {
        "score": score,
        "passed": passed,
        "verification_status": "Pass" if passed else "Fail",
        "total_correct": total_correct,
        "total_questions": len(questions),
        "pass_score": PASS_SCORE,
        "breakdown": breakdown,
    }


def _result_feedback(session, scores):
    questions = session["questions"]
    correct_topics = "; ".join(
        question["question"] for question, result in zip(questions, scores["breakdown"]) if result["is_correct"]
    ) or "none"
    missed_topics = "; ".join(
        question["question"] for question, result in zip(questions, scores["breakdown"]) if not result["is_correct"]
    ) or "none"
    prompt = _fill_prompt(
        _prompt_section("Result prompt"),
        skill=_skill_prompt_name(session["skill"], session["level"]),
        score=scores["score"],
        correct=scores["total_correct"],
        total=scores["total_questions"],
        passed=str(scores["passed"]).lower(),
        correct_topics=correct_topics,
        missed_topics=missed_topics,
    )
    feedback = _parse_json(_ollama_chat(prompt, max_tokens=450))
    feedback["status"] = "verified" if scores["passed"] else "not_verified"
    return feedback


def _student_exists(student):
    if not frappe.db.exists("Student", student):
        frappe.throw("Student not found: {0}".format(student))


def _store_skill_test(session, scores, feedback, answers):
    answer_list = _answers_to_list(answers, len(session["questions"]))
    question_type_counts = {}
    for question in session["questions"]:
        question_type = question.get("type") or "question"
        question_type_counts[question_type] = question_type_counts.get(question_type, 0) + 1

    test_result = {
        "attempt": {
            "session_id": session.get("session_id"),
            "submitted_at": str(now_datetime()),
            "model": MODEL_NAME,
            "student": session["student"],
            "skill": session["skill"],
            "level": session["level"],
            "question_count": len(session["questions"]),
            "question_type_counts": question_type_counts,
        },
        "result": {
            "score": scores["score"],
            "status": scores["verification_status"],
            "passed": scores["passed"],
            "pass_score": PASS_SCORE,
            "total_correct": scores["total_correct"],
            "total_questions": scores["total_questions"],
        },
        "ai_response": feedback,
        "student_answers": answer_list,
        "questions": session["questions"],
        "evaluation_breakdown": scores["breakdown"],
    }
    attempts = frappe.db.count(
        "Skill Test",
        filters={"student": session["student"], "skill_name": session["skill"], "level": session["level"]},
    )
    doc = frappe.get_doc(
        {
            "doctype": "Skill Test",
            "student": session["student"],
            "skill_name": session["skill"],
            "level": session["level"],
            "score": scores["score"],
            "status": scores["verification_status"],
            "attempts": cint(attempts) + 1,
            "test_result": json.dumps(test_result, indent=2),
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name


@frappe.whitelist()
def get_skill_test_questions(student=None, skill=None, level=None):
    student = (student or "").strip()
    skill = (skill or "").strip()
    level = _normalise_level(level)
    if not student:
        frappe.throw("Student is required.")
    if not skill:
        frappe.throw("Skill is required.")
    _student_exists(student)

    try:
        questions = _generate_questions(skill, level)
    except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
        frappe.log_error(frappe.get_traceback(), "Skill Assessment Question Error")
        frappe.throw("Could not generate skill test questions: {0}".format(exc))

    session_id = str(uuid.uuid4())
    session = {
        "session_id": session_id,
        "student": student,
        "skill": skill,
        "level": level,
        "questions": questions,
        "model": MODEL_NAME,
    }
    _set_cached_session(session_id, session)
    safe_questions = _safe_questions(questions)
    return {
        "session_id": session_id,
        "name": student,
        "skill": skill,
        "level": level,
        "no_of_questions": len(safe_questions),
        "questions": safe_questions,
    }


@frappe.whitelist()
def submit_skill_test_answers(session_id=None, student=None, skill=None, level=None, answers=None, questions=None):
    session = _get_cached_session(session_id)

    if not session:
        student = (student or "").strip()
        skill = (skill or "").strip()
        level = _normalise_level(level)
        questions = _load_json_value(questions, [])
        if not student or not skill or not questions:
            frappe.throw("Invalid or expired skill test session.")
        session = {
            "session_id": session_id,
            "student": student,
            "skill": skill,
            "level": level,
            "questions": questions,
            "model": MODEL_NAME,
        }

    scores = _score_questions(session, answers)
    try:
        feedback = _result_feedback(session, scores)
    except (RuntimeError, ValueError, json.JSONDecodeError):
        frappe.log_error(frappe.get_traceback(), "Skill Assessment Feedback Error")
        feedback = {
            "summary": "Quiz completed.",
            "strengths": [],
            "gaps": [],
            "next_step": "Review the missed concepts and retry.",
            "status": "verified" if scores["passed"] else "not_verified",
        }

    skill_test = _store_skill_test(session, scores, feedback, answers)
    return {
        "skill_test": skill_test,
        "name": session["student"],
        "skill": session["skill"],
        "level": session["level"],
        "score": scores["score"],
        "status": scores["verification_status"],
        "verification_status": "verified" if scores["passed"] else "not_verified",
        "passed": scores["passed"],
        "pass_score": PASS_SCORE,
        "total_correct": scores["total_correct"],
        "total_questions": scores["total_questions"],
        "feedback": feedback,
        "breakdown": scores["breakdown"],
    }


@frappe.whitelist()
def start_skill_test(student=None, skill=None, level=None):
    return get_skill_test_questions(student=student, skill=skill, level=level)


@frappe.whitelist()
def submit_skill_test(session_id=None, student=None, skill=None, level=None, answers=None, questions=None):
    return submit_skill_test_answers(
        session_id=session_id,
        student=student,
        skill=skill,
        level=level,
        answers=answers,
        questions=questions,
    )
