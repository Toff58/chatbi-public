import re


MAX_SESSION_ID_LENGTH = 80


def normalize_session_id(session_id: str | None, *, fallback: str = "default") -> str:
    raw_value = str(session_id or "").strip()
    fallback_value = _clean(fallback)
    if not raw_value:
        return fallback_value

    normalized = _clean(raw_value)
    if normalized:
        return normalized[:MAX_SESSION_ID_LENGTH]
    return fallback_value


def _clean(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return cleaned.strip("._-")[:MAX_SESSION_ID_LENGTH]
