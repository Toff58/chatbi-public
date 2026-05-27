import json
from datetime import datetime
from pathlib import Path
from typing import Any

from config import BASE_DIR
from session_ids import normalize_session_id


SESSION_HISTORY_DIR = BASE_DIR / "logs" / "chat_sessions"
MAX_STORED_MESSAGES = 20


def session_history_path(session_id: str) -> Path:
    return SESSION_HISTORY_DIR / f"{normalize_session_id(session_id)}.json"


def load_session_messages(session_id: str) -> list[dict[str, Any]]:
    path = session_history_path(session_id)
    if not path.exists():
        return []

    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (json.JSONDecodeError, OSError):
        return []

    messages = payload.get("messages") if isinstance(payload, dict) else []
    if not isinstance(messages, list):
        return []
    normalized_messages = []
    for message in messages:
        normalized = _normalize_message(message)
        if normalized:
            normalized_messages.append(normalized)
    return normalized_messages


def save_session_messages(session_id: str, messages: list[dict[str, Any]]) -> None:
    path = session_history_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_messages = json.loads(
        json.dumps(messages[-MAX_STORED_MESSAGES:], ensure_ascii=False, default=str)
    )
    payload = {
        "session_id": normalize_session_id(session_id),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "messages": safe_messages,
    }
    temporary_path = path.with_name(f"{path.name}.tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    temporary_path.replace(path)


def clear_session_messages(session_id: str) -> None:
    path = session_history_path(session_id)
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _normalize_message(message: Any) -> dict[str, Any]:
    if not isinstance(message, dict):
        return {}

    role = message.get("role")
    if role == "user" and isinstance(message.get("content"), str):
        return {"role": "user", "content": message["content"]}
    if role == "assistant" and isinstance(message.get("state"), dict):
        return {"role": "assistant", "state": message["state"]}
    return {}
