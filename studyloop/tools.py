import json
from datetime import date, timedelta

from pypdf import PdfReader

from studyloop import db
from studyloop.llm_client import chat
from studyloop.sm2 import sm2_update


def parse_syllabus(raw_text: str) -> dict:
    """
    Setup step (not agent-callable, see tool_schemas.py note).

    Asks the LLM to turn raw syllabus text into a structured topic list,
    then stores it.

    This IS a Reason step — we're just calling it directly instead of
    letting the agent loop discover it, since it only ever happens once.
    """
    prompt = f"""You are given a course syllabus. Extract a JSON list of topics.
For each topic estimate:
- "difficulty": integer 1 (easy) to 5 (hard)
- "est_hours": realistic hours a student needs to first-pass learn it

Return ONLY valid JSON, a list of objects with keys:
name, difficulty, est_hours.

No prose, no markdown fences.

Syllabus:
{raw_text[:6000]}
"""

    result = chat([
        {
            "role": "user",
            "content": prompt,
        }
    ])

    topics = json.loads(result["content"])

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
    """
    Greedy day-by-day allocator.

    Walk forward from today to the exam date, filling each day's hour
    budget with whichever topic currently has the most remaining
    estimated hours.

    Simple on purpose — the adaptivity comes from replan() calling
    this again with updated topic data, not from a clever scheduler.
    """
    exam = db.get_exam()

    if not exam:
        return {
            "status": "error",
            "message": "No exam date set yet.",
        }

    topics = db.get_all_topics()

    if not topics:
        return {
            "status": "error",
            "message": "No topics yet — parse a syllabus first.",
        }

    db.clear_plan()

    remaining = {
        topic["id"]: topic["est_hours"]
        for topic in topics
        if not topic["mastered"]
    }

    exam_date = date.fromisoformat(exam["exam_date"])
    daily_hours = exam["daily_hours"]
    current = date.today()

    while (
        current < exam_date
        and any(hours > 0 for hours in remaining.values())
    ):
        hours_left_today = daily_hours

        # Sort each day by most-remaining-hours-first, so weak topics
        # get first claim on today's budget.
        for topic_id, hours in sorted(
            remaining.items(),
            key=lambda item: -item[1],
        ):
            if hours_left_today <= 0:
                break

            if hours <= 0:
                continue

            # Cap a single block at 2 hours to keep it realistic.
            block = min(hours, hours_left_today, 2.0)

            db.insert_plan_row(
                topic_id,
                current.isoformat(),
                block,
            )

            remaining[topic_id] -= block
            hours_left_today -= block

        current += timedelta(days=1)

    return {
        "status": "ok",
        "reasoning": reasoning,
        "days_planned": (current - date.today()).days,
    }


def generate_quiz(
    topic_name: str,
    num_questions: int = 4,
) -> dict:
    topics = {
        topic["name"]: topic
        for topic in db.get_all_topics()
    }

    if topic_name not in topics:
        return {
            "status": "error",
            "message": f"Unknown topic: {topic_name}",
        }

    prompt = f"""Write {num_questions} short quiz questions to test
understanding of "{topic_name}".

Return ONLY valid JSON: a list of objects with keys
"question" and "answer".

No prose, no markdown fences.
"""

    result = chat([
        {
            "role": "user",
            "content": prompt,
        }
    ])

    questions = json.loads(result["content"])

    return {
        "status": "ok",
        "topic_name": topic_name,
        "questions": questions,
    }


def log_result(topic_name: str, quality: int) -> dict:
    topics = {
        topic["name"]: topic
        for topic in db.get_all_topics()
    }

    topic = topics.get(topic_name)

    if not topic:
        return {
            "status": "error",
            "message": f"Unknown topic: {topic_name}",
        }

    db.insert_quiz_result(
        topic["id"],
        quality,
        date.today().isoformat(),
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
    """
    The heart of "adaptive":

    Look at every topic's current mastery state and remaining hours,
    then just call schedule() again.

    Because schedule() always reads live topic data, re-running it
    after SM-2 updates IS the replan — no separate algorithm needed.
    """
    return schedule(reasoning=f"[replan] {reasoning}")


# Dispatch table the agent loop uses to call a tool by the name
# the LLM gave it.
TOOL_FUNCTIONS = {
    "schedule": schedule,
    "generate_quiz": generate_quiz,
    "log_result": log_result,
    "replan": replan,
}