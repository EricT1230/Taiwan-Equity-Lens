import unittest

from taiwan_stock_analysis.review_actions import (
    build_review_actions,
    build_review_action_summary,
    build_review_action_queue,
)


class ReviewActionTests(unittest.TestCase):
    def test_build_review_actions_from_source_audit_and_reliability(self):
        item = {
            "stock_id": "2330",
            "company_name": "TSMC",
            "priority": "high",
            "research_state": "watching",
            "workflow_status": "ok",
            "reliability_status": "warning",
            "source_audit_status": "manual_review",
            "source_audit_reasons": ["fixture source requires manual review", "offline mode"],
            "attention_reasons": ["data reliability is warning"],
            "thesis": "Leading foundry scale",
            "follow_up_questions": "What drives margin expansion?",
        }

        actions = build_review_actions(item)

        self.assertEqual(
            actions,
            [
                {
                    "id": "source-audit-manual-review",
                    "category": "source_audit",
                    "severity": "manual_review",
                    "message": "Review source audit: fixture source requires manual review; offline mode",
                    "status": "open",
                },
                {
                    "id": "reliability-warning",
                    "category": "reliability",
                    "severity": "warning",
                    "message": "Inspect data reliability warning before handoff.",
                    "status": "open",
                },
            ],
        )

    def test_build_review_actions_from_workflow_failure_and_research_quality(self):
        item = {
            "stock_id": "9999",
            "company_name": "Broken",
            "priority": "high",
            "research_state": "blocked",
            "workflow_status": "error",
            "reliability_status": "error",
            "source_audit_status": "unknown",
            "source_audit_reasons": [],
            "attention_reasons": [
                "workflow failed at batch: fixture missing",
                "valuation output is unavailable or skipped",
            ],
            "thesis": "",
            "follow_up_questions": "",
        }

        actions = build_review_actions(item)

        self.assertEqual(
            [action["id"] for action in actions],
            [
                "workflow-error",
                "reliability-error",
                "source-audit-unknown",
                "valuation-unavailable",
                "research-state-blocked",
                "research-quality-missing-thesis",
                "research-quality-missing-follow-up",
            ],
        )
        self.assertEqual(actions[0]["severity"], "error")
        self.assertIn("workflow failed at batch: fixture missing", actions[0]["message"])

    def test_build_review_actions_dedupes_and_ignores_invalid_values(self):
        item = {
            "stock_id": "2303",
            "priority": "medium",
            "research_state": "watching",
            "workflow_status": "ok",
            "reliability_status": "ok",
            "source_audit_status": "manual_review",
            "source_audit_reasons": ["offline mode", "", {"bad": True}, "offline mode"],
            "attention_reasons": [],
            "thesis": "UMC profile",
            "follow_up_questions": "What utilization is assumed?",
        }

        actions = build_review_actions(item)

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["message"], "Review source audit: offline mode")

    def test_build_review_action_summary_and_queue_are_deterministic(self):
        items = [
            {
                "stock_id": "2303",
                "company_name": "UMC",
                "priority": "medium",
                "review_actions": [
                    {
                        "id": "source-audit-manual-review",
                        "category": "source_audit",
                        "severity": "manual_review",
                        "message": "Review source audit: offline mode",
                        "status": "open",
                    }
                ],
            },
            {
                "stock_id": "2330",
                "company_name": "TSMC",
                "priority": "high",
                "review_actions": [
                    {
                        "id": "workflow-error",
                        "category": "workflow",
                        "severity": "error",
                        "message": "Fix workflow failure.",
                        "status": "open",
                    },
                    {
                        "id": "valuation-unavailable",
                        "category": "valuation",
                        "severity": "warning",
                        "message": "Complete valuation output.",
                        "status": "open",
                    },
                ],
            },
        ]

        summary = build_review_action_summary(items)
        queue = build_review_action_queue(items)

        self.assertEqual(summary["total_open"], 3)
        self.assertEqual(summary["by_category"], {"source_audit": 1, "valuation": 1, "workflow": 1})
        self.assertEqual(summary["by_severity"], {"error": 1, "manual_review": 1, "warning": 1})
        self.assertEqual([entry["stock_id"] for entry in queue], ["2330", "2303"])
        self.assertEqual([action["id"] for action in queue[0]["actions"]], ["workflow-error", "valuation-unavailable"])


if __name__ == "__main__":
    unittest.main()
