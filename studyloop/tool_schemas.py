TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "schedule",
            "description": (
                "Build or rebuild the student's concrete study schedule. "
                "The schedule must contain study sessions, revision sessions "
                "based on SM-2 review dates, and 15-minute quizzes. "
                "Call this after syllabus parsing and after quiz results change "
                "the student's mastery state."
                        ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reasoning": {
                        "type": "string",
                        "description": (
                            "Brief note on how hours are being allocated "
                            "across topics and why."
                        ),
                    }
                },
                "required": ["reasoning"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "generate_quiz",
            "description": (
                "Generate a short multiple-choice quiz with 3-5 questions "
                "for a single topic the student just finished studying. "
                "Each question must have exactly four options labeled A, B, C, and D. "
                "Include the correct answer internally, but never display the answer "
                "to the student."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_name": {
                        "type": "string",
                        "description": "Exact topic name as stored.",
                    },
                    "num_questions": {
                        "type": "integer",
                        "description": "How many questions, between 3 and 5.",
                    },
                },
                "required": ["topic_name"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "evaluate_quiz",
            "description": (
                "Evaluate a completed multiple-choice quiz. Compare the student's "
                "answers with the correct answers, calculate the objective score, "
                "and assign an SM-2 quality score from 0 to 5 based on the student's "
                "actual performance. Do not ask the student to self-evaluate."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_name": {
                        "type": "string",
                        "description": "Exact topic name as stored.",
                    },
                    "questions": {
                        "type": "array",
                        "description": (
                            "The quiz questions including their correct answers."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "question": {
                                    "type": "string",
                                },
                                "options": {
                                    "type": "object",
                                },
                                "correct_answer": {
                                    "type": "string",
                                },
                            },
                            "required": [
                                "question",
                                "options",
                                "correct_answer",
                            ],
                        },
                    },
                    "student_answers": {
                        "type": "object",
                        "description": (
                            "Mapping of question number to the student's "
                            "selected answer."
                        ),
                    },
                },
                "required": [
                    "topic_name",
                    "questions",
                    "student_answers",
                ],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "log_result",
            "description": (
                "Record the student's quiz score for a topic and update its "
                "spaced-repetition state (SM-2). Call this immediately after "
                "a quiz is evaluated."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_name": {
                        "type": "string",
                    },
                    "quality": {
                        "type": "integer",
                        "description": (
                            "0-5 recall quality score: "
                            "0=blackout, 3=correct with difficulty, 5=perfect."
                        ),
                    },
                },
                "required": [
                    "topic_name",
                    "quality",
                ],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "replan",
            "description": (
                "Rebuild the student's adaptive schedule after new learning "
                "evidence is available. Weak topics should receive more study "
                "and revision time, while strong or mastered topics should be "
                "spaced further apart according to their SM-2 state. "
                "The resulting schedule must include concrete revision and "
                "quiz activities."
                ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reasoning": {
                        "type": "string",
                        "description": (
                            "Which topics are weak vs mastered "
                            "and how hours are shifting."
                        ),
                    }
                },
                "required": ["reasoning"],
            },
        },
    },
]