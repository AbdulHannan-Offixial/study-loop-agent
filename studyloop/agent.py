import json

from studyloop.llm_client import chat
from studyloop.tool_schemas import TOOLS
from studyloop.tools import TOOL_FUNCTIONS


SYSTEM_PROMPT = """
You are StudyLoop, an adaptive exam-preparation agent.

Your responsibility is to manage a student's study schedule
using actual learning evidence.

You have tools to:

1. Build a study plan.
2. Generate quizzes.
3. Evaluate quiz performance.
4. Record quiz results.
5. Update SM-2 memory state.
6. Replan the student's schedule.

IMPORTANT RULES:

- When a syllabus has just been parsed and the user asks for an
  initial plan, call schedule().
- The schedule must contain concrete study activities.
- The schedule should contain 15-minute quizzes after appropriate
  study or revision sessions.
- Revision must follow the topic's SM-2 next_review_date.
- When quiz performance is available, call log_result().
- After logging a quiz result, call replan().
- Weak quiz performance means the topic needs additional study
  and/or earlier revision.
- Strong quiz performance means the topic can receive a longer
  review interval.
- Mastered topics should not consume normal study time.
- Do not invent schedule information outside the scheduling tool.
- Prefer tools over asking the student for information that can
  already be obtained from the database.

The Python scheduler owns exact dates and times.
You own the learning strategy.

When there is nothing further to do, return a concise summary.
"""


def run_agent_turn(
    user_message: str,
    max_steps: int = 6,
) -> list[dict]:
    """
    Runs one full Reason-Act-Observe cycle, which may span several
    tool calls.

    Returns the full trace for display in the UI, including the
    final text summary.
    """

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": user_message,
        },
    ]

    trace = []

    for step in range(max_steps):
        result = chat(
            messages,
            tools=TOOLS,
        )

        # ------------------------------------------------------------
        # The model answered with normal text.
        # The agent has finished this turn.
        # ------------------------------------------------------------
        if result["type"] == "text":
            trace.append(
                {
                    "step": step,
                    "type": "final",
                    "content": result["content"],
                }
            )

            return trace

        # ------------------------------------------------------------
        # ACT:
        # The model requested a tool.
        # ------------------------------------------------------------
        tool_name = result["name"]
        args = result["arguments"]

        fn = TOOL_FUNCTIONS.get(tool_name)

        if fn is None:
            observation = {
                "status": "error",
                "message": f"No such tool: {tool_name}",
            }
        else:
            observation = fn(**args)

        trace.append(
            {
                "step": step,
                "type": "tool_call",
                "tool": tool_name,
                "arguments": args,
                "observation": observation,
            }
        )

        # ------------------------------------------------------------
        # OBSERVE:
        # Feed the tool call and its result back into the conversation.
        # ------------------------------------------------------------
        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": result["id"],
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(args),
                        },
                    }
                ],
            }
        )

        messages.append(
            {
                "role": "tool",
                "tool_call_id": result["id"],
                "content": json.dumps(observation),
            }
        )

        # The loop continues.
        # The next iteration is the next Reason step.

    # ------------------------------------------------------------
    # Safety valve:
    # Prevent the agent from looping forever.
    # ------------------------------------------------------------
    trace.append(
        {
            "step": max_steps,
            "type": "final",
            "content": (
                "Stopped after max_steps — check the trace "
                "for a possible loop."
            ),
        }
    )

    return trace