import json
import unittest
from pathlib import Path

from taiwan_stock_analysis.handoff_pack import (
    build_handoff_pack_context,
    render_handoff_pack_markdown,
    write_handoff_evidence_pack,
)


class HandoffEvidencePackTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(".tmp-handoff-pack-test")
        self.root.mkdir(exist_ok=True)

    def test_build_handoff_pack_context_marks_invalid_local_evidence(self):
        research_summary = self._write_research_summary()
        self._write_state(evidence_url="evidence/missing.md")

        context = build_handoff_pack_context(research_summary)

        self.assertEqual("blocked", context["gate"]["status"])
        self.assertEqual(1, context["gate"]["invalid_evidence_count"])
        self.assertEqual(1, len(context["evidence_rows"]))
        self.assertIn("invalid:", context["evidence_rows"][0]["evidence_status"])

    def test_write_handoff_evidence_pack_writes_markdown_html_and_summary(self):
        research_summary = self._write_research_summary()
        evidence_path = self.root / "evidence" / "2330-reliability.md"
        evidence_path.parent.mkdir(exist_ok=True)
        evidence_path.write_text("# Reliability evidence\n", encoding="utf-8")
        self._write_state(evidence_url="evidence/2330-reliability.md")
        output_dir = self.root / "handoff-pack"

        summary_path = write_handoff_evidence_pack(research_summary, output_dir)

        self.assertEqual(output_dir / "handoff_pack_summary.json", summary_path)
        self.assertTrue((output_dir / "handoff-pack.md").exists())
        self.assertTrue((output_dir / "handoff-pack.html").exists())
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertTrue(payload["ready"])
        self.assertEqual("ready", payload["gate_status"])
        self.assertEqual(0, payload["invalid_evidence_count"])
        markdown = (output_dir / "handoff-pack.md").read_text(encoding="utf-8")
        self.assertIn("# Handoff Evidence Pack", markdown)
        self.assertIn("## Evidence Ledger", markdown)
        self.assertIn("handoff-lead", markdown)

    def test_render_handoff_pack_markdown_includes_blockers_and_notice(self):
        research_summary = self._write_research_summary(status="open")

        markdown = render_handoff_pack_markdown(build_handoff_pack_context(research_summary))

        self.assertIn("## Gate Summary", markdown)
        self.assertIn("## Top Blockers", markdown)
        self.assertIn("reliability-warning", markdown)
        self.assertIn("## Notice", markdown)

    def _write_research_summary(self, *, status="open"):
        path = self.root / "research_summary.json"
        path.write_text(
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
                                    "status": status,
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return path

    def _write_state(self, *, evidence_url):
        (self.root / "review_action_state.json").write_text(
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
                            "evidence_url": evidence_url,
                            "updated_at": "2026-05-20T01:00:00Z",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

