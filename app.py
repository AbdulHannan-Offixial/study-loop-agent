import os
from datetime import date, datetime
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from pypdf import PdfReader
from studyloop import db
from studyloop.agent import run_agent_turn
from studyloop.db import init_db
from studyloop.tools import (
    evaluate_quiz,
    log_result,
    parse_syllabus,
)

# --------------------------------------------------
# Flask application
# --------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = (
    os.environ.get("SECRET_KEY")
    or "change-this-secret-key-before-production"
)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

# --------------------------------------------------
# Initialize database
# --------------------------------------------------
init_db()

# --------------------------------------------------
# Helper functions
# --------------------------------------------------
def format_plan(plan):
    """
    Prepare database plan data for the HTML templates.
    """
    formatted_plan = []
    for item in plan:
        item = dict(item)
        scheduled_at = item.get("scheduled_at")
        if scheduled_at:
            try:
                dt = datetime.fromisoformat(scheduled_at)
                item["formatted_time"] = dt.strftime("%I:%M %p")
            except ValueError:
                item["formatted_time"] = "Not scheduled"
        else:
            item["formatted_time"] = "Not scheduled"
            
        item["duration_minutes"] = int(item["planned_hours"] * 60)
        activity_type = item["activity_type"]
        if activity_type == "study":
            item["badge"] = "STUDY"
            item["description"] = "Learn and understand this topic."
        elif activity_type == "revision":
            item["badge"] = "REVISION"
            item["description"] = "Review this topic using active recall."
        elif activity_type == "quiz":
            item["badge"] = "QUIZ"
            item["description"] = "Test your understanding in 15 minutes."
        formatted_plan.append(item)
    return formatted_plan

def group_plan_by_date(plan):
    """
    Group activities by study date.
    """
    grouped = {}
    for item in plan:
        study_date = item["study_date"]
        if study_date not in grouped:
            try:
                dt = datetime.strptime(study_date, "%Y-%m-%d")
                formatted_date = dt.strftime("%A, %d %B %Y")
            except ValueError:
                formatted_date = study_date
            grouped[study_date] = {
                "formatted_date": formatted_date,
                "activities": [],
            }
        grouped[study_date]["activities"].append(item)
    return grouped

def extract_uploaded_syllabus(uploaded_file):
    """
    Extract text from an uploaded PDF or TXT file.
    """
    filename = uploaded_file.filename.lower()
    if filename.endswith(".pdf"):
        reader = PdfReader(uploaded_file)
        return "\n".join(
            page.extract_text() or "" for page in reader.pages
        )
    if filename.endswith(".txt"):
        return uploaded_file.read().decode("utf-8")
    raise ValueError("Only PDF and TXT syllabus files are supported.")

# --------------------------------------------------
# Routes
# --------------------------------------------------
@app.route("/")
def dashboard():
    """
    Main StudyLoop dashboard.
    """
    plan = db.get_plan()
    formatted_plan = format_plan(plan)
    grouped_plan = group_plan_by_date(formatted_plan)
    exam = db.get_exam()
    study_slots = db.get_study_slots()
    upcoming_quizzes = db.get_upcoming_quizzes()
    return render_template(
        "dashboard.html",
        grouped_plan=grouped_plan,
        exam=exam,
        study_slots=study_slots,
        upcoming_quizzes=upcoming_quizzes,
        today=date.today().strftime("%A, %d %B %Y"),
    )

@app.route("/plan", methods=["POST"])
def create_plan():
    """
    Parse syllabus and create the initial adaptive study plan.
    """
    uploaded = request.files.get("syllabus")
    exam_date = request.form.get("exam_date")
    if not uploaded or uploaded.filename == "":
        flash("Please upload your syllabus first.", "error")
        return redirect(url_for("dashboard"))
    if not exam_date:
        flash("Please choose your exam date.", "error")
        return redirect(url_for("dashboard"))
    try:
        db.set_exam(exam_date, 0.0)
        if not db.get_study_slots():
            flash("Please save at least one study time slot first.", "error")
            return redirect(url_for("dashboard"))
        text = extract_uploaded_syllabus(uploaded)
        result = parse_syllabus(text)
        if result.get("status") != "ok":
            flash(
                result.get("message", "Syllabus parsing failed."),
                "error",
            )
            return redirect(url_for("dashboard"))
        trace = run_agent_turn(
            "Build the initial study plan using the student's saved weekly availability."
        )
        session["last_trace"] = trace
        plan = db.get_plan()
        if plan:
            flash(
                f"Study plan created successfully. {len(plan)} activities were scheduled.",
                "success",
            )
        else:
            flash(
                "The syllabus was parsed, but no activities were created.",
                "error",
            )
    except Exception as error:
        flash(f"An error occurred: {str(error)}", "error")
    return redirect(url_for("dashboard"))

@app.route("/study-times", methods=["POST"])
def save_study_times():
    """
    Save the student's weekly study availability.
    """
    try:
        submitted_slots = []
        for weekday in range(7):
            enabled = request.form.get(f"enabled_{weekday}")
            if enabled:
                start_time = request.form.get(f"start_{weekday}")
                end_time = request.form.get(f"end_{weekday}")
                if not start_time or not end_time:
                    flash("Please provide both start and end times.", "error")
                    return redirect(url_for("dashboard"))
                if start_time >= end_time:
                    flash("End time must be after start time.", "error")
                    return redirect(url_for("dashboard"))
                submitted_slots.append(
                    {
                        "weekday": weekday,
                        "start_time": start_time,
                        "end_time": end_time,
                    }
                )
        if not submitted_slots:
            flash("Please select at least one study day.", "error")
            return redirect(url_for("dashboard"))
        db.save_study_slots(submitted_slots)
        flash("Your weekly study times were saved.", "success")
    except Exception as error:
        flash(f"Could not save study times: {str(error)}", "error")
    return redirect(url_for("dashboard"))

@app.route("/quiz")
def quiz_center():
    topics = db.get_all_topics()
    for topic in topics:
        topic["history"] = db.get_quiz_history(topic["id"])
    upcoming_quizzes = db.get_upcoming_quizzes()
    for quiz in upcoming_quizzes:
        scheduled_at = quiz.get("scheduled_at")
        if scheduled_at:
            try:
                dt = datetime.fromisoformat(scheduled_at)
                quiz["formatted_time"] = dt.strftime("%A, %d %B %Y %I:%M %p")
            except ValueError:
                quiz["formatted_time"] = quiz["study_date"]
        else:
            quiz["formatted_time"] = quiz["study_date"]
    return render_template(
        "quiz.html",
        topics=topics,
        upcoming_quizzes=upcoming_quizzes,
        quiz_topic=session.get("quiz_topic"),
        current_quiz=session.get("current_quiz"),
        today=date.today().strftime("%A, %d %B %Y"),
    )


@app.route("/quiz/start/<int:plan_id>")
def start_quiz(plan_id):
    """
    Select a scheduled quiz and automatically generate questions.
    """
    plan = db.get_plan()
    selected_quiz = next(
        (
            item for item in plan
            if item["id"] == plan_id and item["activity_type"] == "quiz"
        ),
        None,
    )
    if not selected_quiz:
        flash("Quiz not found.", "error")
        return redirect(url_for("quiz_center"))
        
    quiz_topic = selected_quiz["topic_name"]
    session["quiz_topic"] = quiz_topic
    session["quiz_plan_id"] = selected_quiz["id"]
    
    # Automatically generate quiz questions for the selected topic
    try:
        trace = run_agent_turn(
            f'Generate the scheduled 15-minute quiz for the topic "{quiz_topic}".'
        )
        session["last_trace"] = trace
        questions = None
        for step in trace:
            if (
                step.get("type") == "tool_call"
                and step.get("tool") == "generate_quiz"
            ):
                observation = step.get("observation", {})
                if observation.get("status") == "ok":
                    questions = observation.get("questions")
                    break
        if not questions:
            flash("The quiz could not be generated.", "error")
            return redirect(url_for("quiz_center"))
            
        session["current_quiz"] = questions
    except Exception as error:
        flash(f"Quiz generation failed: {str(error)}", "error")
        
    return redirect(url_for("quiz_center"))

@app.route("/quiz/generate", methods=["POST"])
def generate_quiz():
    """
    Generate the quiz for the topic selected from the study plan.
    """
    quiz_topic = session.get("quiz_topic")
    if not quiz_topic:
        flash("Please start a scheduled quiz first.", "error")
        return redirect(url_for("quiz_center"))
    try:
        trace = run_agent_turn(
            f'Generate the scheduled 15-minute quiz for the topic "{quiz_topic}".'
        )
        session["last_trace"] = trace
        questions = None
        for step in trace:
            if (
                step.get("type") == "tool_call"
                and step.get("tool") == "generate_quiz"
            ):
                observation = step.get("observation", {})
                if observation.get("status") == "ok":
                    questions = observation.get("questions")
                    break
        if not questions:
            flash("The quiz could not be generated.", "error")
            return redirect(url_for("quiz_center"))
        session["current_quiz"] = questions
        return redirect(url_for("quiz_center"))
    except Exception as error:
        flash(f"Quiz generation failed: {str(error)}", "error")
        return redirect(url_for("quiz_center"))

@app.route("/quiz/submit", methods=["POST"])
def submit_quiz():
    """
    Evaluate the submitted quiz, save the result, update the SM-2 learning state,
    mark the scheduled quiz as completed, and adapt the future study plan.
    """
    current_quiz = session.get("current_quiz")
    quiz_topic = session.get("quiz_topic")
    quiz_plan_id = session.get("quiz_plan_id")
    if not current_quiz or not quiz_topic:
        flash("There is no active quiz to submit.", "error")
        return redirect(url_for("quiz_center"))

    student_answers = {}
    for index, question in enumerate(current_quiz, start=1):
        answer_value = request.form.get(f"answer_{index - 1}")
        if answer_value is None:
            flash("Please answer every question before submitting.", "error")
            return redirect(url_for("quiz_center"))
        student_answers[str(index)] = answer_value

    try:
        result = evaluate_quiz(
            topic_name=quiz_topic,
            questions=current_quiz,
            student_answers=student_answers,
        )
    except Exception as error:
        flash(f"Quiz evaluation failed: {str(error)}", "error")
        return redirect(url_for("quiz_center"))

    if result.get("status") != "ok":
        flash(result.get("message", "Quiz evaluation failed."), "error")
        return redirect(url_for("quiz_center"))

    try:
        sm2_result = log_result(
            topic_name=quiz_topic,
            quality=result["quality"],
        )
    except Exception as error:
        flash(f"Failed to update the learning state: {str(error)}", "error")
        return redirect(url_for("quiz_center"))

    if sm2_result.get("status") != "ok":
        flash(
            sm2_result.get("message", "Failed to update the learning state."),
            "error",
        )
        return redirect(url_for("quiz_center"))

    topic = db.get_topic_by_name(quiz_topic)
    if not topic:
        flash("The quiz was completed, but topic was not found.", "error")
        return redirect(url_for("quiz_center"))

    db.update_latest_quiz_result(
        topic_id=topic["id"],
        correct=result["correct"],
        total=result["total"],
        percentage=result["percentage"],
        evaluation=result["evaluation"],
    )

    if quiz_plan_id:
        db.mark_plan_completed(quiz_plan_id)

    try:
        prompt = f"""The student completed a quiz. Topic: {quiz_topic}
Correct answers: {result['correct']}/{result['total']}
Percentage: {result['percentage']}%
SM-2 quality: {result['quality']}/5
Evaluation: {result['evaluation']}
The learning state is updated. Adapt the future study plan accordingly.
"""
        trace = run_agent_turn(prompt)
        session["last_trace"] = trace
    except Exception as error:
        session["last_trace"] = [
            {
                "type": "error",
                "message": f"Quiz saved, but replanning failed: {str(error)}",
            }
        ]

    session["last_quiz_result"] = {
        "topic_name": result["topic_name"],
        "correct": result["correct"],
        "total": result["total"],
        "percentage": result["percentage"],
        "quality": result["quality"],
        "evaluation": result["evaluation"],
        "plan_updated": True,
    }

    session.pop("current_quiz", None)
    session.pop("quiz_topic", None)
    session.pop("quiz_plan_id", None)

    return redirect(url_for("quiz_result"))

@app.route("/quiz/result")
def quiz_result():
    """
    Display the result of the most recently completed quiz.
    """
    result = session.get("last_quiz_result")
    if not result:
        flash("No quiz result is available.", "error")
        return redirect(url_for("quiz_center"))
    return render_template(
        "results.html",
        topic_name=result["topic_name"],
        correct=result["correct"],
        total=result["total"],
        percentage=result["percentage"],
        quality=result["quality"],
        evaluation=result["evaluation"],
        plan_updated=result.get("plan_updated", False),
    )

@app.route("/trace")
def agent_trace():
    """
    Display the most recent agent execution trace.
    """
    trace = session.get("last_trace")
    return render_template(
        "trace.html",
        trace=trace,
        today=date.today().strftime("%A, %d %B %Y"),
    )

if __name__ == "__main__":
    app.run(debug=True)