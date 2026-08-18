import json

from studyloop.llm_client import chat
from studyloop.tool_schemas import TOOLS
from studyloop.tools import TOOL_FUNCTIONS


SYSTEM_PROMPT = """
You are StudyLoop, an exam-prep agent.

You have tools to schedule study time, generate quizzes, log results,
and replan around a student's actual performance.

Always prefer calling a tool over asking the student a question when
the answer is something you can find out yourself (e.g. by generating
a quiz).

Keep tool arguments concise.

When there is nothing further to do this turn, respond with a short
plain-text summary of what happened and stop.
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