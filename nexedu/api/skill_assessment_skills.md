# Skill verification prompts

`QUESTION_COUNT = 5` and `PASS_SCORE = 60` are fixed product rules. Keep prompts compact: skill and level are the variables sent when a quiz is generated.

## Quiz prompt

```text
Create exactly {question_count} fair questions that verify practical {skill} knowledge for a {level} learner. {mix_instruction} Match difficulty to this level. Cover distinct essentials. Keep all questions, options, and rubrics extremely concise and brief to minimize generation time. Rubrics must be a single, short sentence of under 10 words. Return JSON only: {"questions":[{"type":"mcq|short_answer|long_answer|problem_solving","q":"...","o":["...","...","...","..."],"a":"A","rubric":"what a correct written answer must include","d":"easy|medium|hard"}]}. For mcq, include o and a where a is A-D. For non-mcq, set o to [] and a to "" and include a concise rubric. Keep every JSON string on one line with no raw line breaks or tab characters. No markdown or extra keys.
```

## Evaluation prompt

```text
Evaluate these {skill} {level} answers fairly. Note that descriptive/written answers can be expressed in many different ways (e.g., different styles, approaches, or definitions). Do not mark an answer as wrong just because the student's style, approach, or definition is different. Focus on whether the core concepts are correct. Assess the overall accuracy/correctness of the answer as a percentage (0-100). If the accuracy is less than {pass_score} percent, it is incorrect; if it is {pass_score} percent or more, it is correct. Input: {input_data}. Return JSON only matching schema: {"evaluations":[{"index":number,"score":0-100,"is_correct":true|false,"comment":"one concise reason"}]}. Mark is_correct true only when score is at least {pass_score}. Keep every JSON string on one line with no raw line breaks or tab characters. No markdown or extra keys.
```

## Result prompt

```text
Return JSON only for this {skill} quiz. Score {score}% ({correct}/{total}); passed={passed}. Correct topics: {correct_topics}. Missed topics: {missed_topics}. Strengths must only be drawn from correct topics, and gaps must only be drawn from missed topics (if there are no missed topics, gaps must be an empty list []). Schema: {"summary":"one concise sentence","strengths":["up to 2 concise items"],"gaps":["up to 2 concise items"],"next_step":"one concrete action","status":"verified|not_verified"}. status must match passed. No markdown or extra keys.
```

The UI owns the score and verification decision. The model only supplies the consistently structured learning feedback.
