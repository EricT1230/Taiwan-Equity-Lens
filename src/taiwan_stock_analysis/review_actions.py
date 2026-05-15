from __future__ import annotations

from collections import Counter
from typing import Any


ACTION_CATEGORIES = ("source_audit", "workflow", "reliability", "valuation", "research_quality")
ACTION_SEVERITIES = ("error", "stale", "unknown", "manual_review", "warning", "info")
SEVERITY_RANK = {"error": 0, "stale": 1, "unknown": 2, "manual_review": 3, "warning": 4, "info": 5}
PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


def build_review_actions(item: dict[str, Any]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    _append_action(actions, _source_audit_action(item))
    _append_action(actions, _workflow_action(item))
    _append_action(actions, _reliability_action(item))
    _append_action(actions, _valuation_action(item))
    for action in _research_quality_actions(item):
        _append_action(actions, action)
    return sorted(actions, key=_action_sort_key)


def build_review_action_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    actions = _all_actions(items)
    by_category = Counter(action["category"] for action in actions)
    by_severity = Counter(action["severity"] for action in actions)
    return {
        "total_open": len(actions),
        "by_category": {key: by_category[key] for key in sorted(by_category)},
        "by_severity": {
            severity: by_severity[severity]
            for severity in ACTION_SEVERITIES
            if by_severity[severity]
        },
    }


def build_review_action_queue(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue_items = []
    for item in items:
        actions = _valid_actions(item.get("review_actions"))
        if not actions:
            continue
        sorted_actions = sorted(actions, key=_action_sort_key)
        queue_items.append(
            {
                "stock_id": str(item.get("stock_id") or ""),
                "company_name": str(item.get("company_name") or ""),
                "priority": str(item.get("priority") or ""),
                "actions": sorted_actions,
            }
        )
    return sorted(queue_items, key=_queue_sort_key)


def _source_audit_action(item: dict[str, Any]) -> dict[str, str] | None:
    status = _clean_string(item.get("source_audit_status"))
    if status in {"", "fresh", "skipped"}:
        return None
    if status == "stale":
        return _action(
            "source-audit-stale",
            "source_audit",
            "stale",
            "Refresh or verify stale source-audit data before handoff.",
        )
    if status == "unknown":
        return _action(
            "source-audit-unknown",
            "source_audit",
            "unknown",
            "Review missing or invalid source-audit metadata before handoff.",
        )
    if status == "manual_review":
        reasons = _clean_string_list(item.get("source_audit_reasons"))
        reason_text = "; ".join(reasons) if reasons else "manual source review required"
        return _action(
            "source-audit-manual-review",
            "source_audit",
            "manual_review",
            f"Review source audit: {reason_text}",
        )
    return None


def _workflow_action(item: dict[str, Any]) -> dict[str, str] | None:
    status = _clean_string(item.get("workflow_status"))
    if status == "error":
        detail = _first_attention_reason(item, "workflow failed")
        message = f"Resolve workflow failure: {detail}" if detail else "Resolve workflow failure before handoff."
        return _action("workflow-error", "workflow", "error", message)
    if status == "warning":
        return _action("workflow-warning", "workflow", "warning", "Inspect partial or fallback workflow output.")
    if status == "skipped":
        return _action("workflow-skipped", "workflow", "info", "Run or attach workflow outputs before handoff.")
    return None


def _reliability_action(item: dict[str, Any]) -> dict[str, str] | None:
    status = _clean_string(item.get("reliability_status"))
    if status == "error":
        return _action("reliability-error", "reliability", "error", "Resolve data reliability errors before handoff.")
    if status == "warning":
        return _action("reliability-warning", "reliability", "warning", "Inspect data reliability warning before handoff.")
    return None


def _valuation_action(item: dict[str, Any]) -> dict[str, str] | None:
    reason = _first_attention_reason(item, "valuation output is unavailable or skipped")
    if not reason:
        return None
    return _action("valuation-unavailable", "valuation", "warning", "Complete or verify valuation output before handoff.")


def _research_quality_actions(item: dict[str, Any]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    state = _clean_string(item.get("research_state"))
    if state == "blocked":
        actions.append(
            _action("research-state-blocked", "research_quality", "warning", "Unblock this research item before handoff.")
        )
    elif state == "new":
        actions.append(_action("research-state-new", "research_quality", "info", "Review and classify this new research item."))
    elif state == "review":
        actions.append(_action("research-state-review", "research_quality", "info", "Complete active review checks for this item."))

    priority = _clean_string(item.get("priority"))
    if priority == "high" and not _has_research_value(item.get("thesis")):
        actions.append(
            _action(
                "research-quality-missing-thesis",
                "research_quality",
                "warning",
                "Add a thesis for this high-priority item.",
            )
        )
    if priority == "high" and not _has_research_value(item.get("follow_up_questions")):
        actions.append(
            _action(
                "research-quality-missing-follow-up",
                "research_quality",
                "warning",
                "Add follow-up questions for this high-priority item.",
            )
        )
    return actions


def _append_action(actions: list[dict[str, str]], action: dict[str, str] | None) -> None:
    if action is None:
        return
    if action["id"] in {existing["id"] for existing in actions}:
        return
    actions.append(action)


def _action(action_id: str, category: str, severity: str, message: str) -> dict[str, str]:
    return {
        "id": action_id,
        "category": category if category in ACTION_CATEGORIES else "workflow",
        "severity": severity if severity in ACTION_SEVERITIES else "info",
        "message": _clean_string(message) or "Review this item before handoff.",
        "status": "open",
    }


def _action_sort_key(action: dict[str, str]) -> tuple[int]:
    return (SEVERITY_RANK.get(action.get("severity", ""), len(SEVERITY_RANK)),)


def _queue_sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
    actions = _valid_actions(item.get("actions"))
    top_severity = min(
        (SEVERITY_RANK.get(action.get("severity", ""), len(SEVERITY_RANK)) for action in actions),
        default=len(SEVERITY_RANK),
    )
    return (
        top_severity,
        PRIORITY_RANK.get(_clean_string(item.get("priority")), len(PRIORITY_RANK)),
        _clean_string(item.get("stock_id")),
    )


def _all_actions(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    for item in items:
        actions.extend(_valid_actions(item.get("review_actions")))
    return actions


def _valid_actions(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    actions: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for raw_action in value:
        if not isinstance(raw_action, dict):
            continue
        action_id = _clean_string(raw_action.get("id"))
        if not action_id or action_id in seen_ids:
            continue
        category = _clean_string(raw_action.get("category"))
        severity = _clean_string(raw_action.get("severity"))
        message = _clean_string(raw_action.get("message"))
        status = _clean_string(raw_action.get("status")) or "open"
        actions.append(
            {
                "id": action_id,
                "category": category if category in ACTION_CATEGORIES else "workflow",
                "severity": severity if severity in ACTION_SEVERITIES else "info",
                "message": message or "Review this item before handoff.",
                "status": status,
            }
        )
        seen_ids.add(action_id)
    return actions


def _first_attention_reason(item: dict[str, Any], prefix: str) -> str:
    reasons = item.get("attention_reasons")
    if not isinstance(reasons, list):
        return ""
    for reason in reasons:
        if not isinstance(reason, str):
            continue
        stripped = reason.strip()
        if stripped.startswith(prefix):
            return stripped
    return ""


def _clean_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _clean_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for raw in value:
        text = _clean_string(raw)
        if text and text not in output:
            output.append(text)
    return output


def _has_research_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, list):
        return any(_clean_string(entry) not in {"", "-"} for entry in value)
    return _clean_string(value) not in {"", "-"}
