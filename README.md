# byteforge-converse-api-python

Python client for the ByteforgeConverse backend API. Thin HTTP wrapper that returns strongly-typed model instances from [`byteforge-converse-models`](https://github.com/jmazzahacks/byteforge-converse-models).

## Installation

```bash
pip install git+https://github.com/jmazzahacks/byteforge-converse-api-python.git
```

In `pyproject.toml`:
```toml
dependencies = [
    "byteforge-converse-api-python @ git+https://github.com/jmazzahacks/byteforge-converse-api-python.git",
]
```

In `requirements.txt`:
```
byteforge-converse-api-python @ git+https://github.com/jmazzahacks/byteforge-converse-api-python.git
```

This is a public repo — no token required. The client depends on `byteforge-converse-models` (also public, pulled in transitively).

## Auth and `X-User-Id`

ByteforgeConverse is **not** an auth system. The backend trusts whichever caller sends it `X-User-Id: <id>` to assert "this request is on behalf of user `<id>`." Your application owns auth; you pass the verified user identifier into the client.

```python
from byteforge_converse_api import ConverseClient

client = ConverseClient(
    base_url="http://converse.internal:5252",
    extra_headers={"X-User-Id": user_id},   # required for all per-user endpoints
)
```

A common pattern for a server-side integration: instantiate one `ConverseClient` per request, using the authenticated user id from your own session/JWT/cookie verification. Do **not** share a single client across users — `extra_headers` is set at construction time.

## Quick start: plain chat (no tools)

```python
from byteforge_converse_api import ConverseClient

with ConverseClient("http://converse.internal:5252", extra_headers={"X-User-Id": user_id}) as client:
    conv = client.create_conversation({
        "title": "Greeting",
        "system_prompt": "You are a friendly assistant.",
    })

    turn = client.chat(conv.id, "Say hi.")
    print(turn.message.content)
```

`turn` is a `ChatTurn`:
- `turn.message` — the persisted assistant `Message` (always set). For tool-only turns its `content` may be `""`.
- `turn.tool_calls` — `list[ToolCall]` if the model asked you to invoke tools, otherwise `None`.

## Driving a conversation with tools (the integration loop)

For form-filling flows, freeform agents, or any conversation that advertises tools to the model, the canonical pattern is to loop until the model stops asking for tool calls. Use `chat_tool_result` to feed each tool's output back and drive the next turn in **one** round trip.

```python
from byteforge_converse_api import ConverseClient, ConverseAPIError

SAVE_INVESTOR_PROFILE = {
    "type": "function",
    "function": {
        "name": "save_investor_profile",
        "description": "Persist the completed investor profile and close the interview.",
        "parameters": {
            "type": "object",
            "properties": {
                "profile_text": {"type": "string"},
            },
            "required": ["profile_text"],
        },
    },
}


def execute_tool(name: str, arguments_json: str) -> str:
    """Whatever the consumer wants. Return a string the model will read back."""
    if name == "save_investor_profile":
        import json
        payload = json.loads(arguments_json)
        # ... write to your DB, hit your MCP server, call an API, etc.
        return "saved"
    return f"Unknown tool: {name}"


def drive_chat(client: ConverseClient, conversation_id: str, user_content: str) -> str:
    """
    Run one user turn through the conversation, executing any tool calls the
    model emits along the way, and return the final assistant text the UI
    should display. Tool calls and tool results never leak to the caller —
    they are handled inside this loop.
    """
    turn = client.chat(conversation_id, user_content)
    while turn.tool_calls:
        # Execute each tool the model asked for. The OpenAI-spec contract
        # is "post all results before the next model turn" — for a single
        # tool call, chat_tool_result both posts the result AND drives the
        # next turn. For multiple tool calls in one turn, post the earlier
        # results via post_message() and use chat_tool_result() for the last.
        if len(turn.tool_calls) == 1:
            call = turn.tool_calls[0]
            result = execute_tool(call.name, call.arguments)
            turn = client.chat_tool_result(conversation_id, call.id, result)
        else:
            for call in turn.tool_calls[:-1]:
                client.post_message(conversation_id, {
                    "role": "tool",
                    "content": execute_tool(call.name, call.arguments),
                    "tool_call_id": call.id,
                })
            last = turn.tool_calls[-1]
            turn = client.chat_tool_result(
                conversation_id, last.id, execute_tool(last.name, last.arguments),
            )
    return turn.message.content


with ConverseClient("http://converse.internal:5252",
                    extra_headers={"X-User-Id": user_id}) as client:
    conv = client.create_conversation({
        "title": "Investor interview",
        "system_prompt": (
            "Interview the user to build their investor profile. When you "
            "have enough information, call save_investor_profile with the "
            "completed profile."
        ),
        "tools": [SAVE_INVESTOR_PROFILE],
    })

    reply = drive_chat(client, conv.id, "I'd like to start the interview.")
    print(reply)   # plain text — tool calls already handled
```

The browser-visible HTTP call from your UI to your server is one round trip per user turn (regardless of how many tool calls happened inside `drive_chat`).

## Two-call vs sugar — which to use

Both forms are supported. Pick by which fits your loop.

| Form | Calls | When to use |
|---|---|---|
| `client.chat_tool_result(conv, tool_call_id, content)` | 1 HTTP | Single tool call per turn, or the **last** tool result in a multi-tool turn. |
| `client.post_message(conv, {role: "tool", ...})` then `client.chat(conv, content)` | 2 HTTP | Multiple tool calls (post intermediate results with `post_message`); or when you specifically want to inject a user-side nudge before driving the next turn. |

`chat_tool_result` is strictly a convenience over the two-call form — it persists the tool message and drives the next turn off the persisted history, so you do not have to invent a `"what did the tool say?"` nudge.

## Wire-shape reference

```python
from byteforge_converse_models import Conversation, Message, ChatTurn, ToolCall

# Conversation — created once, advertises tools + system_prompt
Conversation(
    id="<uuid>",
    user_id="<your user id>",
    title="...",
    model="anthropic/claude-sonnet-4-5",          # optional override
    system_prompt="...",
    response_schema=None,                          # optional JSON-schema-constrained output
    tools=[...],                                   # optional OpenAI tool defs
    created_at=1700000000,
    updated_at=1700000000,
)

# ChatTurn — what chat() / chat_tool_result() return
ChatTurn(
    message=Message(role="assistant", content="...", tool_calls=[...], ...),
    tool_calls=[ToolCall(id="call_abc", name="save_investor_profile",
                         arguments='{"profile_text":"..."}')],
)
```

`ToolCall.arguments` is the **raw JSON string** emitted by the model. Parse it yourself with `json.loads()`.

## API surface

| Method | Returns |
|---|---|
| `create_conversation(payload)` | `Conversation` |
| `list_conversations(limit, offset)` | `list[Conversation]` |
| `get_conversation(id)` | `Conversation` |
| `delete_conversation(id)` | `None` |
| `list_messages(id, limit, offset)` | `list[Message]` |
| `post_message(id, payload)` | `Message` |
| `chat(id, content)` | `ChatTurn` |
| `chat_tool_result(id, tool_call_id, content)` | `ChatTurn` |
| `create_session(payload)` / `get_session(id)` / `delete_session(id)` | `Session` |

All methods raise `ConverseAPIError(status_code, message)` for both transport failures (non-2xx) and protocol-shape failures (malformed response). One except clause covers both:

```python
try:
    turn = client.chat(conv_id, "hello")
except ConverseAPIError as e:
    log.exception("converse failed: %s", e)
```

## Compatibility

| api-python | Requires backend | Notes |
|---|---|---|
| 0.3.x | image `:3` or later | adds `chat_tool_result` (`POST /chat/tool_result`) |
| 0.2.x | image `:2` or later | adds `ChatTurn` shape on `chat()` |

## Development

```bash
python -m venv .
source bin/activate
pip install --upgrade -r dev-requirements.txt
pip install -e .
```

## License

O'Saasy License — see [LICENSE](LICENSE). See https://osaasy.dev/ for details.

## Author

Jason Byteforge ([@jmazzahacks](https://github.com/jmazzahacks)) — jason@reallybadapps.com
