import unittest

from taiwan_stock_analysis.handoff import NON_ADVICE_NOTICE, build_handoff_quality_gate


class HandoffGateTests(unittest.TestCase):
    def test_handoff_gate_blocks_open_review_actions(self):
        summary = _summary_with_reliability_warning()

        gate = build_handoff_quality_gate(summary)

        self.assertFalse(gate["ready"])
        self.assertEqual("blocked", gate["status"])
        self.assertEqual(1, gate["open_count"])
        self.assertEqual(0, gate["missing_gate_action_count"])
        self.assertEqual("reliability-warning", gate["top_blockers"][0]["action_id"])
        self.assertEqual("資料可信度專家", gate["top_blockers"][0]["expert_label"])
        self.assertEqual(NON_ADVICE_NOTICE, gate["non_advice_notice"])

    def test_handoff_gate_passes_when_required_action_is_handled(self):
        summary = _summary_with_reliability_warning()
        state = {
            "version": 1,
            "actions": {
                "2330:reliability-warning": {
                    "stock_id": "2330",
                    "action_id": "reliability-warning",
                    "status": "done",
                    "updated_at": "2026-05-20T01:00:00Z",
                }
            },
        }

        gate = build_handoff_quality_gate(summary, state)

        self.assertTrue(gate["ready"])
        self.assertEqual("ready", gate["status"])
        self.assertEqual(0, gate["open_count"])
        self.assertEqual(0, gate["blocker_count"])
        self.assertIn("handoff gate ready", gate["messages"])

    def test_handoff_gate_catches_missing_required_review_action(self):
        summary = _summary_with_reliability_warning()
        summary["review_action_queue"] = []

        gate = build_handoff_quality_gate(summary)

        self.assertFalse(gate["ready"])
        self.assertEqual(0, gate["open_count"])
        self.assertEqual(1, gate["missing_gate_action_count"])
        self.assertEqual("missing_gate_action", gate["top_blockers"][0]["kind"])
        self.assertIn("review-action queue 沒有對應 gate", gate["top_blockers"][0]["message"])

    def test_handoff_gate_blocks_stale_state_even_without_open_actions(self):
        summary = {
            "items": [{"stock_id": "2330", "priority": "low", "research_state": "watching"}],
            "review_action_queue": [],
        }
        state = {
            "version": 1,
            "actions": {
                "2330:old-action": {
                    "stock_id": "2330",
                    "action_id": "old-action",
                    "status": "done",
                    "updated_at": "2026-05-20T01:00:00Z",
                }
            },
        }

        gate = build_handoff_quality_gate(summary, state)

        self.assertFalse(gate["ready"])
        self.assertEqual(1, gate["stale_state_count"])
        self.assertEqual("stale_state", gate["top_blockers"][0]["kind"])
        self.assertIn("prune-stale", gate["top_blockers"][0]["next_step"])


def _summary_with_reliability_warning():
    return {
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
