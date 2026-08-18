from datetime import date, timedelta


def sm2_update(
    quality: int,
    repetitions: int,
    ease_factor: float,
    interval_days: int,
) -> dict:
    """
    quality: 0-5 score from the quiz just taken
             (0 = total blackout, 5 = perfect)

    repetitions, ease_factor, interval_days:
        This topic's CURRENT state.

    Returns the topic's NEW state after this quiz.
    """

    if quality < 0 or quality > 5:
        raise ValueError("quality must be between 0 and 5")

    if quality < 3:
        # Failed recall — start the repetition count over,
        # review again tomorrow.
        repetitions = 0
        interval_days = 1

    else:
        repetitions += 1

        if repetitions == 1:
            interval_days = 1

        elif repetitions == 2:
            interval_days = 6

        else:
            interval_days = round(interval_days * ease_factor)

    ease_factor = ease_factor + (
        0.1
        - (5 - quality) * (0.08 + (5 - quality) * 0.02)
    )

    # SM-2's documented floor
    ease_factor = max(1.3, ease_factor)

    next_review_date = (
        date.today() + timedelta(days=interval_days)
    ).isoformat()

    # A topic counts as "mastered" once it has been
    # recalled well 3 times running AND the gap before
    # it needs review again has stretched past two weeks.
    mastered = (
        1
        if (repetitions >= 3 and interval_days >= 14)
        else 0
    )

    return {
        "repetitions": repetitions,
        "ease_factor": round(ease_factor, 2),
        "interval_days": interval_days,
        "next_review_date": next_review_date,
        "mastered": mastered,
    }