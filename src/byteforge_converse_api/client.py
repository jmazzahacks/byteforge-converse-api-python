import logging
from typing import Optional

import requests

from byteforge_converse_models import ChatTurn, Conversation, Message, Session

logger = logging.getLogger(__name__)


class ConverseAPIError(Exception):
    """Raised when the ByteforgeConverse backend returns a non-2xx response."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"[{status_code}] {message}")
        self.status_code = status_code
        self.message = message


class ConverseClient:
    """
    Thin HTTP client for the ByteforgeConverse backend.

    Auth is delegated to the consuming app — callers either talk to the
    backend directly through a trusted network path, or layer their own
    auth headers via `extra_headers`.
    """

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 30.0,
        extra_headers: Optional[dict] = None,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._session = requests.Session()
        if extra_headers:
            self._session.headers.update(extra_headers)

    # ---- sessions -----------------------------------------------------

    def create_session(self, payload: dict) -> Session:
        data = self._post("/api/sessions", payload)
        return Session.from_dict(data)

    def get_session(self, session_id: str) -> Session:
        data = self._get(f"/api/sessions/{session_id}")
        return Session.from_dict(data)

    def delete_session(self, session_id: str) -> None:
        self._delete(f"/api/sessions/{session_id}")

    # ---- conversations ------------------------------------------------

    def list_conversations(self, limit: int = 100, offset: int = 0) -> list[Conversation]:
        data = self._get("/api/conversations", params={"limit": limit, "offset": offset})
        return [Conversation.from_dict(row) for row in data.get("data", [])]

    def create_conversation(self, payload: dict) -> Conversation:
        data = self._post("/api/conversations", payload)
        return Conversation.from_dict(data)

    def get_conversation(self, conversation_id: str) -> Conversation:
        data = self._get(f"/api/conversations/{conversation_id}")
        return Conversation.from_dict(data)

    def delete_conversation(self, conversation_id: str) -> None:
        self._delete(f"/api/conversations/{conversation_id}")

    # ---- messages -----------------------------------------------------

    def list_messages(
        self,
        conversation_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Message]:
        data = self._get(
            f"/api/conversations/{conversation_id}/messages",
            params={"limit": limit, "offset": offset},
        )
        return [Message.from_dict(row) for row in data.get("data", [])]

    def post_message(self, conversation_id: str, payload: dict) -> Message:
        data = self._post(f"/api/conversations/{conversation_id}/messages", payload)
        return Message.from_dict(data)

    # ---- chat turn ----------------------------------------------------

    def chat(self, conversation_id: str, content: str) -> ChatTurn:
        """
        Submit a user message and receive a `ChatTurn`.

        `turn.message` is always set (the persisted assistant message — its
        `content` may be empty for a pure tool-call turn). `turn.tool_calls`
        is the list of tools the model wants the caller to execute, or None
        for a normal reply. Execute each tool and post the result back as a
        `tool`-role message (with matching `tool_call_id`) before the next
        `chat()` call.

        Raises `ConverseAPIError` for both transport and protocol-shape
        failures so callers only need one except clause.
        """
        data = self._post(
            f"/api/conversations/{conversation_id}/chat",
            {"content": content},
        )
        try:
            return ChatTurn.from_dict(data)
        except ValueError as e:
            raise ConverseAPIError(200, f"malformed ChatTurn response: {e}") from e

    def chat_tool_result(
        self,
        conversation_id: str,
        tool_call_id: str,
        content: str,
    ) -> ChatTurn:
        """
        Submit a tool result and immediately drive the next LLM turn.

        Sugar over `post_message(role="tool", ...)` + `chat()`: persists a
        `tool`-role message with the supplied `tool_call_id` and returns the
        model's next ChatTurn in one round trip.

        Use this after executing a tool the model requested in a previous
        ChatTurn. The returned ChatTurn may itself contain more tool calls —
        loop as needed until you get a plain assistant message.
        """
        data = self._post(
            f"/api/conversations/{conversation_id}/chat/tool_result",
            {"tool_call_id": tool_call_id, "content": content},
        )
        try:
            return ChatTurn.from_dict(data)
        except ValueError as e:
            raise ConverseAPIError(200, f"malformed ChatTurn response: {e}") from e

    # ---- internals ----------------------------------------------------

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        return self._request("GET", path, params=params)

    def _post(self, path: str, json_body: dict) -> dict:
        return self._request("POST", path, json_body=json_body)

    def _delete(self, path: str) -> dict:
        return self._request("DELETE", path)

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> dict:
        url = f"{self._base_url}{path}"
        resp = self._session.request(
            method,
            url,
            params=params,
            json=json_body,
            timeout=self._timeout,
        )
        if not resp.ok:
            try:
                detail = resp.json().get("message", resp.text)
            except ValueError:
                detail = resp.text
            raise ConverseAPIError(resp.status_code, detail)
        if not resp.content:
            return {}
        return resp.json()

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "ConverseClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
