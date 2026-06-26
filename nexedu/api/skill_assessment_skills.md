# Skill verification prompts

`QUESTION_COUNT = 5` and `PASS_SCORE = 60` are fixed product rules. Keep prompts compact: skill and level are the variables sent when a quiz is generated.

## Quiz prompt

```text
Create exactly {question_count} fair questions that verify practical {skill} knowledge for a {level} learner. Match difficulty and question type to this level. Beginner should use mostly mcq and short_answer for fundamentals and simple use cases. Intermediate should mix mcq, short_answer, and problem_solving for applied concepts. Advanced should mix mcq, long_answer, and problem_solving for deeper reasoning, edge cases, and tradeoffs. Expert should use mostly long_answer and problem_solving, with at most one mcq, for mastery, architecture-level judgement, optimization, and nuanced scenarios. Cover distinct essentials. Return JSON only: {"questions":[{"type":"mcq|short_answer|long_answer|problem_solving","q":"...","o":["...","...","...","..."],"a":"A","rubric":"what a correct written answer must include","d":"easy|medium|hard"}]}. For mcq, include o and a where a is A-D. For non-mcq, set o to [] and a to "" and include a concise rubric. Keep every JSON string on one line with no raw line breaks or tab characters. No markdown or extra keys.
```

## Evaluation prompt

```text
Evaluate this {skill} {level} answer. Question type: {question_type}. Question: {question}. Rubric: {rubric}. Student answer: {student_answer}. Return JSON only: {"score":0-100,"is_correct":true|false,"comment":"one concise reason"}. Mark is_correct true only when score is at least {pass_score}. Keep every JSON string on one line with no raw line breaks or tab characters. No markdown or extra keys.
```

## Result prompt

```text
Return JSON only for this {skill} quiz. Score {score}% ({correct}/{total}); passed={passed}. Correct topics: {correct_topics}. Missed topics: {missed_topics}. Schema: {"summary":"one concise sentence","strengths":["up to 2 concise items"],"gaps":["up to 2 concise items"],"next_step":"one concrete action","status":"verified|not_verified"}. status must match passed. No markdown or extra keys.
```

The UI owns the score and verification decision. The model only supplies the consistently structured learning feedback.
