import json
import unittest
from pathlib import Path

from taiwan_stock_analysis.review_action_state import (
    apply_review_action_state,
    build_review_action_state_report,
    current_review_action_keys,
    load_review_action_state,
    prune_stale_review_action_state,
    review_action_key,
    review_action_rows,
    set_review_action_state,
    stale_review_action_state_rows,
    summarize_review_action_state,
    write_review_action_state,
)


class ReviewActionStateTests(unittest.TestCase):
    def test_review_action_key_is_stable(self):
        self.assertEqual(review_action_key(" 2330 ", " source-audit-manual-review "), "2330:source-audit-manual-review")

    def test_load_missing_state_returns_empty_state(self):
        state, warning = load_review_action_state(Path(".tmp-cli-test/missing-review-action-state.json"))

        self.assertEqual(state, {"version": 1, "actions": {}})
        self.assertEqual(warning, "")

    def test_load_invalid_json_returns_warning_and_empty_state(self):
        path = Path(".tmp-cli-test/review-action-state-invalid.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{", encoding="utf-8")

        state, warning = load_review_action_state(path)

        self.assertEqual(state, {"version": 1, "actions": {}})
        self.assertIn("Could not read review action state", warning)

    def test_load_state_normalizes_and_ignores_malformed_entries(self):
        path = Path(".tmp-cli-test/review-action-state-normalized.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "version": 99,
                    "actions": {
                        "2330:workflow-error": {"status": "done", "note": "checked"},
                        "2303:bad": {"status": "bad"},
                        "bad": "value",
                    },
                }
            ),
            encoding="utf-8",
        )

        state, warning = load_review_action_state(path)

        self.assertEqual(warning, "")
        self.assertEqual(
            state,
            {
                "version": 1,
                "actions": {
                    "2330:workflow-error": {
                        "stock_id": "2330",
                        "action_id": "workflow-error",
                        "status": "done",
                        "note": "checked",
                        "updated_at": "",
                    }
                },
            },
        )

    def test_write_and_set_state_are_deterministic(self):
        path = Path(".tmp-cli-test/review-action-state-write.json")

        set_review_action_state(
            path,
            "2330",
            "workflow-error",
            "done",
            note="checked",
            updated_at="2026-05-15T09:00:00Z",
        )
        write_review_action_state(
            path,
            {
                "actions": {
                    "2303:source-audit-stale": {
                        "stock_id": "2303",
                        "action_id": "source-audit-stale",
                        "status": "deferred",
                        "note": "",
                        "updated_at": "2026-05-15T09:01:00Z",
                    },
                    "2330:workflow-error": {
                        "stock_id": "2330",
                        "action_id": "workflow-error",
                        "status": "done",
                        "note": "checked",
                        "updated_at": "2026-05-15T09:00:00Z",
                    },
                }
            },
        )

        payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(list(payload["actions"]), ["2303:source-audit-stale", "2330:workflow-error"])
        self.assertEqual(payload["actions"]["2330:workflow-error"]["status"], "done")

    def test_set_state_rejects_invalid_status(self):
        with self.assertRaisesRegex(ValueError, "invalid review action status"):
            set_review_action_state(
                Path(".tmp-cli-test/review-action-state-invalid-status.json"),
                "2330",
                "workflow-error",
                "bad",
            )

    def test_apply_state_adds_status_and_note_without_mutating_input(self):
        queue = [
            {
                "stock_id": "2330",
                "priority": "high",
                "actions": [
                    {
                        "id": "workflow-error",
                        "category": "workflow",
                        "severity": "error",
                        "message": "Fix workflow.",
                        "status": "open",
                    },
                    {
                        "id": "valuation-unavailable",
                        "category": "valuation",
                        "severity": "warning",
                        "message": "Check valuation.",
                        "status": "open",
                    },
                ],
            }
        ]
        state = {
            "version": 1,
            "actions": {
                "2330:workflow-error": {
                    "stock_id": "2330",
                    "action_id": "workflow-error",
                    "status": "done",
                    "note": "checked",
                    "updated_at": "2026-05-15T09:00:00Z",
                }
            },
        }

        overlaid = apply_review_action_state(queue, state)

        self.assertEqual(overlaid[0]["actions"][0]["status"], "done")
        self.assertEqual(overlaid[0]["actions"][0]["note"], "checked")
        self.assertEqual(overlaid[0]["actions"][0]["updated_at"], "2026-05-15T09:00:00Z")
        self.assertEqual(overlaid[0]["actions"][1]["status"], "open")
        self.assertNotIn("note", queue[0]["actions"][0])

    def test_summarize_state_and_flatten_rows(self):
        queue = [
            {
                "stock_id": "2330",
                "priority": "high",
                "actions": [
                    {
                        "id": "workflow-error",
                        "category": "workflow",
                        "severity": "error",
                        "message": "Fix workflow.",
                        "status": "done",
                    },
                    {
                        "id": "valuation-unavailable",
                        "category": "valuation",
                        "severity": "warning",
                        "message": "Check valuation.",
                    },
                ],
            }
        ]

        self.assertEqual(summarize_review_action_state(queue), {"open": 1, "done": 1})
        self.assertEqual(
            review_action_rows(queue),
            [
                {
                    "stock_id": "2330",
                    "priority": "high",
                    "status": "done",
                    "severity": "error",
                    "category": "workflow",
                    "action_id": "workflow-error",
                    "message": "Fix workflow.",
                },
                {
                    "stock_id": "2330",
                    "priority": "high",
                    "status": "open",
                    "severity": "warning",
                    "category": "valuation",
                    "action_id": "valuation-unavailable",
                    "message": "Check valuation.",
                },
            ],
        )

    def test_current_keys_and_stale_state_rows(self):
        queue = [
            {
                "stock_id": "2330",
                "priority": "high",
                "actions": [
                    {
                        "id": "workflow-error",
                        "category": "workflow",
                        "severity": "error",
                        "message": "Fix workflow.",
                        "status": "open",
                    }
                ],
            }
        ]
        state = {
            "version": 1,
            "actions": {
                "2330:workflow-error": {
                    "stock_id": "2330",
                    "action_id": "workflow-error",
                    "status": "done",
                    "note": "checked",
                    "updated_at": "2026-05-15T09:00:00Z",
                },
                "9999:old-action": {
                    "stock_id": "9999",
                    "action_id": "old-action",
                    "status": "ignored",
                    "note": "obsolete",
                    "updated_at": "2026-05-15T10:00:00Z",
                },
            },
        }

        self.assertEqual(current_review_action_keys(queue), {"2330:workflow-error"})
        self.assertEqual(
            stale_review_action_state_rows(queue, state),
            [
                {
                    "stock_id": "9999",
                    "action_id": "old-action",
                    "status": "ignored",
                    "note": "obsolete",
                    "updated_at": "2026-05-15T10:00:00Z",
                }
            ],
        )

    def test_build_review_action_state_report_counts_stale_and_next_open(self):
        queue = [
            {
                "stock_id": "2330",
                "priority": "high",
                "actions": [
                    {
                        "id": "workflow-error",
                        "category": "workflow",
                        "severity": "error",
                        "message": "Fix workflow.",
                        "status": "open",
                    },
                    {
                        "id": "valuation-unavailable",
                        "category": "valuation",
                        "severity": "warning",
                        "message": "Check valuation.",
                        "status": "open",
                    },
                ],
            },
            {
                "stock_id": "2303",
                "priority": "medium",
                "actions": [
                    {
                        "id": "reliability-warning",
                        "category": "reliability",
                        "severity": "warning",
                        "message": "Check reliability.",
                        "status": "open",
                    }
                ],
            },
        ]
        state = {
            "version": 1,
            "actions": {
                "2330:workflow-error": {
                    "stock_id": "2330",
                    "action_id": "workflow-error",
                    "status": "done",
                    "note": "checked",
                    "updated_at": "2026-05-15T09:00:00Z",
                },
                "9999:old-action": {
                    "stock_id": "9999",
                    "action_id": "old-action",
                    "status": "deferred",
                    "note": "old",
                    "updated_at": "2026-05-15T10:00:00Z",
                },
            },
        }

        report = build_review_action_state_report(queue, state, next_open_limit=1)

        self.assertEqual(report["total_actions"], 3)
        self.assertEqual(report["by_status"], {"open": 2, "done": 1, "deferred": 0, "ignored": 0})
        self.assertEqual(report["stale_count"], 1)
        self.assertEqual(report["last_updated"], "2026-05-15T10:00:00Z")
        self.assertEqual(
            report["next_open"],
            [
                {
                    "stock_id": "2330",
                    "priority": "high",
                    "status": "open",
                    "severity": "warning",
                    "category": "valuation",
                    "action_id": "valuation-unavailable",
                    "message": "Check valuation.",
                }
            ],
        )

    def test_build_review_action_state_report_handles_missing_state_and_limit_zero(self):
        queue = [
            {
                "stock_id": "2330",
                "priority": "high",
                "actions": [
                    {
                        "id": "workflow-error",
                        "category": "workflow",
                        "severity": "error",
                        "message": "Fix workflow.",
                        "status": "open",
                    }
                ],
            }
        ]

        report = build_review_action_state_report(queue, None, next_open_limit=0)

        self.assertEqual(report["total_actions"], 1)
        self.assertEqual(report["by_status"], {"open": 1, "done": 0, "deferred": 0, "ignored": 0})
        self.assertEqual(report["stale_count"], 0)
        self.assertEqual(report["last_updated"], "-")
        self.assertEqual(report["next_open"], [])

    def test_build_review_action_state_report_ignores_malformed_state_entries(self):
        queue = [
            {
                "stock_id": "2330",
                "priority": "high",
                "actions": [
                    {
                        "id": "workflow-error",
                        "category": "workflow",
                        "severity": "error",
                        "message": "Fix workflow.",
                    }
                ],
            }
        ]
        state = {
            "version": 1,
            "actions": {
                "2330:workflow-error": {"status": "bad", "updated_at": "2026-05-15T09:00:00Z"},
                "9999:old-action": "not-an-object",
                "2303:missing-status": {"stock_id": "2303", "action_id": "missing-status"},
            },
        }

        report = build_review_action_state_report(queue, state)

        self.assertEqual(report["by_status"], {"open": 1, "done": 0, "deferred": 0, "ignored": 0})
        self.assertEqual(report["stale_state"], [])
        self.assertEqual(report["last_updated"], "-")

    def test_prune_stale_review_action_state_removes_only_stale_entries(self):
        queue = [
            {
                "stock_id": "2330",
                "priority": "high",
                "actions": [
                    {
                        "id": "workflow-error",
                        "category": "workflow",
                        "severity": "error",
                        "message": "Fix workflow.",
                    }
                ],
            }
        ]
        state = {
            "version": 1,
            "actions": {
                "2330:workflow-error": {
                    "stock_id": "2330",
                    "action_id": "workflow-error",
                    "status": "done",
                    "note": "checked",
                    "updated_at": "2026-05-15T09:00:00Z",
                },
                "9999:old-action": {
                    "stock_id": "9999",
                    "action_id": "old-action",
                    "status": "ignored",
                    "note": "obsolete",
                    "updated_at": "2026-05-15T10:00:00Z",
                },
            },
        }

        pruned, stale_rows = prune_stale_review_action_state(queue, state)

        self.assertEqual(
            pruned,
            {
                "version": 1,
                "actions": {
                    "2330:workflow-error": {
                        "stock_id": "2330",
                        "action_id": "workflow-error",
                        "status": "done",
                        "note": "checked",
                        "updated_at": "2026-05-15T09:00:00Z",
                    }
                },
            },
        )
        self.assertEqual(
            stale_rows,
            [
                {
                    "stock_id": "9999",
                    "action_id": "old-action",
                    "status": "ignored",
                    "note": "obsolete",
                    "updated_at": "2026-05-15T10:00:00Z",
                }
            ],
        )

    def test_prune_stale_review_action_state_preserves_state_when_no_stale_entries(self):
        queue = [
            {
                "stock_id": "2330",
                "actions": [{"id": "workflow-error"}],
            }
        ]
        state = {
            "actions": {
                "2330:workflow-error": {
                    "status": "deferred",
                    "note": "later",
                    "updated_at": "2026-05-15T09:00:00Z",
                }
            }
        }

        pruned, stale_rows = prune_stale_review_action_state(queue, state)

        self.assertEqual(
            pruned["actions"]["2330:workflow-error"],
            {
                "stock_id": "2330",
                "action_id": "workflow-error",
                "status": "deferred",
                "note": "later",
                "updated_at": "2026-05-15T09:00:00Z",
            },
        )
        self.assertEqual(stale_rows, [])

    def test_prune_stale_review_action_state_handles_missing_and_malformed_state(self):
        queue = [{"stock_id": "2330", "actions": [{"id": "workflow-error"}]}]
        state = {
            "actions": {
                "2330:workflow-error": {"status": "bad", "updated_at": "2026-05-15T09:00:00Z"},
                "9999:old-action": "not-an-object",
                "2303:missing-status": {"stock_id": "2303", "action_id": "missing-status"},
            }
        }

        self.assertEqual(prune_stale_review_action_state(queue, None), ({"version": 1, "actions": {}}, []))
        self.assertEqual(prune_stale_review_action_state(queue, state), ({"version": 1, "actions": {}}, []))

    def test_prune_stale_review_action_state_does_not_mutate_input(self):
        queue = [{"stock_id": "2330", "actions": [{"id": "workflow-error"}]}]
        state = {
            "actions": {
                "2330:workflow-error": {
                    "stock_id": "2330",
                    "action_id": "workflow-error",
                    "status": "done",
                    "note": "checked",
                    "updated_at": "2026-05-15T09:00:00Z",
                }
            }
        }

        pruned, _stale_rows = prune_stale_review_action_state(queue, state)
        pruned["actions"]["2330:workflow-error"]["note"] = "changed"

        self.assertEqual(state["actions"]["2330:workflow-error"]["note"], "checked")


if __name__ == "__main__":
    unittest.main()
