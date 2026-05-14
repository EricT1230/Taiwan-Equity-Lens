import unittest
from pathlib import Path

from taiwan_stock_analysis.doctor import check_release_readiness, find_local_markdown_links


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
