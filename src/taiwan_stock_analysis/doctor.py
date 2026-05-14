from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
PROJECT_VERSION_RE = re.compile(r'^\s*version\s*=\s*"([^"]+)"\s*$', re.MULTILINE)
EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "#")


@dataclass(frozen=True)
class DoctorResult:
    ok: bool
    messages: list[str]
    failures: list[str]


def check_release_readiness(root: Path, expected_version: str | None = None) -> DoctorResult:
    root = root.resolve()
    failures: list[str] = []
    messages: list[str] = []
    version = expected_version or _read_project_version(root / "pyproject.toml", failures)
    if not version:
        return DoctorResult(ok=False, messages=messages, failures=failures)

    release_note = Path("docs/releases") / f"v{version}.md"
    _check_contains(root / "pyproject.toml", f'version = "{version}"', f"pyproject version expected {version}", failures)
    _check_contains(root / "README.md", f"version-v{version}-blue.svg", f"README badge expected v{version}", failures)
    _check_contains(
        root / "README.md",
        release_note.as_posix(),
        f"README missing release note link for v{version}",
        failures,
    )
    _check_contains(root / "CHANGELOG.md", f"## v{version} - ", f"CHANGELOG missing section for v{version}", failures)
    if not (root / release_note).exists():
        failures.append(f"Missing release note: {release_note.as_posix()}")

    docs_to_check = [
        Path("README.md"),
        Path("CHANGELOG.md"),
        Path("docs/usage-workflow.md"),
        release_note,
    ]
    failures.extend(_broken_markdown_links(root, docs_to_check))

    messages.append(f"release metadata version {version}")
    messages.append(f"python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    return DoctorResult(ok=not failures, messages=messages, failures=failures)


def find_local_markdown_links(source_path: Path, text: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for match in MARKDOWN_LINK_RE.finditer(text):
        target = match.group(1).strip()
        if target.startswith(EXTERNAL_PREFIXES):
            continue
        target = target.split("#", 1)[0]
        if target:
            links.append((source_path.as_posix(), target))
    return links


def format_doctor_result(result: DoctorResult) -> str:
    if result.ok:
        lines = ["Release readiness OK:"]
        lines.extend(f"- {message}" for message in result.messages)
        return "\n".join(lines)
    lines = ["Release readiness failed:"]
    lines.extend(f"- {failure}" for failure in result.failures)
    return "\n".join(lines)


def _read_project_version(path: Path, failures: list[str]) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        failures.append("Missing pyproject.toml")
        return ""
    match = PROJECT_VERSION_RE.search(text)
    if not match:
        failures.append("pyproject.toml missing project.version")
        return ""
    return match.group(1)


def _check_contains(path: Path, expected: str, failure: str, failures: list[str]) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        failures.append(f"Missing file: {path.name}")
        return
    if expected not in text:
        failures.append(failure)


def _broken_markdown_links(root: Path, docs_to_check: Iterable[Path]) -> list[str]:
    failures: list[str] = []
    for relative_path in docs_to_check:
        path = root / relative_path
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for source, target in find_local_markdown_links(relative_path, text):
            resolved = (root / relative_path.parent / target).resolve()
            if not _is_relative_to(resolved, root) or not resolved.exists():
                failures.append(f"Broken link in {source}: {target}")
    return failures


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
