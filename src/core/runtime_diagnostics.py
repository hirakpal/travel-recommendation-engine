"""Structured, bounded runtime tracing for the Streamlit workflow."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
import logging
from typing import Any, Deque, Dict, Optional

logger = logging.getLogger(__name__)
_EVENTS: Deque[Dict[str, Any]] = deque(maxlen=250)


def _safe(value: Any, limit: int = 1200) -> Any:
    """Make trace values JSON-safe and prevent oversized UI/log entries."""

    if value is None or isinstance(value, (str, int, float, bool)):
        result = value
    elif hasattr(value, "model_dump"):
        result = value.model_dump(mode="json")
    elif isinstance(value, dict):
        result = {str(k): _safe(v, limit) for k, v in value.items()}
    elif isinstance(value, (list, tuple, set)):
        result = [_safe(item, limit) for item in value]
    else:
        result = str(value)

    try:
        encoded = json.dumps(result, default=str)
    except (TypeError, ValueError):
        result = str(result)
        encoded = json.dumps(result)

    if len(encoded) > limit:
        return encoded[: limit - 3] + "..."
    return result


def record_event(
    component: str,
    action: str,
    *,
    mode: str = "system",
    status: str = "info",
    input_data: Any = None,
    output_data: Any = None,
    trip_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Record one workflow event and mirror a compact version to logging."""

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "component": component,
        "action": action,
        "mode": mode,
        "status": status,
        "input": _safe(input_data),
        "output": _safe(output_data),
        "trip_id": trip_id,
        "details": _safe(details or {}),
    }
    _EVENTS.append(event)
    logger.info(
        "RUNTIME_EVENT component=%s action=%s mode=%s status=%s trip_id=%s",
        component,
        action,
        mode,
        status,
        trip_id or "-",
    )
    return event


def get_events() -> list[Dict[str, Any]]:
    """Return a copy of the current bounded event history."""

    return list(_EVENTS)


def clear_events() -> None:
    """Clear runtime events when the user starts a new conversation."""

    _EVENTS.clear()
