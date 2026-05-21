import json
import unittest
from pathlib import Path

from taiwan_stock_analysis.dashboard_server import set_review_action_status_from_payload


class DashboardServerTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
