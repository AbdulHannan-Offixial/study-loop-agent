from studyloop.db import init_db
from studyloop import db
from studyloop.tools import parse_syllabus
from studyloop.agent import run_agent_turn


init_db()


# 1. One-time setup (not agent-driven, see Step 5 note)
db.set_exam(
    exam_date="2026-09-30",
    daily_hours=2.0,
)


sample_syllabus = """
Week 1: Arrays and Strings
Week 2: Linked Lists
Week 3: Trees and Graphs
Week 4: Dynamic Programming
"""


print(parse_syllabus(sample_syllabus))


# 2. Let the agent take it from here
trace = run_agent_turn(
    "Build the initial study plan for me."
)


for step in trace:
    print(step)