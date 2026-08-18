import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent.parent / "data" / "studyloop.db"


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                difficulty INTEGER NOT NULL, -- 1 (easy) to 5 (hard), set by the LLM
                est_hours REAL NOT NULL, -- initial time estimate
                repetitions INTEGER DEFAULT 0, -- SM-2 state
                ease_factor REAL DEFAULT 2.5, -- SM-2 state
                interval_days INTEGER DEFAULT 1, -- SM-2 state
                next_review_date TEXT, -- ISO date string
                mastered INTEGER DEFAULT 0 -- 0/1
            );

            CREATE TABLE IF NOT EXISTS plan (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER NOT NULL,
                study_date TEXT NOT NULL, -- ISO date string
                planned_hours REAL NOT NULL,
                completed INTEGER DEFAULT 0,
                FOREIGN KEY (topic_id) REFERENCES topics(id)
            );

            CREATE TABLE IF NOT EXISTS quiz_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER NOT NULL,
                quality INTEGER NOT NULL, -- 0-5 SM-2 quality score
                taken_at TEXT NOT NULL,
                FOREIGN KEY (topic_id) REFERENCES topics(id)
            );

            CREATE TABLE IF NOT EXISTS exam (
                id INTEGER PRIMARY KEY CHECK (id = 1), -- singleton row
                exam_date TEXT NOT NULL,
                daily_hours REAL NOT NULL
            );
        """)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Lets us access columns by name, e.g. row["name"]
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# --- Small helper functions the tools will call ----------------------


def insert_topic(name: str, difficulty: int, est_hours: float) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO topics (name, difficulty, est_hours) VALUES (?, ?, ?)",
            (name, difficulty, est_hours),
        )
        return cur.lastrowid


def get_all_topics() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM topics").fetchall()
        return [dict(r) for r in rows]


def set_exam(exam_date: str, daily_hours: float):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO exam (id, exam_date, daily_hours) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET exam_date=excluded.exam_date, "
            "daily_hours=excluded.daily_hours",
            (exam_date, daily_hours),
        )


def get_exam() -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM exam WHERE id = 1"
        ).fetchone()
        return dict(row) if row else None


def clear_plan():
    with get_conn() as conn:
        conn.execute("DELETE FROM plan")


def insert_plan_row(
    topic_id: int,
    study_date: str,
    planned_hours: float,
):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO plan (topic_id, study_date, planned_hours) "
            "VALUES (?, ?, ?)",
            (topic_id, study_date, planned_hours),
        )


def get_plan() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT
                plan.*,
                topics.name AS topic_name
            FROM plan
            JOIN topics ON plan.topic_id = topics.id
            ORDER BY study_date
        """).fetchall()

        return [dict(r) for r in rows]


def insert_quiz_result(
    topic_id: int,
    quality: int,
    taken_at: str,
):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO quiz_results (topic_id, quality, taken_at) "
            "VALUES (?, ?, ?)",
            (topic_id, quality, taken_at),
        )


def update_topic_sm2(
    topic_id: int,
    repetitions: int,
    ease_factor: float,
    interval_days: int,
    next_review_date: str,
    mastered: int,
):
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE topics
            SET
                repetitions=?,
                ease_factor=?,
                interval_days=?,
                next_review_date=?,
                mastered=?
            WHERE id=?
            """,
            (
                repetitions,
                ease_factor,
                interval_days,
                next_review_date,
                mastered,
                topic_id,
            ),
        )


def get_quiz_history(topic_id: int | None = None) -> list[dict]:
    with get_conn() as conn:
        if topic_id:
            rows = conn.execute(
                "SELECT * FROM quiz_results "
                "WHERE topic_id=? "
                "ORDER BY taken_at",
                (topic_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM quiz_results "
                "ORDER BY taken_at"
            ).fetchall()

        return [dict(r) for r in rows]