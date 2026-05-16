import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from taiwan_stock_analysis.review_action_state import (
    apply_review_action_state,
    backup_review_action_state,
    build_review_action_state_report,
    current_review_action_keys,
    list_review_action_state_backups,
    load_review_action_state,
    prune_stale_review_action_state,
    review_action_key,
    review_action_rows,
    restore_review_action_state,
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

    def test_backup_review_action_state_preserves_original_bytes(self):
        path = Path(".tmp-cli-test/review-action-state-backup.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        for backup in path.parent.glob(f"{path.name}.bak-*"):
            backup.unlink()
        original = b'{"actions":{"2330:workflow-error":{"status":"done"}}}\r\n'
        path.write_bytes(original)

        backup_path = backup_review_action_state(
            path,
            timestamp=datetime(2026, 5, 16, 17, 30, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(backup_path, Path(".tmp-cli-test/review-action-state-backup.json.bak-20260516T173000Z"))
        self.assertEqual(backup_path.read_bytes(), original)

    def test_backup_review_action_state_returns_none_when_missing(self):
        path = Path(".tmp-cli-test/review-action-state-backup-missing.json")
        if path.exists():
            path.unlink()

        self.assertIsNone(
            backup_review_action_state(
                path,
                timestamp=datetime(2026, 5, 16, 17, 30, 0, tzinfo=timezone.utc),
            )
        )

    def test_backup_review_action_state_avoids_overwriting_existing_backup(self):
        path = Path(".tmp-cli-test/review-action-state-backup-collision.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        for backup in path.parent.glob(f"{path.name}.bak-*"):
            backup.unlink()
        path.write_text("current", encoding="utf-8")
        existing = Path(".tmp-cli-test/review-action-state-backup-collision.json.bak-20260516T173000Z")
        existing.write_text("existing", encoding="utf-8")

        backup_path = backup_review_action_state(
            path,
            timestamp=datetime(2026, 5, 16, 17, 30, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(backup_path, Path(".tmp-cli-test/review-action-state-backup-collision.json.bak-20260516T173000Z.1"))
        self.assertEqual(existing.read_text(encoding="utf-8"), "existing")
        self.assertEqual(backup_path.read_text(encoding="utf-8"), "current")

    def test_restore_review_action_state_preserves_backup_bytes(self):
        path = Path(".tmp-cli-test/review-action-state-restore.json")
        backup_path = Path(".tmp-cli-test/review-action-state-restore.json.bak-source")
        path.parent.mkdir(parents=True, exist_ok=True)
        for backup in path.parent.glob(f"{path.name}.bak-*"):
            backup.unlink()
        path.write_text(
            json.dumps(
                {
                    "actions": {
                        "2330:workflow-error": {
                            "stock_id": "2330",
                            "action_id": "workflow-error",
                            "status": "done",
                            "note": "current",
                            "updated_at": "2026-05-15T09:00:00Z",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        original_backup = (
            b'{\r\n'
            b'  "actions": {\r\n'
            b'    "2330:workflow-error": {\r\n'
            b'      "stock_id": "2330",\r\n'
            b'      "action_id": "workflow-error",\r\n'
            b'      "status": "open",\r\n'
            b'      "note": "backup",\r\n'
            b'      "updated_at": "2026-05-15T08:00:00Z"\r\n'
            b'    }\r\n'
            b'  }\r\n'
            b'}\r\n'
        )
        backup_path.write_bytes(original_backup)

        restored_path, current_backup_path = restore_review_action_state(path, backup_path)

        self.assertEqual(restored_path, path)
        self.assertIsNotNone(current_backup_path)
        self.assertEqual(path.read_bytes(), original_backup)

    def test_restore_review_action_state_missing_target_creates_no_current_backup(self):
        path = Path(".tmp-cli-test/review-action-state-restore-missing-target.json")
        backup_path = Path(".tmp-cli-test/review-action-state-restore-missing-target.json.bak-source")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        for backup in path.parent.glob(f"{path.name}.bak-*"):
            backup.unlink()
        backup_path.write_text(
            json.dumps(
                {
                    "actions": {
                        "2330:workflow-error": {
                            "stock_id": "2330",
                            "action_id": "workflow-error",
                            "status": "open",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        restored_path, current_backup_path = restore_review_action_state(path, backup_path)

        self.assertEqual(restored_path, path)
        self.assertIsNone(current_backup_path)
        self.assertEqual(path.read_bytes(), backup_path.read_bytes())
        self.assertEqual([backup for backup in path.parent.glob(f"{path.name}.bak-*") if backup != backup_path], [])

    def test_restore_review_action_state_backs_up_current_before_restore(self):
        path = Path(".tmp-cli-test/review-action-state-restore-current-backup.json")
        backup_path = Path(".tmp-cli-test/review-action-state-restore-current-backup.json.bak-source")
        path.parent.mkdir(parents=True, exist_ok=True)
        for backup in path.parent.glob(f"{path.name}.bak-*"):
            backup.unlink()
        current_bytes = b'{"actions":{"2330:workflow-error":{"stock_id":"2330","action_id":"workflow-error","status":"done"}}}\n'
        restore_bytes = b'{"actions":{"2330:workflow-error":{"stock_id":"2330","action_id":"workflow-error","status":"open"}}}\n'
        path.write_bytes(current_bytes)
        backup_path.write_bytes(restore_bytes)

        _restored_path, current_backup_path = restore_review_action_state(path, backup_path)

        self.assertIsNotNone(current_backup_path)
        self.assertEqual(current_backup_path.read_bytes(), current_bytes)
        self.assertEqual(path.read_bytes(), restore_bytes)

    def test_restore_review_action_state_rejects_missing_backup(self):
        path = Path(".tmp-cli-test/review-action-state-restore-missing-backup.json")
        backup_path = Path(".tmp-cli-test/review-action-state-restore-missing-backup.json.bak-source")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("current", encoding="utf-8")
        if backup_path.exists():
            backup_path.unlink()

        with self.assertRaisesRegex(ValueError, "backup review action state does not exist"):
            restore_review_action_state(path, backup_path)

        self.assertEqual(path.read_text(encoding="utf-8"), "current")

    def test_restore_review_action_state_rejects_invalid_backup(self):
        path = Path(".tmp-cli-test/review-action-state-restore-invalid-backup.json")
        backup_path = Path(".tmp-cli-test/review-action-state-restore-invalid-backup.json.bak-source")
        path.parent.mkdir(parents=True, exist_ok=True)
        current_bytes = b'{"actions":{"2330:workflow-error":{"stock_id":"2330","action_id":"workflow-error","status":"done"}}}\n'
        path.write_bytes(current_bytes)
        backup_path.write_text("{", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Could not read backup review action state"):
            restore_review_action_state(path, backup_path)

        self.assertEqual(path.read_bytes(), current_bytes)

    def test_restore_review_action_state_rejects_invalid_current_state(self):
        path = Path(".tmp-cli-test/review-action-state-restore-invalid-current.json")
        backup_path = Path(".tmp-cli-test/review-action-state-restore-invalid-current.json.bak-source")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{", encoding="utf-8")
        backup_path.write_text(
            json.dumps(
                {
                    "actions": {
                        "2330:workflow-error": {
                            "stock_id": "2330",
                            "action_id": "workflow-error",
                            "status": "open",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "Could not read current review action state"):
            restore_review_action_state(path, backup_path)

        self.assertEqual(path.read_text(encoding="utf-8"), "{")

    def test_list_review_action_state_backups_sorts_newest_first_and_ignores_unrelated(self):
        root = Path(".tmp-cli-test/review-action-state-backups-list")
        root.mkdir(parents=True, exist_ok=True)
        path = root / "review_action_state.json"
        for item in root.glob("*"):
            if item.is_file():
                item.unlink()
        older = root / "review_action_state.json.bak-20260516T173000Z"
        newer = root / "review_action_state.json.bak-20260516T180000Z"
        unrelated = root / "other_state.json.bak-20260516T190000Z"
        older.write_text("old", encoding="utf-8")
        newer.write_text("newer", encoding="utf-8")
        unrelated.write_text("unrelated", encoding="utf-8")

        rows = list_review_action_state_backups(path)

        self.assertEqual(
            rows,
            [
                {
                    "created_at": "2026-05-16T18:00:00Z",
                    "size": 5,
                    "path": str(newer),
                },
                {
                    "created_at": "2026-05-16T17:30:00Z",
                    "size": 3,
                    "path": str(older),
                },
            ],
        )

    def test_list_review_action_state_backups_handles_collisions_and_unknown_timestamps(self):
        root = Path(".tmp-cli-test/review-action-state-backups-collisions")
        root.mkdir(parents=True, exist_ok=True)
        path = root / "review_action_state.json"
        for item in root.glob("*"):
            if item.is_file():
                item.unlink()
        base = root / "review_action_state.json.bak-20260516T180000Z"
        collision = root / "review_action_state.json.bak-20260516T180000Z.1"
        unknown_b = root / "review_action_state.json.bak-source-b"
        unknown_a = root / "review_action_state.json.bak-source-a"
        base.write_text("base", encoding="utf-8")
        collision.write_text("collision", encoding="utf-8")
        unknown_b.write_text("unknown-b", encoding="utf-8")
        unknown_a.write_text("unknown-a", encoding="utf-8")

        rows = list_review_action_state_backups(path)

        self.assertEqual([row["path"] for row in rows], [str(collision), str(base), str(unknown_b), str(unknown_a)])
        self.assertEqual(rows[0]["created_at"], "2026-05-16T18:00:00Z")
        self.assertEqual(rows[1]["created_at"], "2026-05-16T18:00:00Z")
        self.assertEqual(rows[2]["created_at"], "unknown")
        self.assertEqual(rows[3]["created_at"], "unknown")

    def test_list_review_action_state_backups_returns_empty_for_missing_parent(self):
        path = Path(".tmp-cli-test/missing-backup-parent/review_action_state.json")
        if path.parent.exists():
            for item in path.parent.glob("*"):
                if item.is_file():
                    item.unlink()
            path.parent.rmdir()

        self.assertEqual(list_review_action_state_backups(path), [])

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
