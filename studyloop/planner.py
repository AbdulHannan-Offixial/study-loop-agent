from datetime import date, datetime, timedelta, time

from studyloop import db


QUIZ_MINUTES = 15
MAX_STUDY_BLOCK_MINUTES = 60
MIN_STUDY_BLOCK_MINUTES = 30


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


def _next_available_time(
    current_time: time,
    minutes: int,
) -> time:
    base = datetime.combine(date.today(), current_time)
    result = base + timedelta(minutes=minutes)
    return result.time()


def build_plan(reasoning: str) -> dict:
    """
    Build a concrete study/revision/quiz schedule.

    The planner uses deterministic rules:
    - New topics receive first-pass study time.
    - Each first-pass study block receives a 15-minute quiz.
    - Topics with an SM-2 review date receive revision time.
    - A quiz is placed after a revision session.
    - Mastered topics are not given normal study time.
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

    exam_date = date.fromisoformat(exam["exam_date"])
    daily_hours = float(exam["daily_hours"])

    if exam_date <= date.today():
        return {
            "status": "error",
            "message": "Exam date must be in the future.",
        }

    daily_minutes = int(daily_hours * 60)

    # Reserve 15 minutes for a quiz whenever we create a
    # study/revision session.
    usable_minutes = max(
        30,
        daily_minutes - QUIZ_MINUTES,
    )

    db.clear_future_plan()

    today = date.today()

    # ------------------------------------------------------------
    # 1. Determine topics needing first-pass study.
    # ------------------------------------------------------------

    new_topics = [
        topic
        for topic in topics
        if topic["repetitions"] == 0
        and not topic["mastered"]
    ]

    # Harder topics first.
    new_topics.sort(
        key=lambda topic: (
            -topic["difficulty"],
            -topic["est_hours"],
        )
    )

    # Remaining first-pass hours.
    remaining = {
        topic["id"]: float(topic["est_hours"])
        for topic in new_topics
    }

    # ------------------------------------------------------------
    # 2. Determine revision topics from SM-2.
    # ------------------------------------------------------------

    revision_topics = {}

    for topic in topics:
        next_review = topic.get("next_review_date")

        if (
            next_review
            and not topic["mastered"]
        ):
            try:
                review_date = date.fromisoformat(next_review)
            except ValueError:
                continue

            if today <= review_date < exam_date:
                revision_topics.setdefault(
                    review_date,
                    [],
                ).append(topic)

    # ------------------------------------------------------------
    # 3. Build day-by-day schedule.
    # ------------------------------------------------------------

    current_day = today

    total_study_activities = 0
    total_revision_activities = 0
    total_quizzes = 0

    while current_day < exam_date:

        minutes_left = daily_minutes

        # Start each day at 6:00 PM.
        # You can later make this a user setting.
        current_time = time(18, 0)

        # --------------------------------------------------------
        # Revision due today
        # --------------------------------------------------------

        due_revisions = revision_topics.get(
            current_day,
            [],
        )

        for topic in due_revisions:

            if minutes_left < 45:
                break

            revision_minutes = min(
                45,
                minutes_left - QUIZ_MINUTES,
            )

            if revision_minutes < 30:
                break

            _add_activity(
                topic_id=topic["id"],
                activity_type="revision",
                activity_date=current_day,
                start_time=current_time,
                duration_minutes=revision_minutes,
            )

            total_revision_activities += 1

            current_time = _next_available_time(
                current_time,
                revision_minutes,
            )

            minutes_left -= revision_minutes

            # Quiz immediately after revision.
            if minutes_left >= QUIZ_MINUTES:
                _add_activity(
                    topic_id=topic["id"],
                    activity_type="quiz",
                    activity_date=current_day,
                    start_time=current_time,
                    duration_minutes=QUIZ_MINUTES,
                )

                total_quizzes += 1

                current_time = _next_available_time(
                    current_time,
                    QUIZ_MINUTES,
                )

                minutes_left -= QUIZ_MINUTES

        # --------------------------------------------------------
        # First-pass learning
        # --------------------------------------------------------

        for topic in new_topics:

            if minutes_left < (
                MIN_STUDY_BLOCK_MINUTES
                + QUIZ_MINUTES
            ):
                break

            remaining_hours = remaining[topic["id"]]

            if remaining_hours <= 0:
                continue

            available_study_minutes = min(
                MAX_STUDY_BLOCK_MINUTES,
                int(remaining_hours * 60),
                minutes_left - QUIZ_MINUTES,
            )

            if available_study_minutes < MIN_STUDY_BLOCK_MINUTES:
                continue

            _add_activity(
                topic_id=topic["id"],
                activity_type="study",
                activity_date=current_day,
                start_time=current_time,
                duration_minutes=available_study_minutes,
            )

            total_study_activities += 1

            remaining[topic["id"]] -= (
                available_study_minutes / 60
            )

            current_time = _next_available_time(
                current_time,
                available_study_minutes,
            )

            minutes_left -= available_study_minutes

            # Quiz after study.
            if minutes_left >= QUIZ_MINUTES:
                _add_activity(
                    topic_id=topic["id"],
                    activity_type="quiz",
                    activity_date=current_day,
                    start_time=current_time,
                    duration_minutes=QUIZ_MINUTES,
                )

                total_quizzes += 1

                current_time = _next_available_time(
                    current_time,
                    QUIZ_MINUTES,
                )

                minutes_left -= QUIZ_MINUTES

        current_day += timedelta(days=1)

        # Stop once all first-pass topics are completed.
        if not any(
            hours > 0
            for hours in remaining.values()
        ):
            # We still continue through the calendar because
            # future SM-2 revisions may exist.
            if not any(
                day >= current_day
                for day in revision_topics
            ):
                break

    return {
        "status": "ok",
        "reasoning": reasoning,
        "study_activities": total_study_activities,
        "revision_activities": total_revision_activities,
        "quizzes": total_quizzes,
    }