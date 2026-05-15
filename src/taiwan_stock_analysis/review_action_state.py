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


def backup_review_action_state(path: Path, timestamp: datetime | None = None) -> Path | None:
    if not path.exists():
        return None
    backup_path = _unique_backup_path(path, timestamp or datetime.now(timezone.utc))
    backup_path.write_bytes(path.read_bytes())
    return backup_path


def set_review_action_state(
    path: Path,
    stock_id: str,
    action_id: str,
    status: str,
    note: str = "",
    updated_at: str | None = None,
) -> tuple[Path, Path | None]:
    status = _clean_string(status)
    if status not in ACTION_STATUSES:
        allowed = ", ".join(ACTION_STATUSES)
        raise ValueError(f"invalid review action status '{status}'. Allowed: {allowed}")

    state, warning = load_review_action_state(path)
    if warning:
        raise ValueError(warning)
    key = review_action_key(stock_id, action_id)
    state["actions"][key] = {
        "stock_id": _clean_string(stock_id),
        "action_id": _clean_string(action_id),
        "status": status,
        "note": _clean_string(note),
        "updated_at": updated_at or _utc_now(),
    }
    backup_path = backup_review_action_state(path)
    return write_review_action_state(path, state), backup_path


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
                updated_at = _clean_string(state_entry.get("updated_at"))
                if updated_at:
                    action["updated_at"] = updated_at
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


def current_review_action_keys(action_queue: list[Any]) -> set[str]:
    return {review_action_key(row["stock_id"], row["action_id"]) for row in review_action_rows(action_queue)}


def stale_review_action_state_rows(action_queue: list[Any], state: dict[str, Any] | None) -> list[dict[str, str]]:
    normalized_state = _normalize_state(state) if isinstance(state, dict) else {"version": STATE_VERSION, "actions": {}}
    current_keys = current_review_action_keys(action_queue)
    rows: list[dict[str, str]] = []
    for key, entry in sorted(_actions_by_key(normalized_state).items()):
        if key in current_keys or not isinstance(entry, dict):
            continue
        rows.append(
            {
                "stock_id": _clean_string(entry.get("stock_id")),
                "action_id": _clean_string(entry.get("action_id")),
                "status": _clean_status(entry.get("status")) or "open",
                "note": _clean_string(entry.get("note")),
                "updated_at": _clean_string(entry.get("updated_at")),
            }
        )
    return rows


def prune_stale_review_action_state(
    action_queue: list[Any],
    state: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    normalized_state = _normalize_state(state) if isinstance(state, dict) else {"version": STATE_VERSION, "actions": {}}
    current_keys = current_review_action_keys(action_queue)
    pruned_state: dict[str, Any] = {"version": STATE_VERSION, "actions": {}}
    for key, entry in sorted(_actions_by_key(normalized_state).items()):
        if key in current_keys:
            pruned_state["actions"][key] = deepcopy(entry)
    return pruned_state, stale_review_action_state_rows(action_queue, normalized_state)


def build_review_action_state_report(
    action_queue: list[Any],
    state: dict[str, Any] | None,
    next_open_limit: int = 5,
) -> dict[str, Any]:
    normalized_state = _normalize_state(state) if isinstance(state, dict) else {"version": STATE_VERSION, "actions": {}}
    overlaid_queue = apply_review_action_state(action_queue, normalized_state)
    rows = review_action_rows(overlaid_queue)
    stale_rows = stale_review_action_state_rows(action_queue, normalized_state)
    next_open_limit = max(0, next_open_limit)
    next_open = [row for row in rows if row["status"] == "open"][:next_open_limit]
    return {
        "total_actions": len(rows),
        "by_status": _review_action_status_counts(overlaid_queue),
        "stale_state": stale_rows,
        "stale_count": len(stale_rows),
        "last_updated": _last_updated(_actions_by_key(normalized_state)),
        "next_open": next_open,
    }


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


def _review_action_status_counts(action_queue: list[Any]) -> dict[str, int]:
    sparse_counts = summarize_review_action_state(action_queue)
    return {status: sparse_counts.get(status, 0) for status in ACTION_STATUSES}


def _last_updated(actions: dict[str, dict[str, Any]]) -> str:
    values = [
        _clean_string(entry.get("updated_at"))
        for entry in actions.values()
        if isinstance(entry, dict) and _clean_string(entry.get("updated_at"))
    ]
    return max(values) if values else "-"


def _unique_backup_path(path: Path, timestamp: datetime) -> Path:
    suffix = timestamp.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = path.with_name(f"{path.name}.bak-{suffix}")
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.bak-{suffix}.{counter}")
        counter += 1
    return candidate


def _clean_status(value: object) -> str:
    status = _clean_string(value)
    return status if status in ACTION_STATUSES else ""


def _clean_string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
