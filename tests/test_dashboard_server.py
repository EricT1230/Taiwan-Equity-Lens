import json
import threading
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

from taiwan_stock_analysis.dashboard import discover_dashboard_items, render_dashboard_html
from taiwan_stock_analysis.dashboard_server import (
    create_dashboard_server,
    set_review_action_status_from_payload,
    write_handoff_pack_from_payload,
)


class DashboardServerTests(unittest.TestCase):
    def test_sector_evidence_board_done_button_payload_updates_state(self):
        root = Path(".tmp-cli-test/dashboard-server-sector-evidence")
        state_path = _write_sector_evidence_fixture(root)

        html = render_dashboard_html(discover_dashboard_items([root.resolve()]), action_api_enabled=True)
        button = _find_button_by_text(html, "補證並標記完成")

        result = set_review_action_status_from_payload(
            {
                "state_path": button["data-state-path"],
                "stock_id": button["data-stock-id"],
                "action_id": button["data-action-id"],
                "status": button["data-status-value"],
                "note": "checked source filing",
                "reviewer": "source-audit-lead",
                "evidence_url": "evidence/2330-source.md",
            },
            allowed_roots=[root.resolve()],
        )

        self.assertTrue(result["ok"])
        self.assertEqual("done", result["status"])
        self.assertEqual(0, result["evidence_missing_count"])
        self.assertEqual(0, result["invalid_evidence_count"])
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        action = payload["actions"]["2330:source-audit-manual-review"]
        self.assertEqual("done", action["status"])
        self.assertEqual("checked source filing", action["note"])
        self.assertEqual("source-audit-lead", action["reviewer"])
        self.assertEqual("evidence/2330-source.md", action["evidence_url"])

        updated_html = render_dashboard_html(discover_dashboard_items([root.resolve()]), action_api_enabled=True)
        self.assertIn('data-industry-evidence-status="ready"', updated_html)
        self.assertIn("證據可交付", updated_html)

    def test_served_dashboard_http_updates_sector_evidence_state(self):
        root = Path(".tmp-cli-test/dashboard-server-sector-evidence-http")
        state_path = _write_sector_evidence_fixture(root)
        server, url = create_dashboard_server([root.resolve()], port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            html = _http_get_text(url)
            self.assertIn('data-industry-evidence-row="true"', html)
            button = _find_button_by_text(html, "補證並標記完成")

            result = _http_post_json(
                f"{url}api/review-actions/set",
                {
                    "state_path": button["data-state-path"],
                    "stock_id": button["data-stock-id"],
                    "action_id": button["data-action-id"],
                    "status": button["data-status-value"],
                    "note": "checked source filing",
                    "reviewer": "source-audit-lead",
                    "evidence_url": "evidence/2330-source.md",
                },
            )

            self.assertTrue(result["ok"])
            self.assertEqual("done", result["status"])
            self.assertEqual(0, result["evidence_missing_count"])
            self.assertEqual(0, result["invalid_evidence_count"])
            action = json.loads(state_path.read_text(encoding="utf-8"))["actions"][
                "2330:source-audit-manual-review"
            ]
            self.assertEqual("done", action["status"])
            self.assertEqual("checked source filing", action["note"])
            self.assertEqual("source-audit-lead", action["reviewer"])
            self.assertEqual("evidence/2330-source.md", action["evidence_url"])

            updated_html = _http_get_text(url)
            self.assertIn('data-industry-evidence-status="ready"', updated_html)
            self.assertIn("證據可交付", updated_html)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_set_review_action_status_from_payload_writes_state(self):
        root = Path(".tmp-cli-test/dashboard-server-api")
        root.mkdir(parents=True, exist_ok=True)
        state_path = root / "review_action_state.json"
        (root / "research_summary.json").write_text(
            json.dumps(
                {
                    "review_action_queue": [
                        {
                            "stock_id": "2330",
                            "priority": "high",
                            "actions": [
                                {"id": "source-audit-manual-review", "status": "open"},
                                {"id": "reliability-warning", "status": "open"},
                            ],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        result = set_review_action_status_from_payload(
            {
                "state_path": "review_action_state.json",
                "stock_id": "2330",
                "action_id": "source-audit-manual-review",
                "status": "done",
                "note": "checked source filing",
                "reviewer": "source-audit-lead",
                "evidence_url": "evidence/2330-source.md",
            },
            allowed_roots=[root],
        )

        self.assertTrue(result["ok"])
        self.assertEqual("done", result["status"])
        self.assertEqual({"open": 1, "done": 1, "deferred": 0, "ignored": 0}, result["by_status"])
        self.assertEqual("checked source filing", result["note"])
        self.assertEqual("source-audit-lead", result["reviewer"])
        self.assertEqual("evidence/2330-source.md", result["evidence_url"])
        self.assertEqual(0, result["evidence_missing_count"])
        self.assertEqual(1, result["invalid_evidence_count"])
        self.assertEqual(0, result["stale_count"])
        self.assertNotEqual("-", result["last_updated"])
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        action = payload["actions"]["2330:source-audit-manual-review"]
        self.assertEqual("2330", action["stock_id"])
        self.assertEqual("source-audit-manual-review", action["action_id"])
        self.assertEqual("done", action["status"])
        self.assertEqual("checked source filing", action["note"])
        self.assertEqual("source-audit-lead", action["reviewer"])
        self.assertEqual("evidence/2330-source.md", action["evidence_url"])

    def test_set_review_action_status_from_payload_rejects_outside_state_path(self):
        root = Path(".tmp-cli-test/dashboard-server-api-safe")
        root.mkdir(parents=True, exist_ok=True)

        with self.assertRaisesRegex(ValueError, "outside the served dashboard directories"):
            set_review_action_status_from_payload(
                {
                    "state_path": "../outside.json",
                    "stock_id": "2330",
                    "action_id": "source-audit-manual-review",
                    "status": "done",
                },
                allowed_roots=[root],
            )

    def test_set_review_action_status_from_payload_rejects_invalid_status(self):
        root = Path(".tmp-cli-test/dashboard-server-api-invalid")
        root.mkdir(parents=True, exist_ok=True)

        with self.assertRaisesRegex(ValueError, "invalid review action status"):
            set_review_action_status_from_payload(
                {
                    "state_path": "review_action_state.json",
                    "stock_id": "2330",
                    "action_id": "source-audit-manual-review",
                    "status": "bad",
                },
                allowed_roots=[root],
            )

    def test_write_handoff_pack_from_payload_writes_outputs(self):
        root = Path(".tmp-cli-test/dashboard-server-handoff-pack")
        root.mkdir(parents=True, exist_ok=True)
        (root / "evidence").mkdir(exist_ok=True)
        (root / "evidence" / "2330-reliability.md").write_text("checked", encoding="utf-8")
        (root / "research_summary.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "stock_id": "2330",
                            "company_name": "TSMC",
                            "priority": "high",
                            "research_state": "watching",
                            "thesis": "Leading foundry scale",
                            "follow_up_questions": "Are assumptions current?",
                            "workflow_status": "ok",
                            "reliability_status": "warning",
                            "source_audit_status": "fresh",
                            "attention_reasons": ["data reliability is warning"],
                        }
                    ],
                    "review_action_queue": [
                        {
                            "stock_id": "2330",
                            "company_name": "TSMC",
                            "priority": "high",
                            "actions": [
                                {
                                    "id": "reliability-warning",
                                    "category": "reliability",
                                    "severity": "warning",
                                    "message": "Inspect data reliability warning before handoff.",
                                    "status": "open",
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (root / "review_action_state.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "actions": {
                        "2330:reliability-warning": {
                            "stock_id": "2330",
                            "action_id": "reliability-warning",
                            "status": "done",
                            "note": "checked reliability warning",
                            "reviewer": "handoff-lead",
                            "evidence_url": "evidence/2330-reliability.md",
                            "updated_at": "2026-05-20T01:00:00Z",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        result = write_handoff_pack_from_payload(
            {
                "research_summary_path": "research_summary.json",
                "state_path": "review_action_state.json",
                "output_dir": "handoff-pack",
            },
            allowed_roots=[root],
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["ready"])
        self.assertEqual("ready", result["gate_status"])
        self.assertEqual(0, result["evidence_missing_count"])
        self.assertTrue((root / "handoff-pack" / "handoff-pack.md").exists())
        self.assertTrue((root / "handoff-pack" / "handoff-pack.html").exists())
        self.assertEqual(str(root.resolve() / "handoff-pack" / "handoff_pack_summary.json"), result["summary_path"])

    def test_write_handoff_pack_from_payload_rejects_outside_output_dir(self):
        root = Path(".tmp-cli-test/dashboard-server-handoff-pack-safe")
        root.mkdir(parents=True, exist_ok=True)

        with self.assertRaisesRegex(ValueError, "outside the served dashboard directories"):
            write_handoff_pack_from_payload(
                {
                    "research_summary_path": "research_summary.json",
                    "output_dir": "../outside-pack",
                },
                allowed_roots=[root],
            )


def _write_sector_evidence_fixture(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "evidence").mkdir(exist_ok=True)
    (root / "evidence" / "2330-source.md").write_text("checked source audit", encoding="utf-8")
    state_path = root / "review_action_state.json"
    (root / "research_summary.json").write_text(
        json.dumps(
            {
                "review_action_queue": [
                    {
                        "stock_id": "2330",
                        "company_name": "TSMC",
                        "priority": "high",
                        "actions": [
                            {
                                "id": "source-audit-manual-review",
                                "category": "source_audit",
                                "severity": "manual_review",
                                "message": "Review source audit before handoff.",
                                "status": "open",
                            }
                        ],
                    }
                ],
                "items": [
                    {
                        "stock_id": "2330",
                        "company_name": "TSMC",
                        "category": "Semiconductor",
                        "priority": "high",
                        "research_state": "watching",
                        "workflow_status": "ok",
                        "reliability_status": "ok",
                        "source_audit_status": "manual_review",
                        "attention_reasons": ["source audit requires handoff evidence"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return state_path


class _ButtonTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.buttons: list[tuple[dict[str, str], str]] = []
        self._attrs: dict[str, str] | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "button":
            self._attrs = {key: value or "" for key, value in attrs}
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._attrs is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "button" and self._attrs is not None:
            self.buttons.append((self._attrs, "".join(self._text).strip()))
            self._attrs = None
            self._text = []


def _find_button_by_text(html: str, text: str) -> dict[str, str]:
    parser = _ButtonTextParser()
    parser.feed(html)
    for attrs, button_text in parser.buttons:
        if button_text == text:
            return attrs
    raise AssertionError(f"button not found: {text}")


def _http_get_text(url: str) -> str:
    with urlopen(url, timeout=5) as response:
        return response.read().decode("utf-8")


def _http_post_json(url: str, payload: dict[str, str]) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=5) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, dict):
        raise AssertionError("JSON response must be an object")
    return result


if __name__ == "__main__":
    unittest.main()
