from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ACTION_STATUSES = ("open", "done", "deferred", "ignored")
STATE_VERSION = 1


def review_action_key(stock_id: object, action_id: object) -> str:
    return f"{_clean_string(stock_id)}:{_clean_string(action_id)}"


def load_review_action_state(path: Path | None) -> tuple[dict[str, Any], str]:
    empty_state = {"version": STATE_VERSION, "actions": {}}
    if path is None or not path.exists():
        return empty_state, ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return empty_state, f"Could not read review action state: {exc}"
    if not isinstance(payload, dict):
        return empty_state, "Could not read review action state: root value must be an object"
    return _normalize_state(payload), ""


def write_review_action_state(path: Path, state: dict[str, Any]) -> Path:
    normalized = _normalize_state(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def set_review_action_state(
    path: Path,
    stock_id: str,
    action_id: str,
    status: str,
    note: str = "",
    updated_at: str | None = None,
) -> Path:
    status = _clean_string(status)
    if status not in ACTION_STATUSES:
        allowed = ", ".join(ACTION_STATUSES)
        raise ValueError(f"invalid review action status '{status}'. Allowed: {allowed}")

    state, _warning = load_review_action_state(path)
    key = review_action_key(stock_id, action_id)
    state["actions"][key] = {
        "stock_id": _clean_string(stock_id),
        "action_id": _clean_string(action_id),
        "status": status,
        "note": _clean_string(note),
        "updated_at": updated_at or _utc_now(),
    }
    return write_review_action_state(path, state)


def apply_review_action_state(
    action_queue: list[Any],
    state: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    actions_by_key = _actions_by_key(state)
    output: list[dict[str, Any]] = []
    for raw_item in action_queue:
        if not isinstance(raw_item, dict):
            continue
        item = deepcopy(raw_item)
        stock_id = item.get("stock_id")
        raw_actions = item.get("actions", [])
        item_actions: list[dict[str, Any]] = []
        if isinstance(raw_actions, list):
            for raw_action in raw_actions:
                if not isinstance(raw_action, dict):
                    continue
                action = deepcopy(raw_action)
                action_id = action.get("id")
                state_entry = actions_by_key.get(review_action_key(stock_id, action_id), {})
                action["status"] = _clean_status(state_entry.get("status")) or "open"
                note = _clean_string(state_entry.get("note"))
                if note:
                    action["note"] = note
                item_actions.append(action)
        item["actions"] = item_actions
        if item_actions:
            output.append(item)
    return output


def summarize_review_action_state(action_queue: list[Any]) -> dict[str, int]:
    counts = {status: 0 for status in ACTION_STATUSES}
    for item in action_queue:
        if not isinstance(item, dict):
            continue
        actions = item.get("actions", [])
        if not isinstance(actions, list):
            continue
        for action in actions:
            if not isinstance(action, dict):
                continue
            status = _clean_status(action.get("status")) or "open"
            counts[status] += 1
    return {status: counts[status] for status in ACTION_STATUSES if counts[status]}


def review_action_rows(action_queue: list[Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in action_queue:
        if not isinstance(item, dict):
            continue
        stock_id = _clean_string(item.get("stock_id"))
        priority = _clean_string(item.get("priority"))
        actions = item.get("actions", [])
        if not isinstance(actions, list):
            continue
        for action in actions:
            if not isinstance(action, dict):
                continue
            action_id = _clean_string(action.get("id"))
            if not stock_id or not action_id:
                continue
            rows.append(
                {
                    "stock_id": stock_id,
                    "priority": priority,
                    "status": _clean_status(action.get("status")) or "open",
                    "severity": _clean_string(action.get("severity")),
                    "category": _clean_string(action.get("category")),
                    "action_id": action_id,
                    "message": _clean_string(action.get("message")),
                }
            )
    return rows


def _normalize_state(payload: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {"version": STATE_VERSION, "actions": {}}
    raw_actions = payload.get("actions", {})
    if not isinstance(raw_actions, dict):
        return normalized
    for raw_key, raw_entry in raw_actions.items():
        if not isinstance(raw_entry, dict):
            continue
        stock_id = _clean_string(raw_entry.get("stock_id"))
        action_id = _clean_string(raw_entry.get("action_id"))
        if not stock_id or not action_id:
            key_parts = _clean_string(raw_key).split(":", 1)
            if len(key_parts) == 2:
                stock_id = stock_id or key_parts[0]
                action_id = action_id or key_parts[1]
        status = _clean_status(raw_entry.get("status"))
        if not stock_id or not action_id or not status:
            continue
        normalized["actions"][review_action_key(stock_id, action_id)] = {
            "stock_id": stock_id,
            "action_id": action_id,
            "status": status,
            "note": _clean_string(raw_entry.get("note")),
            "updated_at": _clean_string(raw_entry.get("updated_at")),
        }
    return normalized


def _actions_by_key(state: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(state, dict):
        return {}
    actions = state.get("actions", {})
    return actions if isinstance(actions, dict) else {}


def _clean_status(value: object) -> str:
    status = _clean_string(value)
    return status if status in ACTION_STATUSES else ""


def _clean_string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
