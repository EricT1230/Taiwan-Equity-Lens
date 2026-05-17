from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    tomllib = None  # type: ignore[assignment]

MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
PROJECT_VERSION_RE = re.compile(r'^\s*version\s*=\s*"([^"]+)"\s*$', re.MULTILINE)
TABLE_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "#")


@dataclass(frozen=True)
class DoctorResult:
    ok: bool
    messages: list[str]
    failures: list[str]


@dataclass(frozen=True)
class DemoDoctorResult:
    ok: bool
    messages: list[str]
    failures: list[str]
    repair_command: str


DEMO_REQUIRED_FILES = (
    Path("dashboard.html"),
    Path("workflow_summary.json"),
    Path("research_summary.json"),
    Path("memos/memo_summary.json"),
    Path("packs/pack_summary.json"),
    Path("comparison/comparison.html"),
    Path("comparison/comparison.json"),
    Path("valuation.csv"),
)


def check_release_readiness(root: Path, expected_version: str | None = None) -> DoctorResult:
    root = root.resolve()
    failures: list[str] = []
    messages: list[str] = []
    project_version = _read_project_version(root / "pyproject.toml", failures)
    version = expected_version or project_version
    if not version or not project_version:
        return DoctorResult(ok=False, messages=messages, failures=failures)

    release_note = Path("docs/releases") / f"v{version}.md"
    if project_version != version:
        failures.append(f"pyproject version expected {version}")
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


def check_demo_readiness(output_dir: Path) -> DemoDoctorResult:
    failures: list[str] = []
    messages: list[str] = [f"output directory {output_dir}"]
    repair_command = f"python -m taiwan_stock_analysis.cli demo quickstart --output-dir {output_dir}"

    for relative_path in DEMO_REQUIRED_FILES:
        path = output_dir / relative_path
        if not path.exists():
            failures.append(f"missing {path}")

    workflow_summary = _read_json(output_dir / "workflow_summary.json", failures)
    research_summary = _read_json(output_dir / "research_summary.json", failures)

    dashboard_path = output_dir / "dashboard.html"
    if dashboard_path.exists():
        try:
            dashboard_text = dashboard_path.read_text(encoding="utf-8")
        except OSError as exc:
            failures.append(f"could not read {dashboard_path}: {exc}")
        else:
            if "Review Actions" not in dashboard_text:
                failures.append(f"dashboard missing Review Actions: {dashboard_path}")

    if isinstance(workflow_summary, dict):
        successful_stock_ids = workflow_summary.get("successful_stock_ids")
        if not isinstance(successful_stock_ids, list) or not successful_stock_ids:
            failures.append(f"workflow summary has no successful stock ids: {output_dir / 'workflow_summary.json'}")
        else:
            messages.append("workflow summary has successful stocks")

    if isinstance(research_summary, dict):
        review_action_queue = research_summary.get("review_action_queue")
        if not isinstance(review_action_queue, list) or not review_action_queue:
            failures.append(f"research summary has no review-action queue: {output_dir / 'research_summary.json'}")
        else:
            messages.append("research summary has review actions")

    if not failures:
        messages.append("required files present")
        messages.append("dashboard includes Review Actions")

    return DemoDoctorResult(
        ok=not failures,
        messages=messages,
        failures=failures,
        repair_command=repair_command,
    )


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


def format_demo_doctor_result(result: DemoDoctorResult) -> str:
    if result.ok:
        lines = ["Demo readiness OK:"]
        lines.extend(f"- {message}" for message in result.messages)
        return "\n".join(lines)
    lines = ["Demo readiness failed:"]
    lines.extend(f"- {failure}" for failure in result.failures)
    lines.append("")
    lines.append("Repair:")
    lines.append(result.repair_command)
    return "\n".join(lines)


def _read_json(path: Path, failures: list[str]) -> object | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        failures.append(f"invalid JSON: {path}: {exc.msg}")
    except OSError as exc:
        failures.append(f"could not read {path}: {exc}")
    return None


def _read_project_version(path: Path, failures: list[str]) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        failures.append("Missing pyproject.toml")
        return ""
    if tomllib is not None:
        try:
            payload = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            failures.append(f"Invalid pyproject.toml: {exc}")
            return ""
        version = payload.get("project", {}).get("version")
        if isinstance(version, str) and version:
            return version
        failures.append("pyproject.toml missing project.version")
        return ""
    text = _project_section(text)
    match = PROJECT_VERSION_RE.search(text)
    if not match:
        failures.append("pyproject.toml missing project.version")
        return ""
    return match.group(1)


def _project_section(text: str) -> str:
    lines: list[str] = []
    in_project = False
    for line in text.splitlines():
        table = TABLE_RE.match(line)
        if table:
            in_project = table.group(1).strip() == "project"
            continue
        if in_project:
            lines.append(line)
    return "\n".join(lines)


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
