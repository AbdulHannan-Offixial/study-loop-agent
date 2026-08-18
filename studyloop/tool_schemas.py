TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "schedule",
            "description": (
                "Build or rebuild a day-by-day study plan for all current topics, "
                "respecting the exam date and daily hour budget. Call this after "
                "topics are parsed, and again any time replan decides hours "
                "should shift."
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
                "Generate a short quiz (3-5 questions) for a single topic "
                "the student just finished studying, to observe how well "
                "they actually know it."
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
                        "description": "How many questions, 3-5.",
                    },
                },
                "required": ["topic_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_result",
            "description": (
                "Record the student's quiz score for a topic and update "
                "its spaced-repetition state (SM-2). Call this immediately "
                "after a quiz is scored."
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
                            "0=blackout, 3=correct with difficulty, "
                            "5=perfect."
                        ),
                    },
                },
                "required": ["topic_name", "quality"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replan",
            "description": (
                "Re-derive the study plan using all quiz history so far: "
                "shift hours away from mastered topics toward weak ones, "
                "and slot in SM-2 review dates for topics due for "
                "resurfacing. Call this before starting the next study "
                "session."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reasoning": {
                        "type": "string",
                        "description": (
                            "Which topics are weak vs mastered and "
                            "how hours are shifting."
                        ),
                    }
                },
                "required": ["reasoning"],
            },
        },
    },
]