import json
from datetime import datetime
from studyloop import db
from studyloop.llm_client import chat
from studyloop.sm2 import sm2_update
from studyloop.planner import build_plan

def parse_syllabus(raw_text: str) -> dict:
    prompt = f"""You are given a course syllabus. Extract a JSON list of topics. For each topic estimate:
- difficulty: integer 1 (easy) to 5 (hard)
- est_hours: realistic hours needed for first-pass learning
Return ONLY valid JSON array. Format:
[
  {{"name": "Topic name", "difficulty": 3, "est_hours": 2.0}}
]
No prose. No markdown fences.
Syllabus:
{raw_text[:6000]}"""

    result = chat([{"role": "user", "content": prompt}])
    try:
        content = result["content"].strip().lstrip("```json").rstrip("```").strip()
        topics = json.loads(content)
    except Exception as e:
        return {"status": "error", "message": f"Failed to parse syllabus JSON: {str(e)}"}

    db.clear_topics()
    for topic in topics:
        db.insert_topic(
            topic["name"],
            int(topic["difficulty"]),
            float(topic["est_hours"]),
        )
    return {
        "status": "ok",
        "topics_added": len(topics),
    }

def schedule(reasoning: str) -> dict:
    return build_plan(reasoning)

def generate_quiz(topic_name: str, num_questions: int = 4) -> dict:
    topics = {t["name"]: t for t in db.get_all_topics()}
    if topic_name not in topics:
        return {
            "status": "error",
            "message": f"Unknown topic: {topic_name}",
        }
    num_questions = max(3, min(num_questions, 5))
    prompt = f"""Write {num_questions} multiple-choice questions to test understanding of "{topic_name}".
Each question must have exactly four options: A, B, C, and D.
Return ONLY valid JSON array in this format:
[
  {{
    "question": "Question text",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "correct_answer": "B"
  }}
]
No prose. No markdown fences."""

    result = chat([{"role": "user", "content": prompt}])
    try:
        content = result["content"].strip().lstrip("```json").rstrip("```").strip()
        questions = json.loads(content)
    except Exception as e:
        return {"status": "error", "message": f"Failed to parse quiz JSON: {str(e)}"}

    return {
        "status": "ok",
        "topic_name": topic_name,
        "questions": questions,
    }

def evaluate_quiz(topic_name: str, questions: list[dict], student_answers: dict) -> dict:
    if not questions:
        return {
            "status": "error",
            "message": "No quiz questions were provided.",
        }
    correct = 0
    results = []
    for index, question in enumerate(questions, start=1):
        student_answer = student_answers.get(str(index))
        correct_answer = question.get("correct_answer")
        is_correct = str(student_answer) == str(correct_answer)
        if is_correct:
            correct += 1
        results.append({
            "question": index,
            "student_answer": student_answer,
            "correct_answer": correct_answer,
            "correct": is_correct,
        })
    total = len(questions)
    percentage = round((correct / total) * 100, 2)
    evaluation_prompt = f"""Evaluate this student's multiple-choice quiz performance.
Topic: {topic_name}
Correct answers: {correct}/{total}
Percentage: {percentage}%
Question results: {json.dumps(results)}

Assign an SM-2 quality score from 0 to 5.
Return ONLY valid JSON object:
{{
  "quality": 4,
  "evaluation": "Short explanation of the student's performance."
}}
No prose outside JSON."""

    result = chat([{"role": "user", "content": evaluation_prompt}])
    try:
        content = result["content"].strip().lstrip("```json").rstrip("```").strip()
        evaluation = json.loads(content)
    except Exception as e:
        return {"status": "error", "message": f"Failed to parse evaluation JSON: {str(e)}"}

    return {
        "status": "ok",
        "topic_name": topic_name,
        "correct": correct,
        "total": total,
        "percentage": percentage,
        "quality": int(evaluation["quality"]),
        "evaluation": evaluation["evaluation"],
        "results": results,
    }

def log_result(topic_name: str, quality: int) -> dict:
    topics = {topic["name"]: topic for topic in db.get_all_topics()}
    topic = topics.get(topic_name)
    if not topic:
        return {
            "status": "error",
            "message": f"Unknown topic: {topic_name}",
        }
    db.insert_quiz_result(
        topic["id"],
        quality,
        datetime.now().isoformat(),
    )
    new_state = sm2_update(
        quality,
        topic["repetitions"],
        topic["ease_factor"],
        topic["interval_days"],
    )
    db.update_topic_sm2(
        topic["id"],
        new_state["repetitions"],
        new_state["ease_factor"],
        new_state["interval_days"],
        new_state["next_review_date"],
        new_state["mastered"],
    )
    return {
        "status": "ok",
        "topic_name": topic_name,
        **new_state,
    }

def replan(reasoning: str) -> dict:
    return schedule(reasoning=f"[replan] {reasoning}")

TOOL_FUNCTIONS = {
    "schedule": schedule,
    "generate_quiz": generate_quiz,
    "evaluate_quiz": evaluate_quiz,
    "log_result": log_result,
    "replan": replan,
}