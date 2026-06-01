from __future__ import annotations

from pathlib import Path
from typing import Any

from taiwan_stock_analysis.handoff import NON_ADVICE_NOTICE


DEFAULT_REVIEWERS = {
    "",
    "handoff-reviewer",
    "reviewer",
    "tbd",
    "todo",
    "unknown",
}
DEFAULT_NOTE_PREFIXES = (
    "reviewed handoff blocker:",
    "review handoff blocker:",
)
DEFAULT_SUMMARIES = {
    "",
    "review source audit before handoff.",
    "summarize the manual review evidence for this handoff blocker.",
}
MIN_REVIEWER_LENGTH = 6
MIN_NOTE_LENGTH = 70
MIN_SUMMARY_LENGTH = 90


def assess_evidence_quality(
    *,
    note: object = "",
    reviewer: object = "",
    evidence_summary: object = "",
    evidence_path: Path | None = None,
    evidence_content: object | None = None,
) -> dict[str, Any]:
    """Assess whether dashboard-created evidence is review-ready.

    This is intentionally heuristic and deterministic. The handoff gate still
    owns structural readiness; this result tells the operator whether the
    evidence looks specific enough for reviewer confidence.
    """

    note_text = _clean_text(note)
    reviewer_text = _clean_text(reviewer)
    summary_text = _clean_text(evidence_summary)
    content_text = _evidence_content(evidence_path, evidence_content)

    checks = [
        _file_check(evidence_path),
        _reviewer_check(reviewer_text),
        _note_check(note_text),
        _summary_check(summary_text),
        _non_advice_check(content_text),
    ]
    checks = [check for check in checks if check is not None]
    issues = [check for check in checks if check["status"] != "pass"]

    if any(check["status"] == "fail" for check in checks):
        status = "draft"
        next_step = "Finish the missing evidence file or required notice, then re-run Reviewer Confidence."
    elif issues:
        status = "needs_review"
        next_step = "Strengthen reviewer, note, or evidence summary before treating this handoff as final."
    else:
        status = "handoff_ready"
        next_step = "Reviewer confidence looks ready for handoff."

    return {
        "checks": checks,
        "issues": issues,
        "next_step": next_step,
        "ready": status == "handoff_ready",
        "status": status,
    }


def _file_check(evidence_path: Path | None) -> dict[str, str] | None:
    if evidence_path is None:
        return None
    if evidence_path.exists() and evidence_path.is_file():
        return {
            "id": "evidence_file",
            "label": "Evidence file",
            "message": "Local evidence file exists.",
            "status": "pass",
        }
    return {
        "id": "evidence_file",
        "label": "Evidence file",
        "message": "Create the local evidence file before handoff.",
        "status": "fail",
    }


def _reviewer_check(reviewer: str) -> dict[str, str]:
    normalized = reviewer.lower()
    if normalized in DEFAULT_REVIEWERS or len(reviewer) < MIN_REVIEWER_LENGTH:
        return {
            "id": "reviewer_named",
            "label": "Reviewer",
            "message": "Replace the default reviewer with a named role or accountable reviewer.",
            "status": "warn",
        }
    return {
        "id": "reviewer_named",
        "label": "Reviewer",
        "message": "Reviewer is specific enough for handoff traceability.",
        "status": "pass",
    }


def _note_check(note: str) -> dict[str, str]:
    normalized = note.lower()
    if len(note) < MIN_NOTE_LENGTH or any(normalized.startswith(prefix) for prefix in DEFAULT_NOTE_PREFIXES):
        return {
            "id": "note_specific",
            "label": "Review note",
            "message": "Add what was checked and why the blocker can move forward.",
            "status": "warn",
        }
    return {
        "id": "note_specific",
        "label": "Review note",
        "message": "Review note explains the checked evidence.",
        "status": "pass",
    }


def _summary_check(summary: str) -> dict[str, str]:
    normalized = summary.lower()
    if len(summary) < MIN_SUMMARY_LENGTH or normalized in DEFAULT_SUMMARIES:
        return {
            "id": "summary_specific",
            "label": "Evidence summary",
            "message": "Summarize the actual evidence, not only the blocker title.",
            "status": "warn",
        }
    return {
        "id": "summary_specific",
        "label": "Evidence summary",
        "message": "Evidence summary is specific enough for reviewer confidence.",
        "status": "pass",
    }


def _non_advice_check(content: str) -> dict[str, str]:
    if NON_ADVICE_NOTICE in content or "Non-Investment-Advice" in content or "not investment advice" in content:
        return {
            "id": "non_advice_notice",
            "label": "Non-advice notice",
            "message": "Evidence includes the non-investment-advice notice.",
            "status": "pass",
        }
    return {
        "id": "non_advice_notice",
        "label": "Non-advice notice",
        "message": "Evidence must include the non-investment-advice notice.",
        "status": "fail",
    }


def _evidence_content(evidence_path: Path | None, evidence_content: object | None) -> str:
    if evidence_content is not None:
        return _clean_text(evidence_content)
    if evidence_path is None or not evidence_path.exists():
        return ""
    try:
        return evidence_path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _clean_text(value: object) -> str:
    return str(value or "").strip()
