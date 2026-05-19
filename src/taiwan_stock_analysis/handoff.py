from __future__ import annotations

from typing import Any

from taiwan_stock_analysis.review_action_state import (
    apply_review_action_state,
    review_action_key,
    stale_review_action_state_rows,
)


NON_ADVICE_NOTICE = (
    "此交付品質檢查僅用於研究流程與資料完整性控管，"
    "不構成投資建議、買賣建議或持倉建議。"
)

EXPERT_AGENT_LABELS = {
    "source_audit": "資料來源專家",
    "workflow": "工作流健康專家",
    "reliability": "資料可信度專家",
    "valuation": "估值假設專家",
    "research_quality": "研究完整性專家",
    "fundamental_review": "基本面專家審查",
    "state": "狀態一致性專家",
}

ACTION_GATE_LABELS = {
    "source-audit-manual-review": "來源檢查需要人工確認",
    "source-audit-stale": "來源資料過期",
    "source-audit-unknown": "來源狀態不明",
    "workflow-error": "工作流程失敗",
    "workflow-warning": "工作流程需確認",
    "workflow-skipped": "工作流程未執行",
    "reliability-error": "資料可信度錯誤",
    "reliability-warning": "資料可信度警示",
    "valuation-unavailable": "估值輸出缺失或需確認",
    "fundamental-review-incomplete": "基本面專家審查不完整",
    "fundamental-review-low-quality": "基本面品質分數偏低",
    "fundamental-review-thesis-breakers": "基本面 thesis breaker 尚未處理",
    "fundamental-review-manual-check": "基本面專家問題尚未回覆",
    "research-state-blocked": "研究項目仍被阻塞",
    "research-state-new": "研究項目尚未分類",
    "research-state-review": "研究項目仍在審查",
    "research-quality-missing-thesis": "高優先項目缺少 thesis",
    "research-quality-missing-follow-up": "高優先項目缺少 follow-up questions",
}

ACTION_CATEGORY_BY_ID = {
    "source-audit-manual-review": "source_audit",
    "source-audit-stale": "source_audit",
    "source-audit-unknown": "source_audit",
    "workflow-error": "workflow",
    "workflow-warning": "workflow",
    "workflow-skipped": "workflow",
    "reliability-error": "reliability",
    "reliability-warning": "reliability",
    "valuation-unavailable": "valuation",
    "fundamental-review-incomplete": "fundamental_review",
    "fundamental-review-low-quality": "fundamental_review",
    "fundamental-review-thesis-breakers": "fundamental_review",
    "fundamental-review-manual-check": "fundamental_review",
    "research-state-blocked": "research_quality",
    "research-state-new": "research_quality",
    "research-state-review": "research_quality",
    "research-quality-missing-thesis": "research_quality",
    "research-quality-missing-follow-up": "research_quality",
}


def build_handoff_quality_gate(
    research_summary: dict[str, Any],
    state: dict[str, Any] | None = None,
    *,
    blocker_limit: int = 3,
) -> dict[str, Any]:
    queue_value = research_summary.get("review_action_queue")
    items_value = research_summary.get("items")
    queue = queue_value if isinstance(queue_value, list) else []
    items = items_value if isinstance(items_value, list) else []
    blockers: list[dict[str, str]] = []
    structural_failures: list[str] = []

    if queue_value is not None and not isinstance(queue_value, list):
        structural_failures.append("review_action_queue must be a list")
        blockers.append(_system_blocker("review_action_queue 格式錯誤，無法判斷交付狀態。"))
    if items_value is not None and not isinstance(items_value, list):
        structural_failures.append("items must be a list")
        blockers.append(_system_blocker("items 格式錯誤，無法檢查研究項目。"))

    overlaid_queue = apply_review_action_state(queue, state)
    open_blockers = _open_action_blockers(overlaid_queue)
    stale_rows = stale_review_action_state_rows(queue, state if isinstance(state, dict) else None)
    stale_blockers = [_stale_state_blocker(row) for row in stale_rows]
    missing_blockers = _missing_gate_action_blockers(items, overlaid_queue)
    blockers.extend(open_blockers)
    blockers.extend(stale_blockers)
    blockers.extend(missing_blockers)

    blocker_limit = max(0, blocker_limit)
    ready = not blockers and not structural_failures
    open_count = len(open_blockers)
    stale_count = len(stale_rows)
    missing_gate_count = len(missing_blockers)
    messages = [
        "handoff gate ready" if ready else "handoff gate blocked",
        f"open review actions: {open_count}",
        f"stale state entries: {stale_count}",
        f"missing gate actions: {missing_gate_count}",
    ]
    return {
        "ready": ready,
        "status": "ready" if ready else "blocked",
        "messages": messages,
        "failures": structural_failures,
        "blockers": blockers,
        "top_blockers": blockers[:blocker_limit],
        "blocker_count": len(blockers),
        "open_count": open_count,
        "stale_state_count": stale_count,
        "missing_gate_action_count": missing_gate_count,
        "total_actions": _review_action_row_count(overlaid_queue),
        "next_step": _next_step(open_count, stale_count, missing_gate_count),
        "non_advice_notice": NON_ADVICE_NOTICE,
    }


def _open_action_blockers(action_queue: list[Any]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    for item in action_queue:
        if not isinstance(item, dict):
            continue
        stock_id = _clean_string(item.get("stock_id")) or "-"
        company_name = _clean_string(item.get("company_name"))
        priority = _clean_string(item.get("priority"))
        actions = item.get("actions", [])
        if not isinstance(actions, list):
            continue
        for action in actions:
            if not isinstance(action, dict):
                continue
            status = _clean_string(action.get("status")) or "open"
            if status != "open":
                continue
            category = _clean_string(action.get("category"))
            action_id = _clean_string(action.get("id"))
            blockers.append(
                {
                    "kind": "open_action",
                    "stock_id": stock_id,
                    "company_name": company_name,
                    "priority": priority,
                    "severity": _clean_string(action.get("severity")),
                    "category": category,
                    "expert_label": _expert_label(category),
                    "action_id": action_id,
                    "message": _clean_string(action.get("message")) or ACTION_GATE_LABELS.get(action_id, "待處理審查事項"),
                    "next_step": "到審查動作列標記完成、稍後處理，或明確決定不處理。",
                    "focus_available": "true",
                }
            )
    return blockers


def _missing_gate_action_blockers(items: list[Any], overlaid_queue: list[Any]) -> list[dict[str, str]]:
    action_rows = _action_rows_by_key(overlaid_queue)
    blockers: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        stock_id = _clean_string(item.get("stock_id"))
        if not stock_id:
            continue
        for action_id in _expected_action_ids(item):
            key = review_action_key(stock_id, action_id)
            if key in action_rows:
                continue
            category = ACTION_CATEGORY_BY_ID.get(action_id, "workflow")
            blockers.append(
                {
                    "kind": "missing_gate_action",
                    "stock_id": stock_id,
                    "company_name": _clean_string(item.get("company_name")),
                    "priority": _clean_string(item.get("priority")),
                    "severity": "error",
                    "category": category,
                    "expert_label": _expert_label(category),
                    "action_id": action_id,
                    "message": f"研究摘要顯示「{ACTION_GATE_LABELS.get(action_id, action_id)}」，但 review-action queue 沒有對應 gate。",
                    "next_step": "重新產生 research_summary.json，或修正 review-action 產生邏輯後再交付。",
                    "focus_available": "false",
                }
            )
    return blockers


def _expected_action_ids(item: dict[str, Any]) -> list[str]:
    action_ids: list[str] = []
    source_audit_status = _clean_string(item.get("source_audit_status"))
    if source_audit_status == "manual_review":
        action_ids.append("source-audit-manual-review")
    elif source_audit_status == "stale":
        action_ids.append("source-audit-stale")
    elif source_audit_status == "unknown":
        action_ids.append("source-audit-unknown")

    workflow_status = _clean_string(item.get("workflow_status"))
    if workflow_status == "error":
        action_ids.append("workflow-error")
    elif workflow_status == "warning":
        action_ids.append("workflow-warning")
    elif workflow_status == "skipped":
        action_ids.append("workflow-skipped")

    reliability_status = _clean_string(item.get("reliability_status"))
    if reliability_status == "error":
        action_ids.append("reliability-error")
    elif reliability_status == "warning":
        action_ids.append("reliability-warning")

    if _has_attention_reason(item, "valuation output is unavailable or skipped"):
        action_ids.append("valuation-unavailable")

    review = item.get("fundamental_review")
    if isinstance(review, dict):
        verdict = _clean_string(review.get("verdict"))
        score = review.get("score")
        if verdict == "incomplete":
            action_ids.append("fundamental-review-incomplete")
        elif isinstance(score, int) and score < 60:
            action_ids.append("fundamental-review-low-quality")
        if _clean_string_list(review.get("thesis_breakers")):
            action_ids.append("fundamental-review-thesis-breakers")
        if _clean_string_list(review.get("questions")):
            action_ids.append("fundamental-review-manual-check")

    research_state = _clean_string(item.get("research_state"))
    if research_state == "blocked":
        action_ids.append("research-state-blocked")
    elif research_state == "new":
        action_ids.append("research-state-new")
    elif research_state == "review":
        action_ids.append("research-state-review")

    if _clean_string(item.get("priority")) == "high":
        if not _clean_string(item.get("thesis")):
            action_ids.append("research-quality-missing-thesis")
        if not _clean_string(item.get("follow_up_questions")):
            action_ids.append("research-quality-missing-follow-up")

    return _dedupe(action_ids)


def _action_rows_by_key(action_queue: list[Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for item in action_queue:
        if not isinstance(item, dict):
            continue
        stock_id = item.get("stock_id")
        actions = item.get("actions", [])
        if not isinstance(actions, list):
            continue
        for action in actions:
            if not isinstance(action, dict):
                continue
            action_id = action.get("id")
            if _clean_string(stock_id) and _clean_string(action_id):
                rows[review_action_key(stock_id, action_id)] = action
    return rows


def _stale_state_blocker(row: dict[str, str]) -> dict[str, str]:
    stock_id = _clean_string(row.get("stock_id")) or "-"
    action_id = _clean_string(row.get("action_id"))
    message = f"review_action_state.json 有過期項目：{stock_id} / {action_id}。"
    return {
        "kind": "stale_state",
        "stock_id": stock_id,
        "company_name": "",
        "priority": "",
        "severity": "warning",
        "category": "state",
        "expert_label": _expert_label("state"),
        "action_id": action_id,
        "message": message,
        "next_step": "執行 research action prune-stale，確認 state sidecar 與目前 queue 一致。",
        "focus_available": "false",
    }


def _system_blocker(message: str) -> dict[str, str]:
    return {
        "kind": "invalid_summary",
        "stock_id": "-",
        "company_name": "",
        "priority": "",
        "severity": "error",
        "category": "workflow",
        "expert_label": _expert_label("workflow"),
        "action_id": "",
        "message": message,
        "next_step": "重新產生 research_summary.json 後再執行 handoff gate。",
        "focus_available": "false",
    }


def _review_action_row_count(action_queue: list[Any]) -> int:
    count = 0
    for item in action_queue:
        if not isinstance(item, dict):
            continue
        actions = item.get("actions", [])
        if isinstance(actions, list):
            count += sum(1 for action in actions if isinstance(action, dict))
    return count


def _next_step(open_count: int, stale_count: int, missing_gate_count: int) -> str:
    if missing_gate_count:
        return "下一步：先修正 review-action 產生邏輯或重新產生 research_summary.json，避免靜默遺漏 gate。"
    if open_count:
        return "下一步：先處理 Top 3 阻塞事項，再回到審查動作表確認剩餘事項。"
    if stale_count:
        return "下一步：先 prune stale review-action state，再重新執行 handoff gate。"
    return "下一步：打開研究摘要、memo 與 pack，進行人工閱讀與簽核。"


def _has_attention_reason(item: dict[str, Any], expected: str) -> bool:
    reasons = item.get("attention_reasons", [])
    if not isinstance(reasons, list):
        return False
    expected = expected.lower()
    return any(expected in _clean_string(reason).lower() for reason in reasons)


def _clean_string(value: object) -> str:
    return str(value or "").strip()


def _clean_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clean_string(item) for item in value if _clean_string(item)]


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _expert_label(category: str) -> str:
    return EXPERT_AGENT_LABELS.get(category, category or "品質檢查")
