# byteforge-converse-api-python

Python client for the ByteforgeConverse backend API. Wraps the REST endpoints and returns strongly-typed model instances from [`byteforge-converse-models`](https://github.com/jmazzahacks/byteforge-converse-models).

## Installation

This is a public repo — no token required.

```bash
pip install git+https://github.com/jmazzahacks/byteforge-converse-api-python.git
```

### As a dependency in pyproject.toml
```toml
dependencies = [
    "byteforge-converse-api-python @ git+https://github.com/jmazzahacks/byteforge-converse-api-python.git",
]
```

### As a dependency in requirements.txt
```
byteforge-converse-api-python @ git+https://github.com/jmazzahacks/byteforge-converse-api-python.git
```

## Usage

```python
from byteforge_converse_api import ConverseClient

with ConverseClient("https://converse.example.com") as client:
    convos = client.list_conversations()
    for c in convos:
        print(c.id, c.title)

    turn = client.chat(convos[0].id, content="Hello!")

    # `turn.message` is always set (the persisted assistant reply).
    # `turn.tool_calls` is populated when the model asked you to invoke
    # one or more tools — execute each, then post the result back as a
    # `tool`-role message with matching `tool_call_id` before the next
    # chat() call.
    print(turn.message.content)
    for call in (turn.tool_calls or []):
        result = run_tool(call.name, call.arguments)
        client.post_message(convos[0].id, {
            "role": "tool",
            "content": result,
            "tool_call_id": call.id,
        })
```

Auth is delegated to the consuming app — pass auth headers via `extra_headers={...}` or set them on a `requests.Session` you bring yourself.

## Development

```bash
python -m venv .
source bin/activate
pip install -r dev-requirements.txt
pip install -e .
```

## License

O'Saasy License — see [LICENSE](LICENSE). See https://osaasy.dev/ for details.

## Author

Jason Byteforge ([@jmazzahacks](https://github.com/jmazzahacks)) — jason@reallybadapps.com
