from __future__ import annotations

import json
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from taiwan_stock_analysis.dashboard import discover_dashboard_items, render_dashboard_html
from taiwan_stock_analysis.handoff import NON_ADVICE_NOTICE, build_handoff_quality_gate
from taiwan_stock_analysis.handoff_pack import write_handoff_evidence_pack
from taiwan_stock_analysis.review_action_state import (
    build_review_action_state_report,
    load_review_action_state,
    set_review_action_state,
)

DashboardOpener = Callable[[str], object]
DashboardServer = ThreadingHTTPServer


def set_review_action_status_from_payload(
    payload: dict[str, Any],
    *,
    allowed_roots: list[Path],
) -> dict[str, Any]:
    state_path = _allowed_state_path(str(payload.get("state_path") or ""), allowed_roots)
    stock_id = _required_text(payload, "stock_id")
    action_id = _required_text(payload, "action_id")
    status = _required_text(payload, "status")
    note = str(payload.get("note") or "")
    reviewer = str(payload.get("reviewer") or "")
    evidence_url = str(payload.get("evidence_url") or "")

    output_path, backup_path = set_review_action_state(
        state_path,
        stock_id,
        action_id,
        status,
        note=note,
        reviewer=reviewer,
        evidence_url=evidence_url,
    )
    report = _state_report_for_path(output_path)
    return {
        "action_id": action_id,
        "backup_path": str(backup_path) if backup_path else "",
        "by_status": report.get("by_status", {}),
        "last_updated": report.get("last_updated", "-"),
        "ok": True,
        "note": note.strip(),
        "reviewer": reviewer.strip(),
        "evidence_missing_count": report.get("evidence_missing_count", 0),
        "invalid_evidence_count": report.get("invalid_evidence_count", 0),
        "handoff_status": report.get("handoff_status", "blocked"),
        "ready": bool(report.get("ready")),
        "blocker_count": report.get("blocker_count", 0),
        "open_count": report.get("open_count", 0),
        "next_step": report.get("next_step", ""),
        "evidence_url": evidence_url.strip(),
        "state_path": str(output_path),
        "status": status,
        "stale_count": report.get("stale_count", 0),
        "stock_id": stock_id,
        "updated_at": report.get("last_updated", "-"),
    }


def compose_evidence_from_payload(
    payload: dict[str, Any],
    *,
    allowed_roots: list[Path],
) -> dict[str, Any]:
    state_path = _allowed_state_path(str(payload.get("state_path") or ""), allowed_roots)
    stock_id = _required_text(payload, "stock_id")
    action_id = _required_text(payload, "action_id")
    status = str(payload.get("status") or "done").strip()
    if status == "open":
        raise ValueError("evidence composer status must be done, deferred, or ignored")
    note = _required_text(payload, "note")
    reviewer = _required_text(payload, "reviewer")
    evidence_summary = _required_text(payload, "evidence_summary")
    evidence_url = str(payload.get("evidence_url") or "").strip() or _default_evidence_url(stock_id, action_id)
    evidence_path = _allowed_evidence_path(evidence_url, state_path, allowed_roots)

    evidence_created = not evidence_path.exists()
    overwrite = _payload_bool(payload.get("overwrite"))
    if evidence_created or overwrite:
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(
            _compose_evidence_markdown(
                stock_id=stock_id,
                action_id=action_id,
                status=status,
                note=note,
                reviewer=reviewer,
                evidence_summary=evidence_summary,
            ),
            encoding="utf-8",
        )

    state_result = set_review_action_status_from_payload(
        {
            **payload,
            "state_path": str(state_path),
            "stock_id": stock_id,
            "action_id": action_id,
            "status": status,
            "note": note,
            "reviewer": reviewer,
            "evidence_url": evidence_url,
        },
        allowed_roots=allowed_roots,
    )
    return {
        **state_result,
        "evidence_created": evidence_created,
        "evidence_path": str(evidence_path),
        "evidence_updated": bool(overwrite and not evidence_created),
        "evidence_url": evidence_url,
    }


def write_handoff_pack_from_payload(
    payload: dict[str, Any],
    *,
    allowed_roots: list[Path],
) -> dict[str, Any]:
    research_summary_path = _allowed_path(
        str(payload.get("research_summary_path") or ""),
        allowed_roots,
        label="research_summary_path",
    )
    raw_state_path = str(payload.get("state_path") or "").strip()
    state_path = (
        _allowed_path(raw_state_path, allowed_roots, label="state_path")
        if raw_state_path
        else research_summary_path.with_name("review_action_state.json")
    )
    raw_output_dir = str(payload.get("output_dir") or "").strip()
    output_dir = (
        _allowed_path(raw_output_dir, allowed_roots, label="output_dir")
        if raw_output_dir
        else research_summary_path.parent / "handoff-pack"
    )
    if not any(_is_relative_to(output_dir.resolve(), root.resolve()) for root in allowed_roots):
        raise ValueError("output_dir is outside the served dashboard directories")

    try:
        blocker_limit = int(payload.get("blocker_limit") or 10)
    except (TypeError, ValueError) as exc:
        raise ValueError("blocker_limit must be an integer") from exc

    summary_path = write_handoff_evidence_pack(
        research_summary_path,
        output_dir,
        state_path=state_path,
        output_format=str(payload.get("format") or "both"),
        blocker_limit=blocker_limit,
    )
    summary = _load_pack_summary(summary_path)
    return {
        "blocker_count": summary.get("blocker_count", 0),
        "evidence_missing_count": summary.get("evidence_missing_count", 0),
        "gate_status": summary.get("gate_status", "blocked"),
        "html_path": summary.get("html_path", ""),
        "invalid_evidence_count": summary.get("invalid_evidence_count", 0),
        "markdown_path": summary.get("markdown_path", ""),
        "ok": True,
        "output_dir": str(output_dir),
        "ready": bool(summary.get("ready")),
        "research_summary_path": str(research_summary_path),
        "state_path": str(state_path),
        "summary_path": str(summary_path),
    }


def serve_dashboard(
    search_dirs: list[Path],
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
    opener: DashboardOpener | None = None,
) -> str:
    server, url = create_dashboard_server(search_dirs, host=host, port=port)
    if open_browser:
        (opener or webbrowser.open)(url)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return url


def create_dashboard_server(
    search_dirs: list[Path],
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> tuple[DashboardServer, str]:
    roots = [directory.resolve() for directory in search_dirs]
    handler = _build_handler(roots)
    server = ThreadingHTTPServer((host, port), handler)
    actual_host, actual_port = server.server_address[:2]
    return server, f"http://{actual_host}:{actual_port}/"


def _build_handler(search_dirs: list[Path]) -> type[BaseHTTPRequestHandler]:
    class DashboardRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path not in {"/", "/dashboard"}:
                self._send_json({"error": "not found", "ok": False}, status=HTTPStatus.NOT_FOUND)
                return
            items = discover_dashboard_items(search_dirs)
            html = render_dashboard_html(items, action_api_enabled=True)
            body = html.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if self.path not in {
                "/api/review-actions/set",
                "/api/handoff-pack/write",
                "/api/evidence/compose-and-set",
            }:
                self._send_json({"error": "not found", "ok": False}, status=HTTPStatus.NOT_FOUND)
                return
            try:
                payload = self._read_json()
                if self.path == "/api/review-actions/set":
                    result = set_review_action_status_from_payload(payload, allowed_roots=search_dirs)
                elif self.path == "/api/handoff-pack/write":
                    result = write_handoff_pack_from_payload(payload, allowed_roots=search_dirs)
                else:
                    result = compose_evidence_from_payload(payload, allowed_roots=search_dirs)
            except ValueError as exc:
                self._send_json({"error": str(exc), "ok": False}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(result)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _read_json(self) -> dict[str, Any]:
            content_length = int(self.headers.get("Content-Length") or "0")
            if content_length <= 0:
                raise ValueError("request body is required")
            try:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            return payload

        def _send_json(self, payload: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return DashboardRequestHandler


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _allowed_state_path(raw_path: str, allowed_roots: list[Path]) -> Path:
    if not raw_path.strip():
        raise ValueError("state_path is required")
    roots = [root.resolve() for root in allowed_roots]
    raw = Path(raw_path)
    candidates = [raw.resolve()] if raw.is_absolute() else [(root / raw).resolve() for root in roots]
    for candidate in candidates:
        if any(_is_relative_to(candidate, root) for root in roots):
            return candidate
    raise ValueError("state_path is outside the served dashboard directories")


def _allowed_path(raw_path: str, allowed_roots: list[Path], *, label: str) -> Path:
    if not raw_path.strip():
        raise ValueError(f"{label} is required")
    roots = [root.resolve() for root in allowed_roots]
    raw = Path(raw_path)
    candidates = [raw.resolve()] if raw.is_absolute() else [(root / raw).resolve() for root in roots]
    for candidate in candidates:
        if any(_is_relative_to(candidate, root) for root in roots):
            return candidate
    raise ValueError(f"{label} is outside the served dashboard directories")


def _allowed_evidence_path(raw_path: str, state_path: Path, allowed_roots: list[Path]) -> Path:
    if not raw_path.strip():
        raise ValueError("evidence_url is required")
    if "://" in raw_path:
        raise ValueError("evidence composer only writes local evidence files")
    roots = [root.resolve() for root in allowed_roots]
    raw = Path(raw_path)
    candidates = [raw.resolve()] if raw.is_absolute() else [(state_path.parent / raw).resolve()]
    if not raw.is_absolute():
        candidates.extend((root / raw).resolve() for root in roots)
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if any(_is_relative_to(candidate, root) for root in roots):
            return candidate
    raise ValueError("evidence_url is outside the served dashboard directories")


def _compose_evidence_markdown(
    *,
    stock_id: str,
    action_id: str,
    status: str,
    note: str,
    reviewer: str,
    evidence_summary: str,
) -> str:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return "\n".join(
        [
            f"# Evidence: {stock_id} / {action_id}",
            "",
            f"- Reviewer: {reviewer}",
            f"- Status: {status}",
            f"- Generated at: {generated_at}",
            "",
            "## Review Note",
            note,
            "",
            "## Evidence Summary",
            evidence_summary,
            "",
            "## Non-Investment-Advice Notice",
            NON_ADVICE_NOTICE,
            "",
        ]
    )


def _default_evidence_url(stock_id: str, action_id: str) -> str:
    return f"evidence/{_safe_slug(stock_id)}-{_safe_slug(action_id)}.md"


def _safe_slug(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_" else "-" for char in value.strip())
    return cleaned.strip("-") or "evidence"


def _payload_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _state_report_for_path(state_path: Path) -> dict[str, Any]:
    research_summary = state_path.with_name("research_summary.json")
    if not research_summary.exists():
        return {"by_status": {}, "last_updated": "-", "stale_count": 0}
    try:
        payload = json.loads(research_summary.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"by_status": {}, "last_updated": "-", "stale_count": 0}
    queue = payload.get("review_action_queue", []) if isinstance(payload, dict) else []
    state, warning = load_review_action_state(state_path)
    if warning:
        return {"by_status": {}, "last_updated": "-", "stale_count": 0}
    report = build_review_action_state_report(queue if isinstance(queue, list) else [], state)
    gate = (
        build_handoff_quality_gate(payload, state, evidence_base_dir=research_summary.parent)
        if isinstance(payload, dict)
        else {}
    )
    report["evidence_missing_count"] = gate.get("evidence_missing_count", 0)
    report["invalid_evidence_count"] = gate.get("invalid_evidence_count", 0)
    report["handoff_status"] = gate.get("status", "blocked")
    report["ready"] = bool(gate.get("ready"))
    report["blocker_count"] = gate.get("blocker_count", 0)
    report["open_count"] = gate.get("open_count", 0)
    report["next_step"] = gate.get("next_step", "")
    return report


def _load_pack_summary(summary_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("could not read generated handoff pack summary") from exc
    if not isinstance(payload, dict):
        raise ValueError("generated handoff pack summary must be a JSON object")
    return payload


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
