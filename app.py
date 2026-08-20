import streamlit as st
from datetime import date, datetime, time, timedelta
from streamlit_autorefresh import st_autorefresh
from pypdf import PdfReader

from studyloop import db
from studyloop.agent import run_agent_turn
from studyloop.db import init_db
from studyloop.tools import evaluate_quiz, parse_syllabus


# --------------------------------------------------
# Page configuration
# --------------------------------------------------

st.set_page_config(
    page_title="StudyLoop",
    page_icon="📚",
    layout="wide",
)


# --------------------------------------------------
# Database initialization
# --------------------------------------------------

init_db()


# --------------------------------------------------
# Session state defaults
# --------------------------------------------------

if "active_section" not in st.session_state:
    st.session_state["active_section"] = "plan"

if "quiz_topic" not in st.session_state:
    st.session_state["quiz_topic"] = None

if "quiz_plan_id" not in st.session_state:
    st.session_state["quiz_plan_id"] = None

if "current_quiz" not in st.session_state:
    st.session_state["current_quiz"] = None

if "quiz_evaluation" not in st.session_state:
    st.session_state["quiz_evaluation"] = None


# --------------------------------------------------
# Navigation helper
# --------------------------------------------------

def navigate_to(section: str):
    st.session_state["active_section"] = section
    st.rerun()


# --------------------------------------------------
# Page title
# --------------------------------------------------

st.title("StudyLoop — Adaptive Exam-Prep Agent")


# --------------------------------------------------
# CSS Styling
# --------------------------------------------------

st.markdown(
    """
    <style>

    /* --------------------------------------------------
       Global
    -------------------------------------------------- */

    .stApp {
        font-family:
            Inter,
            ui-sans-serif,
            system-ui,
            -apple-system,
            BlinkMacSystemFont,
            "Segoe UI",
            sans-serif;
    }

    h1, h2, h3 {
        letter-spacing: -0.025em;
    }

    /* --------------------------------------------------
       Sidebar
    -------------------------------------------------- */

    section[data-testid="stSidebar"] {
        border-right: 1px solid rgba(128, 128, 128, 0.18);
    }

    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {
        font-weight: 700;
    }

    /* --------------------------------------------------
       Cards
    -------------------------------------------------- */

    .studyloop-card {
        padding: 20px;
        border-radius: 16px;
        border: 1px solid rgba(128, 128, 128, 0.18);
        margin-bottom: 14px;
        background: rgba(128, 128, 128, 0.045);
    }

    .studyloop-card-title {
        font-size: 1.08rem;
        font-weight: 700;
        margin-bottom: 6px;
    }

    .studyloop-meta {
        font-size: 0.88rem;
        opacity: 0.72;
    }

    .studyloop-badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 0.76rem;
        font-weight: 700;
        margin-bottom: 8px;
    }

    .studyloop-hero {
        padding: 26px;
        border-radius: 20px;
        border: 1px solid rgba(128, 128, 128, 0.18);
        background: linear-gradient(
            135deg,
            rgba(70, 120, 180, 0.16),
            rgba(70, 180, 150, 0.08)
        );
        margin-bottom: 24px;
    }

    .studyloop-hero-title {
        font-size: 2rem;
        font-weight: 800;
        margin-bottom: 5px;
    }

    .studyloop-hero-subtitle {
        opacity: 0.72;
        font-size: 1rem;
    }

    /* --------------------------------------------------
       Buttons
    -------------------------------------------------- */

    div.stButton > button {
        border-radius: 10px;
        font-weight: 650;
        min-height: 42px;
        transition: all 0.18s ease;
    }

    div.stButton > button:hover {
        transform: translateY(-1px);
    }

    /* --------------------------------------------------
       Navigation
    -------------------------------------------------- */

    .nav-caption {
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        opacity: 0.55;
        font-weight: 700;
        margin-bottom: 6px;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------
# Auto refresh
# --------------------------------------------------

st_autorefresh(
    interval=30_000,
    key="studyloop_scheduler",
)


# --------------------------------------------------
# Due notifications
# --------------------------------------------------

def show_due_notifications():
    """
    Display in-app notifications for activities whose
    scheduled time has arrived.
    """

    now = datetime.now().isoformat()

    due_activities = db.get_due_activities(now)

    for activity in due_activities:

        activity_type = activity["activity_type"]
        topic = activity["topic_name"]

        if activity_type == "quiz":

            message = (
                f"Quiz due: {topic}. "
                f"You have 15 minutes for this quiz."
            )

        elif activity_type == "revision":

            message = (
                f"Revision time: {topic}. "
                f"Review this topic according to your study plan."
            )

        else:

            message = (
                f"Study session: {topic}. "
                f"Start your scheduled study session."
            )

        st.toast(
            message,
            icon="📚",
        )

        db.mark_notification_sent(
            activity["id"]
        )


show_due_notifications()


# --------------------------------------------------
# Sidebar: Setup
# --------------------------------------------------

with st.sidebar:

    st.markdown("## StudyLoop")

    st.caption(
        "Your adaptive exam-preparation assistant"
    )

    st.divider()

    st.markdown(
        '<div class="nav-caption">EXAM SETUP</div>',
        unsafe_allow_html=True,
    )

    exam_date = st.date_input(
        "Exam date",
        min_value=date.today() + timedelta(days=1),
    )

    uploaded = st.file_uploader(
        "Upload syllabus",
        type=["pdf", "txt"],
        help=(
            "Upload the syllabus for the course you want "
            "StudyLoop to plan."
        ),
    )

    st.divider()

    st.markdown(
        '<div class="nav-caption">YOUR STUDY WINDOWS</div>',
        unsafe_allow_html=True,
    )

    st.caption(
        "Tell StudyLoop when you are available. "
        "The agent will decide what to study inside these windows."
    )

    day_names = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]

    existing_slots = db.get_study_slots()

    existing_by_day = {
        day: []
        for day in range(7)
    }

    for slot in existing_slots:

        existing_by_day[
            slot["weekday"]
        ].append(slot)

    with st.form("study_schedule_form"):

        submitted_slots = []

        for weekday, day_name in enumerate(day_names):

            existing = existing_by_day[weekday]

            default_enabled = bool(existing)

            enabled = st.checkbox(
                day_name,
                value=default_enabled,
                key=f"enabled_{weekday}",
            )

            if enabled:

                default_start = (
                    datetime.strptime(
                        existing[0]["start_time"],
                        "%H:%M",
                    ).time()
                    if existing
                    else time(18, 0)
                )

                default_end = (
                    datetime.strptime(
                        existing[0]["end_time"],
                        "%H:%M",
                    ).time()
                    if existing
                    else time(20, 0)
                )

                col1, col2 = st.columns(2)

                with col1:

                    start = st.time_input(
                        "From",
                        value=default_start,
                        key=f"start_{weekday}",
                    )

                with col2:

                    end = st.time_input(
                        "To",
                        value=default_end,
                        key=f"end_{weekday}",
                    )

                if start >= end:

                    st.error(
                        f"{day_name}: end time must be after start time."
                    )

                else:

                    submitted_slots.append(
                        {
                            "weekday": weekday,
                            "start_time": start.strftime("%H:%M"),
                            "end_time": end.strftime("%H:%M"),
                        }
                    )

        save_slots = st.form_submit_button(
            "Save Study Times",
            use_container_width=True,
        )

        if save_slots:

            if not submitted_slots:

                st.error(
                    "Please select at least one study day."
                )

            else:

                db.save_study_slots(
                    submitted_slots
                )

                st.success(
                    "Your weekly study times were saved."
                )

    st.divider()

    plan_button = st.button(
        "Plan My Exam",
        disabled=not uploaded,
        use_container_width=True,
        type="primary",
        help=(
            "Upload your syllabus and save your study times first. "
            "StudyLoop will create your study, revision, and quiz schedule."
        ),
    )


# --------------------------------------------------
# Build plan
# --------------------------------------------------

if plan_button:

    db.set_exam(
        exam_date.isoformat(),
        0.0,
    )

    if not db.get_study_slots():

        st.error(
            "Please save at least one study time slot first."
        )

    else:

        if uploaded.type == "application/pdf":

            reader = PdfReader(uploaded)

            text = "\n".join(
                page.extract_text() or ""
                for page in reader.pages
            )

        else:

            text = uploaded.read().decode("utf-8")

        with st.spinner(
            "Understanding your syllabus..."
        ):

            result = parse_syllabus(text)

        if result["status"] != "ok":

            st.error(
                result.get(
                    "message",
                    "Syllabus parsing failed.",
                )
            )

        else:

            st.success(
                f"Found {result['topics_added']} topics."
            )

            with st.spinner(
                "Your adaptive study plan is being created..."
            ):

                trace = run_agent_turn(
                    "Build the initial study plan "
                    "using the student's saved weekly "
                    "availability."
                )

            st.session_state["last_trace"] = trace

            plan = db.get_plan()

            if plan:

                st.success(
                    f"Your study plan is ready — "
                    f"{len(plan)} activities scheduled."
                )

                st.session_state["active_section"] = "plan"

                st.rerun()

            else:

                st.error(
                    "The syllabus was parsed, but the planner "
                    "did not create any activities."
                )


# --------------------------------------------------
# Main navigation
# --------------------------------------------------

st.markdown(
    '<div class="nav-caption">WORKSPACE</div>',
    unsafe_allow_html=True,
)

nav1, nav2, nav3 = st.columns(3)

with nav1:

    if st.button(
        "Study Plan",
        use_container_width=True,
    ):

        navigate_to("plan")

with nav2:

    if st.button(
        "Quiz",
        use_container_width=True,
    ):

        navigate_to("quiz")

with nav3:

    if st.button(
        "Agent Trace",
        use_container_width=True,
    ):

        navigate_to("trace")


active_section = st.session_state["active_section"]


# --------------------------------------------------
# Study Plan section
# --------------------------------------------------

if active_section == "plan":

    st.markdown(
        """
        <div class="studyloop-hero">
            <div class="studyloop-hero-title">
                Your Study Plan
            </div>
            <div class="studyloop-hero-subtitle">
                StudyLoop adapts this schedule as your quiz
                performance changes.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    plan = db.get_plan()

    if not plan:

        st.info(
            "Your plan is empty. Upload a syllabus and "
            "choose your study times to begin."
        )

    else:

        current_date = None

        for item in plan:

            activity_date = item["study_date"]

            if activity_date != current_date:

                current_date = activity_date

                formatted_date = datetime.strptime(
                    activity_date,
                    "%Y-%m-%d",
                ).strftime(
                    "%A, %d %B %Y"
                )

                st.markdown(
                    f"### {formatted_date}"
                )

            activity_type = item["activity_type"]

            scheduled_at = item.get(
                "scheduled_at"
            )

            if scheduled_at:

                dt = datetime.fromisoformat(
                    scheduled_at
                )

                time_text = dt.strftime(
                    "%I:%M %p"
                )

            else:

                time_text = "Not scheduled"

            duration = int(
                item["planned_hours"] * 60
            )

            if activity_type == "study":

                badge = "STUDY"

                description = (
                    "Learn and understand this topic."
                )

            elif activity_type == "revision":

                badge = "REVISION"

                description = (
                    "Review this topic using active recall."
                )

            else:

                badge = "QUIZ"

                description = (
                    "Test your understanding in 15 minutes."
                )
            st.markdown(
    f"""
<div class="studyloop-card">
    <div class="studyloop-badge">
        {badge}
    </div>

    <div class="studyloop-card-title">
        {item["topic_name"]}
    </div>

    <div class="studyloop-meta">
        {time_text}
        &nbsp; • &nbsp;
        {duration} minutes
        &nbsp; • &nbsp;
        {description}
    </div>
</div>
""",
    unsafe_allow_html=True,
)

            
            if activity_type == "quiz":

                if st.button(
                    "Take Quiz",
                    key=f"take_quiz_{item['id']}",
                    type="primary",
                ):

                    st.session_state["quiz_topic"] = (
                        item["topic_name"]
                    )

                    st.session_state["quiz_plan_id"] = (
                        item["id"]
                    )

                    st.session_state["current_quiz"] = None

                    st.session_state["quiz_evaluation"] = None

                    st.session_state["active_section"] = "quiz"

                    st.rerun()


# --------------------------------------------------
# Quiz section
# --------------------------------------------------

elif active_section == "quiz":

    st.markdown(
        """
        <div class="studyloop-hero">
            <div class="studyloop-hero-title">
                Quiz Center
            </div>
            <div class="studyloop-hero-subtitle">
                Test yourself according to your adaptive
                study plan.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    topics = db.get_all_topics()

    upcoming_quizzes = db.get_upcoming_quizzes()

    # ----------------------------------------------
    # Scheduled quizzes
    # ----------------------------------------------

    st.subheader("Scheduled Quizzes")

    if not upcoming_quizzes:

        st.info(
            "There are currently no pending quizzes."
        )

    else:

        for quiz_activity in upcoming_quizzes:

            scheduled_at = quiz_activity.get(
                "scheduled_at"
            )

            if scheduled_at:

                dt = datetime.fromisoformat(
                    scheduled_at
                )

                quiz_time = dt.strftime(
                    "%A, %d %B • %I:%M %p"
                )

            else:

                quiz_time = quiz_activity[
                    "study_date"
                ]

            with st.container(border=True):

                col1, col2 = st.columns(
                    [4, 1]
                )

                with col1:

                    st.markdown(
                        f"### {quiz_activity['topic_name']}"
                    )

                    st.caption(
                        f"Scheduled for {quiz_time} "
                        "• 15 minutes"
                    )

                with col2:

                    if st.button(
                        "Start Quiz",
                        key=(
                            f"start_"
                            f"{quiz_activity['id']}"
                        ),
                        type="primary",
                    ):

                        st.session_state["quiz_topic"] = (
                            quiz_activity["topic_name"]
                        )

                        st.session_state["quiz_plan_id"] = (
                            quiz_activity["id"]
                        )

                        st.session_state["current_quiz"] = None

                        st.session_state["quiz_evaluation"] = None

                        st.rerun()

    st.divider()

    # ----------------------------------------------
    # Quiz generation
    # ----------------------------------------------

    if (
        st.session_state.get("quiz_topic")
        and not st.session_state.get("current_quiz")
        and not st.session_state.get("quiz_evaluation")
    ):

        quiz_topic = st.session_state["quiz_topic"]

        st.subheader(
            f"Ready: {quiz_topic}"
        )

        if st.button(
            "Generate Quiz",
            type="primary",
            use_container_width=True,
        ):

            with st.spinner(
                "StudyLoop is preparing your quiz..."
            ):

                trace = run_agent_turn(
                    f"""
                    Generate the scheduled 15-minute quiz
                    for the topic "{quiz_topic}".
                    """
                )

            st.session_state["quiz_trace"] = trace

            for step in trace:

                if (
                    step["type"] == "tool_call"
                    and step["tool"] == "generate_quiz"
                ):

                    observation = step["observation"]

                    if observation["status"] == "ok":

                        st.session_state["current_quiz"] = (
                            observation["questions"]
                        )

            st.rerun()

    # ----------------------------------------------
    # Display generated quiz
    # ----------------------------------------------

    if st.session_state.get("current_quiz"):

        quiz = st.session_state["current_quiz"]

        quiz_topic = st.session_state["quiz_topic"]

        st.divider()

        st.subheader(
            f"Quiz: {quiz_topic}"
        )

        st.caption(
            "Answer all questions, then submit your quiz."
        )

        student_answers = {}

        for i, question in enumerate(
            quiz,
            start=1,
        ):

            st.markdown(
                f"### Question {i}"
            )

            st.write(
                question["question"]
            )

            options = question["options"]

            if isinstance(options, dict):

                option_keys = list(
                    options.keys()
                )

                selected = st.radio(
                    "Choose your answer:",
                    options=option_keys,
                    format_func=lambda option,
                    q=question: (
                        f"{option}. "
                        f"{q['options'][option]}"
                    ),
                    key=f"question_{i}",
                )

            else:

                selected = st.radio(
                    "Choose your answer:",
                    options=options,
                    key=f"question_{i}",
                )

            student_answers[str(i)] = selected

            st.divider()

        # ------------------------------------------
        # Submit quiz
        # ------------------------------------------

        if st.button(
            "Submit Quiz",
            type="primary",
            use_container_width=True,
        ):

            with st.spinner(
                "Agent is evaluating your answers..."
            ):

                evaluation = evaluate_quiz(
                    topic_name=quiz_topic,
                    questions=quiz,
                    student_answers=student_answers,
                )

            if evaluation["status"] == "ok":

                st.session_state["quiz_evaluation"] = (
                    evaluation
                )

                # ----------------------------------
                # Find topic in database
                # ----------------------------------

                topic = next(
                    (
                        t
                        for t in topics
                        if t["name"] == quiz_topic
                    ),
                    None,
                )

                # ----------------------------------
                # Save actual quiz result
                # ----------------------------------

                if topic:

                    db.update_latest_quiz_result(
                        topic_id=topic["id"],
                        correct=evaluation["correct"],
                        total=evaluation["total"],
                        percentage=evaluation["percentage"],
                        evaluation=evaluation.get(
                            "evaluation",
                            "",
                        ),
                    )

                # ----------------------------------
                # Mark scheduled quiz completed
                # ----------------------------------

                quiz_plan_id = st.session_state.get(
                    "quiz_plan_id"
                )

                if quiz_plan_id:

                    db.mark_plan_completed(
                        quiz_plan_id
                    )

                # ----------------------------------
                # Replan based on quiz performance
                # ----------------------------------

                quality = evaluation["quality"]

                with st.spinner(
                    "StudyLoop is updating your study plan..."
                ):

                    trace = run_agent_turn(
                        f"""
                        The student completed a quiz for
                        "{quiz_topic}".

                        Quiz quality: {quality}/5.

                        Update the learning state and
                        rebuild the remaining study,
                        revision, and quiz schedule.
                        """
                    )

                st.session_state["last_trace"] = trace

                # ----------------------------------
                # Show result
                # ----------------------------------

                correct = evaluation["correct"]
                total = evaluation["total"]
                percentage = evaluation["percentage"]

                st.success(
                    f"Quiz completed: {correct}/{total} "
                    f"correct ({percentage}%). "
                    "Your study plan has been updated."
                )

                # ----------------------------------
                # Clear current quiz
                # ----------------------------------

                st.session_state["current_quiz"] = None
                st.session_state["quiz_topic"] = None
                st.session_state["quiz_plan_id"] = None

                st.session_state["active_section"] = "plan"

                st.rerun()

            else:

                st.error(
                    evaluation.get(
                        "message",
                        "Quiz evaluation failed.",
                    )
                )

    # ----------------------------------------------
    # Previous results
    # ----------------------------------------------

    st.divider()

    st.subheader(
        "Previous Quiz Results"
    )

    if not topics:

        st.info(
            "Your quiz history will appear here "
            "after you complete your first quiz."
        )

    else:

        for topic in topics:

            history = db.get_quiz_history(
                topic["id"]
            )

            latest = (
                history[0]
                if history
                else None
            )

            if latest:

                score = (
                    f"{latest['correct']}/"
                    f"{latest['total']}"
                    if latest["correct"] is not None
                    and latest["total"] is not None
                    else f"SM-2 {latest['quality']}/5"
                )

                percentage = (
                    f"{latest['percentage']}%"
                    if latest["percentage"] is not None
                    else "Score unavailable"
                )

                help_text = (
                    f"Latest result: {score} "
                    f"({percentage}). "
                    f"SM-2 quality: "
                    f"{latest['quality']}/5."
                )

            else:

                help_text = (
                    "No quiz has been completed "
                    "for this topic yet."
                )

            col1, col2 = st.columns(
                [4, 1]
            )

            with col1:

                st.markdown(
                    f"**{topic['name']}**"
                )

                if latest:

                    st.caption(
                        f"Latest: {score} • "
                        f"{percentage}"
                    )

                else:

                    st.caption(
                        "No quiz attempts yet"
                    )

            with col2:

                if st.button(
                    "Show quiz results",
                    key=(
                        f"results_"
                        f"{topic['id']}"
                    ),
                    help=help_text,
                ):

                    st.session_state[
                        f"show_results_{topic['id']}"
                    ] = not st.session_state.get(
                        f"show_results_{topic['id']}",
                        False,
                    )

            if st.session_state.get(
                f"show_results_{topic['id']}",
                False,
            ):

                if not history:

                    st.info(
                        "No quiz results yet."
                    )

                else:

                    for result in history:

                        result_date = result[
                            "taken_at"
                        ]

                        if (
                            result["percentage"]
                            is not None
                        ):

                            result_text = (
                                f"{result['correct']}/"
                                f"{result['total']} "
                                f"({result['percentage']}%)"
                            )

                        else:

                            result_text = (
                                f"SM-2 "
                                f"{result['quality']}/5"
                            )
                        st.markdown(
    f"""
<div class="studyloop-card">
    <strong>
        {result_text}
    </strong>

    <div class="studyloop-meta">
        {result_date}
        &nbsp; • &nbsp;
        SM-2 quality:
        {result["quality"]}/5
    </div>
</div>
""",
    unsafe_allow_html=True,
)
                        

# --------------------------------------------------
# Agent Trace section
# --------------------------------------------------

elif active_section == "trace":

    st.markdown(
        """
        <div class="studyloop-hero">
            <div class="studyloop-hero-title">
                Agent Trace
            </div>
            <div class="studyloop-hero-subtitle">
                See the actions taken by StudyLoop.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    trace = st.session_state.get(
        "last_trace"
    )

    if not trace:

        st.info(
            "No agent activity has been recorded yet."
        )

    else:

        for index, step in enumerate(
            trace,
            start=1,
        ):

            with st.expander(
                f"Step {index}: {step.get('type', 'Unknown')}",
                expanded=False,
            ):

                st.json(step)