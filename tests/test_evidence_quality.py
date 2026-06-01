import unittest
from pathlib import Path

from taiwan_stock_analysis.evidence_quality import assess_evidence_quality
from taiwan_stock_analysis.handoff import NON_ADVICE_NOTICE


class EvidenceQualityTests(unittest.TestCase):
    def test_assess_evidence_quality_accepts_specific_review_evidence(self):
        evidence_path = Path(".tmp-cli-test/evidence-quality/2330-source.md")
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        content = "\n".join(
            [
                "# Evidence: 2330 / source-audit-manual-review",
                "Reviewer: source-audit-lead",
                "The reviewer checked source freshness against the fixture note and marked the manual review complete.",
                NON_ADVICE_NOTICE,
            ]
        )
        evidence_path.write_text(content, encoding="utf-8")

        result = assess_evidence_quality(
            note="Checked fixture source freshness, source mode, and manual-review reason before handoff.",
            reviewer="source-audit-lead",
            evidence_summary="The fixture source remains acceptable for this demo handoff because the manual source-audit reason was inspected and documented.",
            evidence_path=evidence_path,
            evidence_content=content,
        )

        self.assertEqual("handoff_ready", result["status"])
        self.assertTrue(result["ready"])
        self.assertEqual(0, len(result["issues"]))
        self.assertEqual("Reviewer confidence looks ready for handoff.", result["next_step"])

    def test_assess_evidence_quality_flags_default_stub_inputs(self):
        result = assess_evidence_quality(
            note="Reviewed handoff blocker: Review source audit before handoff.",
            reviewer="handoff-reviewer",
            evidence_summary="Review source audit before handoff.",
            evidence_content="stub without notice",
        )

        self.assertEqual("draft", result["status"])
        self.assertFalse(result["ready"])
        issue_ids = {issue["id"] for issue in result["issues"]}
        self.assertIn("reviewer_named", issue_ids)
        self.assertIn("note_specific", issue_ids)
        self.assertIn("summary_specific", issue_ids)
        self.assertIn("non_advice_notice", issue_ids)
        self.assertIn("Finish the missing evidence file or required notice", result["next_step"])


if __name__ == "__main__":
    unittest.main()
