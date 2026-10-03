"""JSONL audit storage with recursive secret redaction."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


class AuditTrail:
    """Append structured events without persisting known secret fields."""

    REDACTED = "[REDACTED]"
    SECRET_KEYS = {
        "password",
        "passwd",
        "token",
        "api_key",
        "secret",
        "private_key",
        "community_string",
    }

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "event_id": f"event-{uuid4().hex}",
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": self._redact(payload),
        }
        with self.path.open("a", encoding="utf-8") as audit_file:
            audit_file.write(json.dumps(event, sort_keys=True) + "\n")
        return event

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as audit_file:
            return [json.loads(line) for line in audit_file if line.strip()]

    @classmethod
    def _redact(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: cls.REDACTED if key.lower() in cls.SECRET_KEYS else cls._redact(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [cls._redact(item) for item in value]
        return value