from __future__ import annotations

# Leaf module: pure data, zero internal imports. Exists to break the
# `dashboard -> page -> workbench -> dashboard` import cycle -- these constants
# used to live only as module-level attributes on `dashboard.py`. Values are
# copied verbatim from `dashboard.py` (lines 21-66) and must stay in sync with
# it until the old dashboard module is retired (Task 11).

REVIEW_ACTION_SEVERITIES = ("error", "stale", "unknown", "manual_review", "warning", "info")
REVIEW_ACTION_PRIORITIES = ("high", "medium", "low")
REVIEW_ACTION_SEVERITY_LABELS = {
    "error": "錯誤",
    "stale": "資料過期",
    "unknown": "狀態不明",
    "manual_review": "需人工確認",
    "warning": "需注意",
    "info": "提醒",
}
REVIEW_ACTION_CATEGORY_LABELS = {
    "source_audit": "來源檢查",
    "workflow": "工作流程",
    "reliability": "資料可信度",
    "valuation": "估值",
    "research_quality": "研究品質",
    "fundamental_review": "基本面專家審查",
}
REVIEW_ACTION_PRIORITY_LABELS = {"high": "高", "medium": "中", "low": "低"}
REVIEW_ACTION_STATUS_LABELS = {
    "open": "待處理",
    "done": "已完成",
    "deferred": "稍後處理",
    "ignored": "不處理",
}
