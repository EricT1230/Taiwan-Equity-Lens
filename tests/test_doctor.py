import json
import unittest
from pathlib import Path

from taiwan_stock_analysis.doctor import (
    check_demo_readiness,
    check_release_readiness,
    find_local_markdown_links,
    format_demo_doctor_result,
)


class DoctorTests(unittest.TestCase):
    def test_check_release_readiness_passes_for_complete_fixture(self):
        root = Path(".tmp-doctor-test/pass")
        write_release_fixture(root, version="0.10.0")

        result = check_release_readiness(root, expected_version="0.10.0")

        self.assertTrue(result.ok)
        self.assertEqual([], result.failures)
        self.assertTrue(any("version 0.10.0" in line for line in result.messages))

    def test_check_release_readiness_reports_version_mismatch(self):
        root = Path(".tmp-doctor-test/mismatch")
        write_release_fixture(root, version="0.10.0", badge_version="0.9.1")

        result = check_release_readiness(root, expected_version="0.10.0")

        self.assertFalse(result.ok)
        self.assertIn("README badge expected v0.10.0", result.failures)

    def test_check_release_readiness_reads_project_version_only(self):
        root = Path(".tmp-doctor-test/project-version-only")
        write_release_fixture(root, version="0.9.1")
        with (root / "pyproject.toml").open("a", encoding="utf-8") as handle:
            handle.write('\n[tool.fake]\nversion = "0.10.0"\n')

        result = check_release_readiness(root, expected_version="0.10.0")

        self.assertFalse(result.ok)
        self.assertIn("pyproject version expected 0.10.0", result.failures)

    def test_check_release_readiness_reports_missing_release_note(self):
        root = Path(".tmp-doctor-test/missing-note")
        write_release_fixture(root, version="0.10.0")
        (root / "docs/releases/v0.10.0.md").unlink()

        result = check_release_readiness(root, expected_version="0.10.0")

        self.assertFalse(result.ok)
        self.assertIn("Missing release note: docs/releases/v0.10.0.md", result.failures)

    def test_check_release_readiness_reports_missing_changelog_section(self):
        root = Path(".tmp-doctor-test/missing-changelog")
        write_release_fixture(root, version="0.10.0", changelog_version="0.9.1")

        result = check_release_readiness(root, expected_version="0.10.0")

        self.assertFalse(result.ok)
        self.assertIn("CHANGELOG missing section for v0.10.0", result.failures)

    def test_check_release_readiness_reports_broken_markdown_link(self):
        root = Path(".tmp-doctor-test/broken-link")
        write_release_fixture(root, version="0.10.0")
        (root / "README.md").write_text("[Missing](docs/missing.md)\n", encoding="utf-8")

        result = check_release_readiness(root, expected_version="0.10.0")

        self.assertFalse(result.ok)
        self.assertIn("Broken link in README.md: docs/missing.md", result.failures)

    def test_find_local_markdown_links_ignores_external_and_anchor_links(self):
        links = find_local_markdown_links(
            Path("README.md"),
            "[Local](docs/usage-workflow.md) [Web](https://example.com) [Anchor](#verify)",
        )

        self.assertEqual([("README.md", "docs/usage-workflow.md")], links)

    def test_check_demo_readiness_passes_for_complete_demo(self):
        output_dir = Path(".tmp-doctor-test/demo-pass")
        write_demo_fixture(output_dir)

        result = check_demo_readiness(output_dir)

        self.assertTrue(result.ok)
        self.assertEqual([], result.failures)
        self.assertIn(f"output directory {output_dir}", result.messages)
        self.assertIn("required files present", result.messages)
        self.assertIn("dashboard includes review-action section", result.messages)

    def test_format_demo_doctor_result_reports_success(self):
        output_dir = Path(".tmp-doctor-test/demo-format-pass")
        write_demo_fixture(output_dir)

        text = format_demo_doctor_result(check_demo_readiness(output_dir))

        self.assertIn("Demo readiness OK:", text)
        self.assertIn("required files present", text)

    def test_check_demo_readiness_reports_missing_required_file(self):
        output_dir = Path(".tmp-doctor-test/demo-missing-dashboard")
        write_demo_fixture(output_dir)
        (output_dir / "dashboard.html").unlink()

        result = check_demo_readiness(output_dir)

        self.assertFalse(result.ok)
        self.assertIn(f"missing {output_dir / 'dashboard.html'}", result.failures)

    def test_check_demo_readiness_reports_invalid_research_json(self):
        output_dir = Path(".tmp-doctor-test/demo-invalid-json")
        write_demo_fixture(output_dir)
        (output_dir / "research_summary.json").write_text("{", encoding="utf-8")

        result = check_demo_readiness(output_dir)

        self.assertFalse(result.ok)
        self.assertTrue(
            any(f"invalid JSON: {output_dir / 'research_summary.json'}" in failure for failure in result.failures)
        )

    def test_check_demo_readiness_reports_missing_review_action_queue(self):
        output_dir = Path(".tmp-doctor-test/demo-missing-queue")
        write_demo_fixture(output_dir)
        (output_dir / "research_summary.json").write_text(json.dumps({"items": []}), encoding="utf-8")

        result = check_demo_readiness(output_dir)

        self.assertFalse(result.ok)
        self.assertIn(
            f"research summary has no review-action queue: {output_dir / 'research_summary.json'}",
            result.failures,
        )

    def test_check_demo_readiness_reports_missing_successful_stock_ids(self):
        output_dir = Path(".tmp-doctor-test/demo-no-successes")
        write_demo_fixture(output_dir)
        (output_dir / "workflow_summary.json").write_text(json.dumps({"successful_stock_ids": []}), encoding="utf-8")

        result = check_demo_readiness(output_dir)

        self.assertFalse(result.ok)
        self.assertIn(
            f"workflow summary has no successful stock ids: {output_dir / 'workflow_summary.json'}",
            result.failures,
        )

    def test_check_demo_readiness_reports_dashboard_without_review_actions(self):
        output_dir = Path(".tmp-doctor-test/demo-dashboard-missing-actions")
        write_demo_fixture(output_dir)
        (output_dir / "dashboard.html").write_text("<html><body>No actions</body></html>", encoding="utf-8")

        result = check_demo_readiness(output_dir)

        self.assertFalse(result.ok)
        self.assertIn(f"dashboard missing review-action section: {output_dir / 'dashboard.html'}", result.failures)

    def test_format_demo_doctor_result_includes_repair_command(self):
        output_dir = Path(".tmp-doctor-test/demo-format-fail")

        text = format_demo_doctor_result(check_demo_readiness(output_dir))

        self.assertIn("Demo readiness failed:", text)
        self.assertIn("Repair:", text)
        self.assertIn(
            f"python -m taiwan_stock_analysis.cli demo quickstart --output-dir {output_dir}",
            text,
        )


def write_release_fixture(
    root: Path,
    *,
    version: str,
    badge_version: str | None = None,
    changelog_version: str | None = None,
) -> None:
    badge = badge_version or version
    changelog = changelog_version or version
    (root / "docs/releases").mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "fixture"\nversion = "{version}"\n',
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        f"[![Version](https://img.shields.io/badge/version-v{badge}-blue.svg)](CHANGELOG.md)\n"
        f"[v{version} release notes](docs/releases/v{version}.md)\n",
        encoding="utf-8",
    )
    (root / "CHANGELOG.md").write_text(f"# Changelog\n\n## v{changelog} - 2026-05-14\n", encoding="utf-8")
    (root / "docs/usage-workflow.md").write_text("# Usage\n", encoding="utf-8")
    (root / f"docs/releases/v{version}.md").write_text(f"# v{version}\n", encoding="utf-8")


def write_demo_fixture(output_dir: Path) -> None:
    (output_dir / "memos").mkdir(parents=True, exist_ok=True)
    (output_dir / "packs").mkdir(parents=True, exist_ok=True)
    (output_dir / "comparison").mkdir(parents=True, exist_ok=True)
    (output_dir / "dashboard.html").write_text(
        '<html><body><div data-review-actions-section="true"></div></body></html>',
        encoding="utf-8",
    )
    (output_dir / "workflow_summary.json").write_text(
        json.dumps({"successful_stock_ids": ["2330"]}),
        encoding="utf-8",
    )
    (output_dir / "research_summary.json").write_text(
        json.dumps({"review_action_queue": [{"stock_id": "2330", "actions": [{"id": "source-audit"}]}]}),
        encoding="utf-8",
    )
    (output_dir / "memos" / "memo_summary.json").write_text("{}", encoding="utf-8")
    (output_dir / "packs" / "pack_summary.json").write_text("{}", encoding="utf-8")
    (output_dir / "comparison" / "comparison.html").write_text("<html></html>", encoding="utf-8")
    (output_dir / "comparison" / "comparison.json").write_text("{}", encoding="utf-8")
    (output_dir / "valuation.csv").write_text("stock_id\n2330\n", encoding="utf-8")
