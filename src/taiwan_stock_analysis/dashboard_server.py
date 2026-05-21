from __future__ import annotations

import json
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from taiwan_stock_analysis.dashboard import discover_dashboard_items, render_dashboard_html
from taiwan_stock_analysis.handoff import build_handoff_quality_gate
from taiwan_stock_analysis.review_action_state import (
    build_review_action_state_report,
    load_review_action_state,
    set_review_action_state,
)

DashboardOpener = Callable[[str], object]


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
        "evidence_url": evidence_url.strip(),
        "state_path": str(output_path),
        "status": status,
        "stale_count": report.get("stale_count", 0),
        "stock_id": stock_id,
        "updated_at": report.get("last_updated", "-"),
    }


def serve_dashboard(
    search_dirs: list[Path],
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
    opener: DashboardOpener | None = None,
) -> str:
    roots = [directory.resolve() for directory in search_dirs]
    handler = _build_handler(roots)
    server = ThreadingHTTPServer((host, port), handler)
    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}/"
    if open_browser:
        (opener or webbrowser.open)(url)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return url


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
            if self.path != "/api/review-actions/set":
                self._send_json({"error": "not found", "ok": False}, status=HTTPStatus.NOT_FOUND)
                return
            try:
                payload = self._read_json()
                result = set_review_action_status_from_payload(payload, allowed_roots=search_dirs)
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
    return report


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
