import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent.parent / "data" / "studyloop.db"


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                difficulty INTEGER NOT NULL,
                est_hours REAL NOT NULL,
                repetitions INTEGER DEFAULT 0,
                ease_factor REAL DEFAULT 2.5,
                interval_days INTEGER DEFAULT 1,
                next_review_date TEXT,
                mastered INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS plan (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER NOT NULL,
                study_date TEXT NOT NULL,
                planned_hours REAL NOT NULL,
                activity_type TEXT DEFAULT 'study',
                scheduled_at TEXT,
                completed INTEGER DEFAULT 0,
                notification_sent INTEGER DEFAULT 0,
                FOREIGN KEY (topic_id) REFERENCES topics(id)
            );

            CREATE TABLE IF NOT EXISTS quiz_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER NOT NULL,
                quality INTEGER NOT NULL,
                taken_at TEXT NOT NULL,
                FOREIGN KEY (topic_id) REFERENCES topics(id)
            );

            CREATE TABLE IF NOT EXISTS exam (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                exam_date TEXT NOT NULL,
                daily_hours REAL NOT NULL
            );
        """)

        # ------------------------------------------------------------
        # Database migration for existing installations.
        # ------------------------------------------------------------

        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(plan)"
            ).fetchall()
        }

        if "activity_type" not in columns:
            conn.execute(
                """
                ALTER TABLE plan
                ADD COLUMN activity_type TEXT DEFAULT 'study'
                """
            )

        if "scheduled_at" not in columns:
            conn.execute(
                """
                ALTER TABLE plan
                ADD COLUMN scheduled_at TEXT
                """
            )

        if "notification_sent" not in columns:
            conn.execute(
                """
                ALTER TABLE plan
                ADD COLUMN notification_sent INTEGER DEFAULT 0
                """
            )


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


def clear_future_plan():
    """
    Remove future activities so the agent can rebuild
    the schedule after a quiz result.

    Historical completed activities are preserved.
    """
    with get_conn() as conn:
        conn.execute(
            """
            DELETE FROM plan
            WHERE completed = 0
            """
        )

def insert_plan_row(
    topic_id: int,
    study_date: str,
    planned_hours: float,
    activity_type: str = "study",
    scheduled_at: str | None = None,
):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO plan (
                topic_id,
                study_date,
                planned_hours,
                activity_type,
                scheduled_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                topic_id,
                study_date,
                planned_hours,
                activity_type,
                scheduled_at,
            ),
        )


def get_plan() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                plan.*,
                topics.name AS topic_name,
                topics.difficulty,
                topics.mastered,
                topics.next_review_date
            FROM plan
            JOIN topics
                ON plan.topic_id = topics.id
            ORDER BY
                plan.study_date,
                plan.scheduled_at
            """
        ).fetchall()

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

def get_due_activities(now_iso: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                plan.*,
                topics.name AS topic_name
            FROM plan
            JOIN topics
                ON plan.topic_id = topics.id
            WHERE
                plan.scheduled_at <= ?
                AND plan.completed = 0
                AND plan.notification_sent = 0
            ORDER BY plan.scheduled_at
            """,
            (now_iso,),
        ).fetchall()

        return [dict(r) for r in rows]


def mark_notification_sent(plan_id: int):
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE plan
            SET notification_sent = 1
            WHERE id = ?
            """,
            (plan_id,),
        )


def mark_plan_completed(plan_id: int):
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE plan
            SET completed = 1
            WHERE id = ?
            """,
            (plan_id,),
        )

def clear_topics():
    with get_conn() as conn:
        conn.execute("DELETE FROM quiz_results")
        conn.execute("DELETE FROM plan")
        conn.execute("DELETE FROM topics")