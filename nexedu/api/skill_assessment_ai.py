import json
from pathlib import Path
from urllib import error, request

import frappe
from frappe.utils import cint, now_datetime

from nexedu.api.skill_assessment_config import (
    MODEL_NAME,
    OLLAMA_BASE_URL,
    PASS_SCORE,
    QUESTION_COUNT,
    QUESTION_GENERATION_ATTEMPTS,
    QUESTION_MAX_TOKENS,
    REQUEST_TIMEOUT_SECONDS,
)


PROMPTS_FILE = Path(__file__).with_name("skill_assessment_skills.md")
VALID_LEVELS = {"Beginner", "Intermediate", "Advanced", "Expert"}
ANSWER_KEYS = {"A": 0, "B": 1, "C": 2, "D": 3}
QUESTION_TYPES = {"mcq", "short_answer", "long_answer", "problem_solving"}
QUESTION_TYPE_ALIASES = {
    "multiple_choice": "mcq",
    "multiple_choice_question": "mcq",
    "short": "short_answer",
    "written_answer": "short_answer",
    "open_ended": "long_answer",
    "essay": "long_answer",
    "coding": "problem_solving",
    "coding_problem": "problem_solving",
    "practical": "problem_solving",
}


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
            "format": "json",
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


def _normalise_questions(data):
    if not isinstance(data, dict):
        raise ValueError("Model response must be a JSON object")
    questions = data.get("questions")
    if not isinstance(questions, list) or len(questions) != QUESTION_COUNT:
        count = len(questions) if isinstance(questions, list) else 0
        raise ValueError("Model returned {0} questions; expected {1}".format(count, QUESTION_COUNT))

    normalised = []
    for index, item in enumerate(questions, 1):
        if not isinstance(item, dict):
            raise ValueError("Model returned an invalid question at index {0}".format(index))
        question_text = item.get("q") or item.get("question") or item.get("text")
        options = item.get("o") or item.get("options") or item.get("choices")
        question_type = str(item.get("type") or item.get("question_type") or "mcq").strip().lower()
        question_type = question_type.replace(" ", "_").replace("-", "_")
        question_type = QUESTION_TYPE_ALIASES.get(question_type, question_type)
        if question_type not in QUESTION_TYPES:
            question_type = "mcq" if options else "short_answer"
        if options is None:
            options = []
        raw_answer = item.get("a") or item.get("answer") or item.get("correct_answer") or ""
        answer = _normalise_answer(raw_answer, options or []) if question_type == "mcq" else ""
        rubric = item.get("rubric") or item.get("expected_answer") or item.get("answer_key") or ""
        difficulty = item.get("d") or item.get("difficulty") or "medium"
        if not isinstance(question_text, str) or not isinstance(options, list):
            raise ValueError("Model returned an invalid question at index {0}".format(index))
        if question_type == "mcq" and (len(options) != 4 or not answer):
            raise ValueError("Model returned an invalid MCQ at index {0}".format(index))
        if question_type != "mcq" and not str(rubric).strip():
            rubric = str(raw_answer).strip() or (
                "Evaluate technical correctness, completeness, reasoning, and practical relevance "
                "for the question. Accept equivalent valid approaches."
            )
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


def _generate_questions(skill, level):
    prompt = _fill_prompt(
        _prompt_section("Quiz prompt"),
        skill=skill,
        level=level,
        question_count=QUESTION_COUNT,
    )
    last_error = None
    for attempt in range(QUESTION_GENERATION_ATTEMPTS):
        try:
            raw = _ollama_chat(prompt, max_tokens=QUESTION_MAX_TOKENS)
            return _normalise_questions(_parse_json(raw))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            last_error = exc
            if attempt + 1 < QUESTION_GENERATION_ATTEMPTS:
                continue

    raise ValueError(
        "Model failed to return valid questions after {0} attempts: {1}".format(
            QUESTION_GENERATION_ATTEMPTS, last_error
        )
    )


def _answers_to_list(answers, questions):
    answers = _load_json_value(answers, [])
    if isinstance(answers, dict):
        values = []
        for index, question in enumerate(questions, 1):
            question_text = question.get("question") or ""
            if question_text in answers:
                values.append(answers[question_text])
            else:
                values.append(answers.get(str(index), answers.get(index, "")))
        return values
    if isinstance(answers, list):
        return answers
    frappe.throw("Answers must be a list or dict.")


def _question_type_from_text(question):
    first_word = question.strip().split(" ", 1)[0].lower()
    if first_word in {"build", "create", "design", "develop", "implement", "solve", "write"}:
        return "problem_solving"
    return "long_answer"


def _build_submission(student, skill, level, answers):
    try:
        answers = _load_json_value(answers, {})
    except json.JSONDecodeError:
        frappe.throw("Answers must be a complete, valid JSON question-to-answer dict.")
    if not isinstance(answers, dict) or not answers:
        frappe.throw("Answers must be a non-empty question-to-answer dict.")

    questions = []
    answer_map = {}
    for index, (question_text, submitted) in enumerate(answers.items(), 1):
        question_text = str(question_text or "").strip()
        if not question_text:
            frappe.throw("Every submitted answer must include its question text.")

        question_type = _question_type_from_text(question_text)
        options = []
        if isinstance(submitted, dict):
            selected = submitted.get("answer", submitted.get("student_answer", ""))
            requested_type = str(submitted.get("type") or "").strip().lower().replace("-", "_").replace(" ", "_")
            requested_type = QUESTION_TYPE_ALIASES.get(requested_type, requested_type)
            if requested_type in QUESTION_TYPES:
                question_type = requested_type
            if isinstance(submitted.get("options"), list):
                options = [str(option).strip() for option in submitted["options"]]
        else:
            selected = submitted

        questions.append(
            {
                "index": index,
                "type": question_type,
                "question": question_text,
                "options": options,
                "answer": "",
                "rubric": (
                    "Evaluate technical correctness, completeness, reasoning, and practical relevance. "
                    "Accept equivalent valid approaches."
                ),
                "difficulty": "hard" if level in {"Advanced", "Expert"} else "medium",
                "source": "submitted",
            }
        )
        answer_map[question_text] = selected

    return {
        "student": student,
        "skill": skill,
        "level": level,
        "questions": questions,
        "model": MODEL_NAME,
    }, answer_map


def _evaluate_written_answer(assessment, question, selected):
    question_text = question["question"]
    if question.get("options"):
        question_text = "{0} Options: {1}".format(question_text, "; ".join(question["options"]))
    prompt = _fill_prompt(
        _prompt_section("Evaluation prompt"),
        skill=assessment["skill"],
        level=assessment["level"],
        question_type=question["type"],
        question=question_text,
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


def _score_questions(assessment, answers):
    questions = assessment["questions"]
    answers = _answers_to_list(answers, questions)
    if len(answers) != len(questions):
        frappe.throw("Expected {0} answers.".format(len(questions)))

    breakdown = []
    for question, answer in zip(questions, answers):
        selected = str(answer or "").strip()
        if question.get("type") == "mcq" and question.get("answer"):
            selected = _normalise_answer(selected, question.get("options") or [])
            answer_score = 100 if selected == question["answer"] else 0
            correct = answer_score == 100
            evaluation_comment = ""
        else:
            evaluation = _evaluate_written_answer(assessment, question, selected)
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


def _result_feedback(assessment, scores):
    questions = assessment["questions"]
    correct_topics = "; ".join(
        question["question"] for question, result in zip(questions, scores["breakdown"]) if result["is_correct"]
    ) or "none"
    missed_topics = "; ".join(
        question["question"] for question, result in zip(questions, scores["breakdown"]) if not result["is_correct"]
    ) or "none"
    prompt = _fill_prompt(
        _prompt_section("Result prompt"),
        skill=_skill_prompt_name(assessment["skill"], assessment["level"]),
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


def _store_skill_test(assessment, scores, feedback, answers):
    answer_list = _answers_to_list(answers, assessment["questions"])
    question_type_counts = {}
    for question in assessment["questions"]:
        question_type = question.get("type") or "question"
        question_type_counts[question_type] = question_type_counts.get(question_type, 0) + 1

    test_result = {
        "attempt": {
            "submitted_at": str(now_datetime()),
            "model": MODEL_NAME,
            "student": assessment["student"],
            "skill": assessment["skill"],
            "level": assessment["level"],
            "question_count": len(assessment["questions"]),
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
        "questions": assessment["questions"],
        "evaluation_breakdown": scores["breakdown"],
    }
    attempts = frappe.db.count(
        "Skill Test",
        filters={
            "student": assessment["student"],
            "skill_name": assessment["skill"],
            "level": assessment["level"],
        },
    )
    doc = frappe.get_doc(
        {
            "doctype": "Skill Test",
            "student": assessment["student"],
            "skill_name": assessment["skill"],
            "level": assessment["level"],
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

    safe_questions = _safe_questions(questions)
    return {
        "name": student,
        "skill": skill,
        "level": level,
        "no_of_questions": len(safe_questions),
        "questions": safe_questions,
    }


@frappe.whitelist()
def submit_skill_test_answers(student=None, skill=None, level=None, answers=None):
    student = (student or "").strip()
    skill = (skill or "").strip()
    level = _normalise_level(level)
    if not student:
        frappe.throw("Student is required.")
    if not skill:
        frappe.throw("Skill is required.")
    _student_exists(student)
    assessment, answers = _build_submission(student, skill, level, answers)

    scores = _score_questions(assessment, answers)
    try:
        feedback = _result_feedback(assessment, scores)
    except (RuntimeError, ValueError, json.JSONDecodeError):
        frappe.log_error(frappe.get_traceback(), "Skill Assessment Feedback Error")
        feedback = {
            "summary": "Quiz completed.",
            "strengths": [],
            "gaps": [],
            "next_step": "Review the missed concepts and retry.",
            "status": "verified" if scores["passed"] else "not_verified",
        }

    skill_test = _store_skill_test(assessment, scores, feedback, answers)
    return {
        "skill_test": skill_test,
        "name": assessment["student"],
        "student": assessment["student"],
        "skill": assessment["skill"],
        "level": assessment["level"],
        "score": scores["score"],
        "status": scores["verification_status"],
        "verification_status": "verified" if scores["passed"] else "not_verified",
        "passed": scores["passed"],
        "pass_score": PASS_SCORE,
        "total_correct": scores["total_correct"],
        "total_questions": scores["total_questions"],
        "feedback": feedback,
        "question_answers": [
            {
                "question": item["question"],
                "answer": item["selected_answer"],
                "type": item["type"],
            }
            for item in scores["breakdown"]
        ],
        "breakdown": scores["breakdown"],
    }


@frappe.whitelist()
def start_skill_test(student=None, skill=None, level=None):
    return get_skill_test_questions(student=student, skill=skill, level=level)


@frappe.whitelist()
def submit_skill_test(student=None, skill=None, level=None, answers=None):
    return submit_skill_test_answers(
        student=student,
        skill=skill,
        level=level,
        answers=answers,
    )
