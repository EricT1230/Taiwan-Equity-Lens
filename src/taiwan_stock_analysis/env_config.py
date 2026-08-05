from __future__ import annotations

import json
import os
import re
from pathlib import Path


APP_ENV_KEYS = frozenset(
    {
        "FUBON_API_KEY",
        "FUBON_CERT_PASSWORD",
        "FUBON_CERT_PATH",
        "FUBON_MARKET_DATA_ONLY_CONFIRMED",
        "FUBON_PERSONAL_ID",
        "FUBON_REDISPLAY_LICENSED",
        "FUBON_TAIEX_SYMBOL",
        "FUBON_TPEX_SYMBOL",
        "FUGLE_API_KEY",
        "FUGLE_REDISPLAY_LICENSED",
        "FUGLE_TAIEX_SYMBOL",
        "FUGLE_TPEX_SYMBOL",
        "MARKET_DATA_PROVIDER",
    }
)

_ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MAX_ENV_FILE_BYTES = 64 * 1024
_MARKET_DATA_PROVIDERS = frozenset(
    {"auto", "fubon", "fugle", "twse-mis-personal"}
)
_BOOLEAN_VALUES = frozenset(
    {"0", "1", "false", "no", "true", "yes"}
)


class EnvConfigError(ValueError):
    """A sanitized local .env configuration error."""


def project_env_path() -> Path:
    """Return the source checkout's project-root .env path."""

    return Path(__file__).resolve().parents[2] / ".env"


def load_project_env(path: Path | None = None) -> tuple[str, ...]:
    """Load supported app settings without overriding process environment.

    The file is parsed completely before any values are applied so a malformed
    line cannot leave a partially configured process. Unknown variables are
    intentionally ignored instead of being copied into the whole process.
    """

    env_path = Path(path) if path is not None else project_env_path()
    try:
        size = env_path.stat().st_size
    except FileNotFoundError:
        return ()
    except OSError as exc:
        raise EnvConfigError("could not inspect the local .env file") from exc

    if not env_path.is_file():
        raise EnvConfigError("the local .env path is not a regular file")
    if size > _MAX_ENV_FILE_BYTES:
        raise EnvConfigError("the local .env file exceeds the 64 KiB limit")

    try:
        content = env_path.read_text(encoding="utf-8-sig")
    except UnicodeError:
        raise EnvConfigError(
            "the local .env file must use UTF-8 encoding"
        ) from None
    except OSError as exc:
        raise EnvConfigError("could not read the local .env file") from exc

    parsed = _parse_env(content)
    pending = {
        key: value
        for key, value in parsed.items()
        if key not in os.environ
    }
    if any("\x00" in value for value in pending.values()):
        raise EnvConfigError("the local .env file contains an invalid value")
    _validate_app_env(pending)
    loaded: list[str] = []
    for key, value in pending.items():
        os.environ[key] = value
        loaded.append(key)
    return tuple(loaded)


def _parse_env(content: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()

        key, separator, raw_value = line.partition("=")
        key = key.strip()
        if not separator or not _ENV_KEY_PATTERN.fullmatch(key):
            raise EnvConfigError(
                f"invalid local .env syntax at line {line_number}"
            )
        if key not in APP_ENV_KEYS:
            continue
        parsed[key] = _parse_env_value(raw_value, line_number)
    return parsed


def _validate_app_env(parsed: dict[str, str]) -> None:
    provider = parsed.get("MARKET_DATA_PROVIDER", "").strip().lower()
    if provider and provider not in _MARKET_DATA_PROVIDERS:
        raise EnvConfigError(
            "MARKET_DATA_PROVIDER in .env must be auto, fubon, fugle, "
            "or twse-mis-personal"
        )

    for name in (
        "FUBON_MARKET_DATA_ONLY_CONFIRMED",
        "FUBON_REDISPLAY_LICENSED",
        "FUGLE_REDISPLAY_LICENSED",
    ):
        redisplay = parsed.get(name, "").strip().lower()
        if redisplay and redisplay not in _BOOLEAN_VALUES:
            raise EnvConfigError(
                f"{name} in .env must be a boolean value"
            )


def _parse_env_value(raw_value: str, line_number: int) -> str:
    value = raw_value.strip()
    if not value:
        return ""
    if "\x00" in value:
        raise EnvConfigError(
            f"invalid local .env value at line {line_number}"
        )

    if value[0] in {"'", '"'}:
        quote = value[0]
        end = _quoted_value_end(value, quote)
        if end is None:
            raise EnvConfigError(
                f"unterminated local .env quote at line {line_number}"
            )
        remainder = value[end + 1 :].strip()
        if remainder and not remainder.startswith("#"):
            raise EnvConfigError(
                f"invalid local .env value at line {line_number}"
            )
        quoted = value[: end + 1]
        if quote == "'":
            return quoted[1:-1]
        try:
            decoded = json.loads(quoted)
        except json.JSONDecodeError:
            raise EnvConfigError(
                f"invalid local .env value at line {line_number}"
            ) from None
        if not isinstance(decoded, str):
            raise EnvConfigError(
                f"invalid local .env value at line {line_number}"
            )
        return decoded

    comment_start = next(
        (
            index
            for index, char in enumerate(value)
            if char == "#" and index > 0 and value[index - 1].isspace()
        ),
        None,
    )
    if comment_start is not None:
        value = value[:comment_start].rstrip()
    return value


def _quoted_value_end(value: str, quote: str) -> int | None:
    escaped = False
    for index in range(1, len(value)):
        char = value[index]
        if quote == '"' and char == "\\" and not escaped:
            escaped = True
            continue
        if char == quote and not escaped:
            return index
        escaped = False
    return None
