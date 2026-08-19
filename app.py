import streamlit as st
from datetime import date, datetime
from streamlit_autorefresh import st_autorefresh
from pypdf import PdfReader

from studyloop import db
from studyloop.agent import run_agent_turn
from studyloop.db import init_db
from studyloop.tools import evaluate_quiz, parse_syllabus

st.set_page_config(
    page_title="StudyLoop",
    page_icon="📚",
    layout="wide",
)

st.title("StudyLoop — Adaptive Exam-Prep Agent")

init_db()
# Check the schedule every 30 seconds.

st_autorefresh(
    interval=30_000,
    key="studyloop_scheduler",
)

def show_due_notifications():
    """
    Display in-app notifications for activities whose scheduled
    time has arrived.
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




# --------------------------------------------------------------------
# Sidebar: Setup
# --------------------------------------------------------------------

with st.sidebar:
    st.header("1. Setup")

    exam_date = st.date_input(
        "Exam date",
        min_value=date.today(),
    )

    daily_hours = st.number_input(
        "Hours available per day",
        min_value=0.5,
        max_value=12.0,
        value=2.0,
        step=0.5,
    )

    uploaded = st.file_uploader(
        "Upload syllabus",
        type=["pdf", "txt"],
    )

    if st.button(
        "Parse syllabus & build initial plan",
        disabled=not uploaded,
    ):
        db.set_exam(
            exam_date.isoformat(),
            daily_hours,
        )

        if uploaded.type == "application/pdf":
            reader = PdfReader(uploaded)

            text = "\n".join(
                page.extract_text() or ""
                for page in reader.pages
            )
        else:
            text = uploaded.read().decode("utf-8")

        with st.spinner("Parsing syllabus..."):
            result = parse_syllabus(text)

        st.success(
            f"Added {result['topics_added']} topics."
        )

        with st.spinner("Agent is building your plan..."):
            trace = run_agent_turn(
                "Build the initial study plan for me."
            )

        st.session_state["last_trace"] = trace


# --------------------------------------------------------------------
# Main interface
# --------------------------------------------------------------------

tab_plan, tab_quiz, tab_trace = st.tabs(
    ["Plan", "Quiz", "Agent trace"]
)


# --------------------------------------------------------------------
# Plan tab
# --------------------------------------------------------------------

with tab_plan:

    st.subheader("Study Plan")

    plan = db.get_plan()

    if not plan:

        st.info(
            "Upload a syllabus and build a plan from the sidebar."
        )

    else:

        for item in plan:

            activity_type = item["activity_type"]

            if activity_type == "study":
                label = "Study"

            elif activity_type == "revision":
                label = "Revision"

            elif activity_type == "quiz":
                label = "Quiz"

            else:
                label = activity_type.title()

            scheduled_at = item.get("scheduled_at")

            if scheduled_at:
                try:
                    dt = datetime.fromisoformat(
                        scheduled_at
                    )
                    time_text = dt.strftime(
                        "%I:%M %p"
                    )
                except ValueError:
                    time_text = "Unknown time"
            else:
                time_text = "No time"

            duration = int(
                item["planned_hours"] * 60
            )

            status = (
                "Completed"
                if item["completed"]
                else "Pending"
            )

            with st.container(border=True):

                st.markdown(
                    f"### {label}: {item['topic_name']}"
                )

                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.write(
                        f"**Date:** {item['study_date']}"
                    )

                with col2:
                    st.write(
                        f"**Time:** {time_text}"
                    )

                with col3:
                    st.write(
                        f"**Duration:** {duration} min"
                    )

                with col4:
                    st.write(
                        f"**Status:** {status}"
                    )


# --------------------------------------------------------------------
# Quiz tab
# --------------------------------------------------------------------

with tab_quiz:
    topics = db.get_all_topics()

    if not topics:
        st.info("No topics yet.")

    else:
        names = [topic["name"] for topic in topics]

        chosen = st.selectbox(
            "Topic just studied",
            names,
        )

        if st.button("Generate quiz"):
            with st.spinner("Agent is writing a quiz..."):
                trace = run_agent_turn(
                    f"Generate a quiz for the topic '{chosen}'."
                )

            st.session_state["quiz_trace"] = trace

            # Extract quiz from the agent trace.
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
                        st.session_state["quiz_topic"] = chosen

        if "current_quiz" in st.session_state:
            st.subheader("Quiz")

            quiz = st.session_state["current_quiz"]

            # Store student's answers separately.
            student_answers = {}

            for i, question in enumerate(quiz, start=1):
                st.write(
                    f"**Q{i}. {question['question']}**"
                )

                selected = st.radio(
                    "Choose your answer:",
                    options=["A", "B", "C", "D"],
                    format_func=lambda option, q=question: (
                        f"{option}. {q['options'][option]}"
                    ),
                    key=f"question_{i}",
                )

                student_answers[str(i)] = selected

                st.divider()

            if st.button("Submit Quiz"):
                with st.spinner(
                    "Agent is evaluating your answers..."
                ):
                    evaluation = evaluate_quiz(
                        topic_name=st.session_state["quiz_topic"],
                        questions=quiz,
                        student_answers=student_answers,
                    )

                if evaluation["status"] == "ok":
                    st.session_state["quiz_evaluation"] = evaluation

                    quality = evaluation["quality"]

                    with st.spinner(
                        "Agent is updating your study plan..."
                    ):
                        trace = run_agent_turn(
                            f"""
The quiz for topic
'{st.session_state["quiz_topic"]}'
has been evaluated.

The objective quiz result is:
{evaluation["correct"]}/{evaluation["total"]}
({evaluation["percentage"]}%)

The agent evaluation assigned SM-2 quality:
{quality}/5

Log this result and then replan the study schedule.
"""
                        )

                    st.session_state["last_trace"] = trace

                    st.success(
                        "Quiz evaluated and study plan updated."
                    )

                else:
                    st.error(
                        evaluation.get(
                            "message",
                            "Quiz evaluation failed.",
                        )
                    )

            # Display evaluation AFTER submission.
            if "quiz_evaluation" in st.session_state:
                evaluation = st.session_state["quiz_evaluation"]

                st.subheader("Evaluation")

                st.metric(
                    "Score",
                    f"{evaluation['correct']}/{evaluation['total']}",
                )

                st.metric(
                    "Percentage",
                    f"{evaluation['percentage']}%",
                )

                st.metric(
                    "SM-2 Quality",
                    f"{evaluation['quality']}/5",
                )

                st.write(
                    f"**Agent evaluation:** "
                    f"{evaluation['evaluation']}"
                )


# --------------------------------------------------------------------
# Agent trace tab
# --------------------------------------------------------------------

with tab_trace:
    st.caption(
        "This is the literal Reason → Act → Observe trace "
        "from the last agent call — the whole point of the "
        "project, made visible."
    )

    if "last_trace" in st.session_state:
        for step in st.session_state["last_trace"]:
            st.json(step)

    else:
        st.info(
            "Run something from the sidebar or Quiz tab "
            "to see a trace here."
        )