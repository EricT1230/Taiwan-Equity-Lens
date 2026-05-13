from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_run_metadata(
    kind: str,
    command: str,
    inputs: dict[str, Any],
    output_root: str,
    *,
    generated_at: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    timestamp = generated_at or _utc_timestamp()
    return {
        "run_id": run_id or f"{kind}-{_timestamp_token(timestamp)}",
        "generated_at": timestamp,
        "kind": kind,
        "command": command,
        "inputs": dict(inputs),
        "output_root": str(output_root),
    }


def read_run_metadata(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    metadata = payload.get("run_metadata")
    if not isinstance(metadata, dict):
        return {}
    required_text_fields = ("run_id", "generated_at", "kind", "command", "output_root")
    if any(not isinstance(metadata.get(field), str) or not metadata[field] for field in required_text_fields):
        return {}
    if not isinstance(metadata.get("inputs"), dict):
        return {}
    return dict(metadata)


def build_artifact_registry(
    self_path: str,
    *,
    dependencies: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "self": str(self_path),
        "dependencies": dict(dependencies or {}),
        "outputs": dict(outputs or {}),
    }


def merge_traceability(
    payload: dict[str, Any],
    *,
    run_metadata: dict[str, Any],
    artifact_registry: dict[str, Any],
) -> dict[str, Any]:
    return {
        **payload,
        "run_metadata": dict(run_metadata),
        "artifact_registry": dict(artifact_registry),
    }


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp_token(timestamp: str) -> str:
    return timestamp.replace("-", "").replace(":", "")
