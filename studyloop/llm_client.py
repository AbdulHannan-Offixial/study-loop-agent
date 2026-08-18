import json
import os

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

client = Groq(api_key=os.environ["GROQ_API_KEY"])
MODEL = "openai/gpt-oss-20b" 


def chat(
    messages: list[dict],
    tools: list[dict] | None = None,
) -> dict:
    """
    messages: standard chat list, e.g.
        [{"role": "user", "content": "..."}]

    tools: optional list of tool schemas
        (see tool_schemas.py)

    Returns a normalized dict:

        {
            "type": "text",
            "content": "..."
        }

        Model answered in prose — loop should stop.

        {
            "type": "tool_call",
            "name": "...",
            "arguments": {...},
            "id": "..."
        }

        Model wants a tool executed.
    """

    kwargs = {
        "model": MODEL,
        "messages": messages,
    }

    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    response = client.chat.completions.create(**kwargs)
    choice = response.choices[0].message

    if choice.tool_calls:
        # We process one tool call per turn:
        # simpler loop, easier to debug.
        call = choice.tool_calls[0]

        return {
            "type": "tool_call",
            "name": call.function.name,
            "arguments": json.loads(call.function.arguments),
            "id": call.id,
        }

    return {
        "type": "text",
        "content": choice.content,
    }


# --------------------------------------------------------------------
# TO SWITCH BACK TO THE CLAUDE API LATER (if you get API credits):
#
#     pip install anthropic
#
#     from anthropic import Anthropic
#
#     client = Anthropic(
#         api_key=os.environ["ANTHROPIC_API_KEY"]
#     )
#
#     response = client.messages.create(
#         model="claude-sonnet-4-5",
#         max_tokens=1024,
#         messages=messages,
#         tools=tools,
#     )
#
#     Claude returns response.content as a list of blocks;
#     find the one with type == "tool_use"
#     (name, input, id) or type == "text" (text).
#
#     Adjust the return dict above to match and nothing else in the
#     project needs to change — that's the entire point of this wrapper.
# --------------------------------------------------------------------