from datetime import date, datetime, timedelta, time

from studyloop import db


QUIZ_MINUTES = 15
MAX_STUDY_BLOCK_MINUTES = 60
MIN_STUDY_BLOCK_MINUTES = 30
REVISION_MINUTES = 45


def _time_from_string(value: str) -> time:
    return datetime.strptime(
        value,
        "%H:%M",
    ).time()


def _minutes_between(
    start: time,
    end: time,
) -> int:

    start_dt = datetime.combine(
        date.today(),
        start,
    )

    end_dt = datetime.combine(
        date.today(),
        end,
    )

    return int(
        (end_dt - start_dt).total_seconds() / 60
    )


def _add_activity(
    topic_id: int,
    activity_type: str,
    activity_date: date,
    start_time: time,
    duration_minutes: int,
):
    scheduled_at = datetime.combine(
        activity_date,
        start_time,
    ).isoformat()

    db.insert_plan_row(
        topic_id=topic_id,
        study_date=activity_date.isoformat(),
        planned_hours=duration_minutes / 60,
        activity_type=activity_type,
        scheduled_at=scheduled_at,
    )


def _next_time(
    current: time,
    minutes: int,
) -> time:

    base = datetime.combine(
        date.today(),
        current,
    )

    return (
        base + timedelta(minutes=minutes)
    ).time()


def build_plan(reasoning: str) -> dict:
    """
    Build the study plan using the student's actual
    weekly availability.

    The agent decides WHAT should be studied.
    This planner decides WHEN it fits into the
    student's available time.
    """

    exam = db.get_exam()

    if not exam:
        return {
            "status": "error",
            "message": "No exam date has been configured.",
        }

    topics = db.get_all_topics()

    if not topics:
        return {
            "status": "error",
            "message": "No topics found. Parse a syllabus first.",
        }

    slots_by_day = db.get_study_slots_by_weekday()

    if not any(slots_by_day.values()):
        return {
            "status": "error",
            "message": (
                "No study time slots have been configured. "
                "Set your weekly study availability first."
            ),
        }

    exam_date = date.fromisoformat(
        exam["exam_date"]
    )

    today = date.today()

    if exam_date <= today:
        return {
            "status": "error",
            "message": (
                "Exam date must be after today."
            ),
        }

    # ---------------------------------------------------------
    # Remove only pending activities.
    # Completed activities remain as history.
    # ---------------------------------------------------------

    db.clear_future_plan()

    # ---------------------------------------------------------
    # New topics
    # ---------------------------------------------------------

    new_topics = [
        topic
        for topic in topics
        if topic["repetitions"] == 0
        and not topic["mastered"]
    ]

    new_topics.sort(
        key=lambda topic: (
            -topic["difficulty"],
            -topic["est_hours"],
        )
    )

    remaining_hours = {
        topic["id"]: float(topic["est_hours"])
        for topic in new_topics
    }

    # ---------------------------------------------------------
    # SM-2 revision queue
    # ---------------------------------------------------------

    revision_queue = []

    for topic in topics:

        next_review = topic.get(
            "next_review_date"
        )

        if (
            next_review
            and not topic["mastered"]
        ):
            try:
                review_date = date.fromisoformat(
                    next_review
                )
            except ValueError:
                continue

            if review_date < exam_date:
                revision_queue.append(
                    {
                        "topic": topic,
                        "eligible_date": review_date,
                    }
                )

    revision_queue.sort(
        key=lambda item: item["eligible_date"]
    )

    new_topic_index = 0

    total_study = 0
    total_revision = 0
    total_quizzes = 0

    current_day = today

    while current_day < exam_date:

        weekday = current_day.weekday()

        raw_slots = slots_by_day.get(
            weekday,
            [],
        )

        # Convert DB slots into mutable cursors.
        slots = []

        for slot in raw_slots:

            start = _time_from_string(
                slot["start_time"]
            )

            end = _time_from_string(
                slot["end_time"]
            )

            if start >= end:
                continue

            slots.append(
                {
                    "start": start,
                    "end": end,
                    "cursor": start,
                }
            )

        # -----------------------------------------------------
        # Process every availability window for this day.
        # -----------------------------------------------------

        for slot in slots:

            cursor = slot["cursor"]

            while cursor < slot["end"]:

                available = _minutes_between(
                    cursor,
                    slot["end"],
                )

                # Need at least:
                # 30 min study + 15 min quiz
                if available < (
                    MIN_STUDY_BLOCK_MINUTES
                    + QUIZ_MINUTES
                ):
                    break

                # -------------------------------------------------
                # 1. Revision gets priority when due.
                # -------------------------------------------------

                due_revision = None

                for item in revision_queue:

                    if (
                        item["eligible_date"]
                        <= current_day
                    ):
                        due_revision = item
                        break

                if due_revision:

                    topic = due_revision["topic"]

                    revision_minutes = min(
                        REVISION_MINUTES,
                        available - QUIZ_MINUTES,
                    )

                    if revision_minutes >= 30:

                        _add_activity(
                            topic_id=topic["id"],
                            activity_type="revision",
                            activity_date=current_day,
                            start_time=cursor,
                            duration_minutes=revision_minutes,
                        )

                        total_revision += 1

                        cursor = _next_time(
                            cursor,
                            revision_minutes,
                        )

                        available = _minutes_between(
                            cursor,
                            slot["end"],
                        )

                        if available >= QUIZ_MINUTES:

                            _add_activity(
                                topic_id=topic["id"],
                                activity_type="quiz",
                                activity_date=current_day,
                                start_time=cursor,
                                duration_minutes=QUIZ_MINUTES,
                            )

                            total_quizzes += 1

                            cursor = _next_time(
                                cursor,
                                QUIZ_MINUTES,
                            )

                        revision_queue.remove(
                            due_revision
                        )

                        continue

                # -------------------------------------------------
                # 2. First-pass study.
                # -------------------------------------------------

                while (
                    new_topic_index
                    < len(new_topics)
                ):

                    topic = new_topics[
                        new_topic_index
                    ]

                    remaining = int(
                        remaining_hours[
                            topic["id"]
                        ] * 60
                    )

                    if remaining <= 0:
                        new_topic_index += 1
                        continue

                    study_minutes = min(
                        MAX_STUDY_BLOCK_MINUTES,
                        remaining,
                        available - QUIZ_MINUTES,
                    )

                    if study_minutes < 30:
                        break

                    _add_activity(
                        topic_id=topic["id"],
                        activity_type="study",
                        activity_date=current_day,
                        start_time=cursor,
                        duration_minutes=study_minutes,
                    )

                    total_study += 1

                    remaining_hours[
                        topic["id"]
                    ] -= study_minutes / 60

                    cursor = _next_time(
                        cursor,
                        study_minutes,
                    )

                    available = _minutes_between(
                        cursor,
                        slot["end"],
                    )

                    # Quiz immediately after study.
                    if available >= QUIZ_MINUTES:

                        _add_activity(
                            topic_id=topic["id"],
                            activity_type="quiz",
                            activity_date=current_day,
                            start_time=cursor,
                            duration_minutes=QUIZ_MINUTES,
                        )

                        total_quizzes += 1

                        cursor = _next_time(
                            cursor,
                            QUIZ_MINUTES,
                        )

                    if (
                        remaining_hours[
                            topic["id"]
                        ] <= 0
                    ):
                        new_topic_index += 1

                    break

                slot["cursor"] = cursor

        current_day += timedelta(days=1)

    return {
        "status": "ok",
        "reasoning": reasoning,
        "study_activities": total_study,
        "revision_activities": total_revision,
        "quizzes": total_quizzes,
    }