from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import math
import os
import stat
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


FUBON_STOCK_BASE_URL = "https://api.fugle.tw/marketdata/v1.0/stock"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUPPORTED_SDK_VERSION = "2.2.8"
_MAX_CREDENTIAL_LENGTH = 16 * 1024
_MAX_SDK_TOKEN_LENGTH = 64 * 1024
_MIN_AUTH_COOLDOWN_SECONDS = 60.0
_MAX_AUTH_COOLDOWN_SECONDS = 15.0 * 60.0
_BOUNDED_LOGOUT_WAIT_SECONDS = 0.05


class FubonSessionError(RuntimeError):
    """A sanitized failure while creating or using a Fubon market session."""


class FubonConfigurationError(FubonSessionError):
    """The explicit Fubon configuration is missing or unsafe."""


class FubonSDKUnavailableError(FubonSessionError):
    """The optional Fubon Neo SDK cannot be loaded or initialized."""


class FubonAuthenticationError(FubonSessionError):
    """Fubon rejected the configured credentials or login could not complete."""


class FubonAuthenticationCooldownError(FubonAuthenticationError):
    """Authentication is temporarily blocked after a recent failure."""

    def __init__(self, retry_after_seconds: float) -> None:
        self.retry_after_seconds = max(0.0, retry_after_seconds)
        super().__init__(
            "Fubon authentication is temporarily unavailable; retry later"
        )


class FubonSessionTimeoutError(FubonSessionError):
    """A bounded wait expired while the SDK worker was still running."""


@dataclass(frozen=True, slots=True)
class FubonSession:
    """Credentials needed by the licensed Fubon/Fugle REST stock endpoint."""

    base_url: str
    sdk_token: str = field(repr=False)


@dataclass(slots=True)
class _AuthenticationBreaker:
    lock: threading.RLock = field(default_factory=threading.RLock)
    condition: threading.Condition = field(init=False)
    consecutive_failures: int = 0
    blocked_until: float = 0.0
    attempt_in_progress: bool = False
    invalidations_in_progress: int = 0
    invalidation_epoch: int = 0

    def __post_init__(self) -> None:
        self.condition = threading.Condition(self.lock)


@dataclass(slots=True)
class _SessionAttempt:
    generation: int
    done: threading.Event = field(default_factory=threading.Event)
    cancelled: bool = False
    authentication_failure_recorded: bool = False
    error: FubonSessionError | None = None


_AUTHENTICATION_BREAKERS: dict[str, _AuthenticationBreaker] = {}
_AUTHENTICATION_BREAKERS_LOCK = threading.Lock()


class FubonSessionManager:
    """Lazily create and cache one authenticated Fubon Neo market session.

    The SDK is optional and is imported only when :meth:`sdk_available` or
    :meth:`session` is called. Authentication responses are deliberately not
    exposed because they contain customer account and name fields.
    """

    def __init__(
        self,
        personal_id: str | None,
        api_key: str | None,
        cert_path: str | os.PathLike[str] | None,
        cert_password: str | None,
        *,
        sdk_factory: Callable[[], Any] | None = None,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        self._personal_id = personal_id
        self._api_key = api_key
        self._cert_path = cert_path
        self._cert_password = cert_password
        self._provided_sdk_factory = sdk_factory
        self._monotonic_clock = (
            monotonic_clock
            if monotonic_clock is not None
            else time.monotonic
        )
        self._loaded_sdk_factory: Callable[[], Any] | None = None
        self._sdk: Any | None = None
        self._session: FubonSession | None = None
        self._session_invalidation_epoch: int | None = None
        self._attempt: _SessionAttempt | None = None
        self._generation = 0
        self._authentication_scope: str | None = None
        self._authentication_invalidations_in_progress = 0
        self._closed = False
        self._lock = threading.RLock()
        self._sdk_factory_lock = threading.Lock()

    def configuration_error(self) -> str:
        """Return a sanitized configuration problem, or an empty string."""

        issue, _ = self._validated_configuration()
        return issue

    def sdk_available(self) -> bool:
        """Return whether the optional SDK entry point can be loaded."""

        with self._lock:
            try:
                self._sdk_factory()
            except FubonSDKUnavailableError:
                return False
            return True

    def session(
        self,
        timeout_seconds: float | None = None,
    ) -> FubonSession:
        """Return a cached session or wait for one daemon authentication worker.

        ``timeout_seconds=None`` preserves the original blocking API. A bounded
        wait never abandons or duplicates an in-flight SDK login; a later call
        may consume the session after that worker finishes.
        """

        timeout = _validated_timeout(timeout_seconds)
        stale_sdk: Any | None = None
        stale_error: FubonAuthenticationCooldownError | None = None
        with self._lock:
            if self._closed:
                raise FubonSessionError("the Fubon session manager is closed")
            if self._authentication_invalidations_in_progress > 0:
                raise FubonAuthenticationCooldownError(
                    _MIN_AUTH_COOLDOWN_SECONDS
                )
            if self._session is not None:
                cached_session, stale_sdk, stale_error = (
                    self._validated_cached_session_locked()
                )
                if cached_session is not None:
                    return cached_session

            attempt = self._attempt
            if stale_error is None and attempt is None:
                issue, certificate_path = self._validated_configuration()
                if issue or certificate_path is None:
                    raise FubonConfigurationError(
                        issue or "the Fubon configuration is invalid"
                    )
                breaker = self._breaker(certificate_path)
                attempt = _SessionAttempt(generation=self._generation)
                self._attempt = attempt
                worker = threading.Thread(
                    target=self._establish_session_worker,
                    args=(attempt, certificate_path, breaker),
                    daemon=True,
                    name="fubon-session-establishment",
                )
                worker.start()

        if stale_error is not None:
            self._bounded_best_effort_logout(stale_sdk)
            raise stale_error from None
        if not attempt.done.wait(timeout):
            raise FubonSessionTimeoutError(
                "Fubon session establishment timed out"
            )

        with self._lock:
            if self._closed:
                raise FubonSessionError("the Fubon session manager is closed")
            if (
                attempt.cancelled
                or attempt.generation != self._generation
            ):
                raise FubonSessionError(
                    "Fubon session establishment was invalidated"
                )
            if self._session is not None:
                cached_session, stale_sdk, stale_error = (
                    self._validated_cached_session_locked()
                )
                if cached_session is not None:
                    return cached_session
            if attempt.error is not None:
                raise attempt.error from None
            if stale_error is None:
                raise FubonSessionError(
                    "Fubon session establishment did not produce a session"
                )

        self._bounded_best_effort_logout(stale_sdk)
        raise stale_error from None

    def stock_websocket_client(
        self,
        timeout_seconds: float | None = None,
    ) -> Any:
        """Return the authenticated Normal-mode stock WebSocket client."""

        self.session(timeout_seconds=timeout_seconds)
        with self._lock:
            if self._closed or self._sdk is None:
                raise FubonSessionError(
                    "the Fubon market WebSocket session is unavailable"
                )
            try:
                client = self._sdk.marketdata.websocket_client.stock
            except Exception:
                raise FubonSessionError(
                    "the Fubon stock WebSocket client is unavailable"
                ) from None
            if client is None:
                raise FubonSessionError(
                    "the Fubon stock WebSocket client is unavailable"
                )
            return client

    def invalidate(self, *, authentication_failure: bool = False) -> None:
        """Discard the cached session and best-effort logout its SDK."""

        breaker: _AuthenticationBreaker | None = None
        should_record_authentication_failure = False
        with self._lock:
            if authentication_failure:
                breaker = self._current_breaker()
                self._authentication_invalidations_in_progress += 1
                if breaker is not None:
                    with breaker.condition:
                        breaker.invalidations_in_progress += 1
                        breaker.invalidation_epoch += 1
            attempt = self._attempt
            if attempt is not None:
                attempt.cancelled = True
                if (
                    authentication_failure
                    and not attempt.authentication_failure_recorded
                ):
                    attempt.authentication_failure_recorded = True
                    should_record_authentication_failure = True
                attempt.done.set()
            elif authentication_failure:
                should_record_authentication_failure = True
            self._attempt = None
            self._generation += 1
            sdk = self._sdk
            self._sdk = None
            self._session = None
            self._session_invalidation_epoch = None

        try:
            if should_record_authentication_failure and breaker is not None:
                self._install_authentication_failure(breaker)
        finally:
            if authentication_failure:
                if breaker is not None:
                    with breaker.condition:
                        breaker.invalidations_in_progress -= 1
                        breaker.condition.notify_all()
                with self._lock:
                    self._authentication_invalidations_in_progress -= 1
        self._bounded_best_effort_logout(sdk)

    def close(self) -> None:
        """Permanently close this manager and best-effort logout once."""

        with self._lock:
            if self._closed:
                return
            self._closed = True
            attempt = self._attempt
            if attempt is not None:
                attempt.cancelled = True
                attempt.done.set()
            self._attempt = None
            self._generation += 1
            sdk = self._sdk
            self._sdk = None
            self._session = None
            self._session_invalidation_epoch = None
        self._bounded_best_effort_logout(sdk)

    def _establish_session_worker(
        self,
        attempt: _SessionAttempt,
        certificate_path: Path,
        breaker: _AuthenticationBreaker,
    ) -> None:
        try:
            claimed_invalidation_epoch = (
                self._wait_for_authentication_slot(
                    attempt,
                    breaker,
                )
            )
        except FubonSessionError as error:
            self._finish_attempt(attempt, error=error)
            return
        if claimed_invalidation_epoch is None:
            return

        sdk: Any | None = None
        created_session: FubonSession | None = None
        error: FubonSessionError | None = None
        authentication_started = False
        cancelled = False
        authentication_invalidated = False
        invalidation_retry_after = _MIN_AUTH_COOLDOWN_SECONDS
        try:
            if self._attempt_is_cancelled(attempt):
                cancelled = True
            else:
                factory = self._sdk_factory()
                if self._attempt_is_cancelled(attempt):
                    cancelled = True
                else:
                    try:
                        sdk = factory()
                    except Exception:
                        raise FubonSDKUnavailableError(
                            "the Fubon Neo SDK could not be initialized"
                        ) from None
                    if self._attempt_is_cancelled(attempt):
                        cancelled = True
                    else:
                        authentication_started = True
                        self._authenticate(sdk, certificate_path)
                        self._initialize_realtime(sdk)
                        created_session = self._extract_session(sdk)
        except FubonSessionError as caught_error:
            error = caught_error
        except Exception:
            error = FubonSessionError(
                "the Fubon market session could not be initialized"
            )
        finally:
            should_record_failure = False
            if error is not None and authentication_started:
                with self._lock:
                    if not attempt.authentication_failure_recorded:
                        attempt.authentication_failure_recorded = True
                        should_record_failure = True
            with breaker.condition:
                authentication_invalidated = (
                    breaker.invalidation_epoch
                    != claimed_invalidation_epoch
                )
                if authentication_invalidated:
                    invalidation_retry_after = max(
                        _MIN_AUTH_COOLDOWN_SECONDS,
                        breaker.blocked_until - self._monotonic_clock(),
                    )
                if should_record_failure:
                    self._record_authentication_failure(breaker)
                elif (
                    error is None
                    and created_session is not None
                    and not attempt.cancelled
                    and breaker.invalidations_in_progress == 0
                    and not authentication_invalidated
                ):
                    self._reset_authentication_breaker(breaker)
                breaker.attempt_in_progress = False
                breaker.condition.notify_all()

        if cancelled:
            self._bounded_best_effort_logout(sdk)
            self._finish_attempt(
                attempt,
                error=FubonSessionError(
                    "Fubon session establishment was invalidated"
                ),
            )
            return
        if authentication_invalidated:
            self._bounded_best_effort_logout(sdk)
            self._finish_attempt(
                attempt,
                error=FubonAuthenticationCooldownError(
                    invalidation_retry_after
                ),
            )
            return
        if error is not None:
            self._bounded_best_effort_logout(sdk)
            self._finish_attempt(attempt, error=error)
            return
        if created_session is None or sdk is None:
            self._finish_attempt(
                attempt,
                error=FubonSessionError(
                    "Fubon session establishment did not produce a session"
                ),
            )
            return

        late_authentication_invalidation = False
        with self._lock:
            with breaker.condition:
                retry_after = (
                    breaker.blocked_until - self._monotonic_clock()
                )
                late_authentication_invalidation = (
                    breaker.invalidation_epoch
                    != claimed_invalidation_epoch
                    or breaker.invalidations_in_progress > 0
                    or retry_after > 0
                )
                publish = (
                    not late_authentication_invalidation
                    and not self._closed
                    and not attempt.cancelled
                    and attempt.generation == self._generation
                    and self._attempt is attempt
                )
                if publish:
                    self._sdk = sdk
                    self._session = created_session
                    self._session_invalidation_epoch = (
                        claimed_invalidation_epoch
                    )
                    self._attempt = None
                    attempt.done.set()
                    return

        self._bounded_best_effort_logout(sdk)
        self._finish_attempt(
            attempt,
            error=(
                FubonAuthenticationCooldownError(
                    max(_MIN_AUTH_COOLDOWN_SECONDS, retry_after)
                )
                if late_authentication_invalidation
                else FubonSessionError(
                    "Fubon session establishment was invalidated"
                )
            ),
        )

    def _wait_for_authentication_slot(
        self,
        attempt: _SessionAttempt,
        breaker: _AuthenticationBreaker,
    ) -> int | None:
        while not self._attempt_is_cancelled(attempt):
            with breaker.condition:
                if breaker.invalidations_in_progress > 0:
                    raise FubonAuthenticationCooldownError(
                        _MIN_AUTH_COOLDOWN_SECONDS
                    )
                self._raise_if_authentication_blocked(breaker)
                if not breaker.attempt_in_progress:
                    breaker.attempt_in_progress = True
                    return breaker.invalidation_epoch
                breaker.condition.wait(timeout=0.05)
        return None

    def _attempt_is_cancelled(self, attempt: _SessionAttempt) -> bool:
        with self._lock:
            return (
                self._closed
                or attempt.cancelled
                or attempt.generation != self._generation
                or self._attempt is not attempt
            )

    def _validated_cached_session_locked(
        self,
    ) -> tuple[
        FubonSession | None,
        Any | None,
        FubonAuthenticationCooldownError | None,
    ]:
        if self._session is None:
            return None, None, None
        breaker = self._current_breaker()
        if breaker is None:
            sdk = self._sdk
            self._sdk = None
            self._session = None
            self._session_invalidation_epoch = None
            self._generation += 1
            return (
                None,
                sdk,
                FubonAuthenticationCooldownError(
                    _MIN_AUTH_COOLDOWN_SECONDS
                ),
            )

        with breaker.condition:
            retry_after = breaker.blocked_until - self._monotonic_clock()
            is_valid = (
                self._session_invalidation_epoch
                == breaker.invalidation_epoch
                and breaker.invalidations_in_progress == 0
                and retry_after <= 0
            )
            if is_valid:
                return self._session, None, None

            sdk = self._sdk
            self._sdk = None
            self._session = None
            self._session_invalidation_epoch = None
            self._generation += 1
            return (
                None,
                sdk,
                FubonAuthenticationCooldownError(
                    max(_MIN_AUTH_COOLDOWN_SECONDS, retry_after)
                ),
            )

    def _finish_attempt(
        self,
        attempt: _SessionAttempt,
        *,
        error: FubonSessionError,
    ) -> None:
        with self._lock:
            attempt.error = error
            if self._attempt is attempt:
                self._attempt = None
            attempt.done.set()

    def _breaker(self, certificate_path: Path) -> _AuthenticationBreaker:
        if self._authentication_scope is None:
            identity = "\0".join(
                (
                    str(self._personal_id),
                    str(self._api_key),
                    str(certificate_path),
                    str(self._cert_password),
                )
            )
            self._authentication_scope = hashlib.sha256(
                identity.encode("utf-8")
            ).hexdigest()
        return _authentication_breaker(self._authentication_scope)

    def _current_breaker(self) -> _AuthenticationBreaker | None:
        if self._authentication_scope is not None:
            return _authentication_breaker(self._authentication_scope)
        issue, certificate_path = self._validated_configuration()
        if issue or certificate_path is None:
            return None
        return self._breaker(certificate_path)

    def _raise_if_authentication_blocked(
        self,
        breaker: _AuthenticationBreaker,
    ) -> None:
        retry_after_seconds = breaker.blocked_until - self._monotonic_clock()
        if retry_after_seconds > 0:
            raise FubonAuthenticationCooldownError(retry_after_seconds)

    def _record_authentication_failure(
        self,
        breaker: _AuthenticationBreaker,
    ) -> None:
        breaker.consecutive_failures = min(
            breaker.consecutive_failures + 1,
            64,
        )
        exponent = min(breaker.consecutive_failures - 1, 4)
        cooldown = min(
            _MAX_AUTH_COOLDOWN_SECONDS,
            _MIN_AUTH_COOLDOWN_SECONDS * (2**exponent),
        )
        breaker.blocked_until = max(
            breaker.blocked_until,
            self._monotonic_clock() + cooldown,
        )

    def _install_authentication_failure(
        self,
        breaker: _AuthenticationBreaker,
    ) -> None:
        with breaker.condition:
            self._record_authentication_failure(breaker)
            breaker.condition.notify_all()

    @staticmethod
    def _reset_authentication_breaker(
        breaker: _AuthenticationBreaker,
    ) -> None:
        breaker.consecutive_failures = 0
        breaker.blocked_until = 0.0

    def _validated_configuration(self) -> tuple[str, Path | None]:
        for field_name, value, whitespace_allowed in (
            ("personal_id", self._personal_id, False),
            ("api_key", self._api_key, False),
            ("cert_password", self._cert_password, True),
        ):
            if value is None or value == "":
                return f"Fubon configuration requires {field_name}", None
            if not _safe_credential(
                value,
                whitespace_allowed=whitespace_allowed,
            ):
                return f"Fubon configuration has an invalid {field_name}", None

        if self._cert_path is None or self._cert_path == "":
            return "Fubon configuration requires cert_path", None
        if self._provided_sdk_factory is not None and not callable(
            self._provided_sdk_factory
        ):
            return "Fubon configuration has an invalid SDK factory", None

        try:
            raw_path = os.fspath(self._cert_path)
            if not isinstance(raw_path, str) or not _safe_path_value(raw_path):
                return "Fubon configuration has an invalid cert_path", None

            candidate = Path(raw_path)
            if candidate.is_absolute():
                certificate_path = candidate.resolve(strict=False)
            else:
                repository_root = _REPO_ROOT.resolve(strict=True)
                certificate_path = (repository_root / candidate).resolve(
                    strict=False
                )
                try:
                    certificate_path.relative_to(repository_root)
                except ValueError:
                    return (
                        "Fubon relative cert_path must stay within the repository",
                        None,
                    )

            certificate_stat = certificate_path.stat()
        except Exception:
            return (
                "Fubon cert_path must identify an accessible regular file",
                None,
            )

        if not stat.S_ISREG(certificate_stat.st_mode):
            return "Fubon cert_path must identify a regular file", None
        return "", certificate_path

    def _sdk_factory(self) -> Callable[[], Any]:
        with self._sdk_factory_lock:
            return self._sdk_factory_unlocked()

    def _sdk_factory_unlocked(self) -> Callable[[], Any]:
        if self._provided_sdk_factory is not None:
            if not callable(self._provided_sdk_factory):
                raise FubonSDKUnavailableError(
                    "the configured Fubon SDK factory is unavailable"
                )
            return self._provided_sdk_factory

        if self._loaded_sdk_factory is not None:
            return self._loaded_sdk_factory

        try:
            sdk_version = importlib.metadata.version("fubon-neo")
            if sdk_version != _SUPPORTED_SDK_VERSION:
                raise LookupError
            sdk_module = importlib.import_module("fubon_neo.sdk")
            sdk_factory = getattr(sdk_module, "FubonSDK")
        except Exception:
            raise FubonSDKUnavailableError(
                "Fubon Neo SDK v2.2.8 is unavailable"
            ) from None
        if not callable(sdk_factory):
            raise FubonSDKUnavailableError(
                "Fubon Neo SDK v2.2.8 is unavailable"
            )

        self._loaded_sdk_factory = sdk_factory
        return sdk_factory

    def _authenticate(self, sdk: Any, certificate_path: Path) -> None:
        try:
            login = getattr(sdk, "apikey_login")
        except Exception:
            raise FubonSDKUnavailableError(
                "the Fubon Neo SDK does not support API key login"
            ) from None
        if not callable(login):
            raise FubonSDKUnavailableError(
                "the Fubon Neo SDK does not support API key login"
            )

        try:
            result = login(
                self._personal_id,
                self._api_key,
                str(certificate_path),
                self._cert_password,
            )
            is_success = getattr(result, "is_success") is True
        except Exception:
            raise FubonAuthenticationError(
                "Fubon API key authentication failed"
            ) from None
        if not is_success:
            raise FubonAuthenticationError(
                "Fubon API key authentication failed"
            )

    @staticmethod
    def _initialize_realtime(sdk: Any) -> None:
        try:
            initializer = getattr(sdk, "init_realtime")
            if not callable(initializer):
                raise TypeError
            sdk_module = importlib.import_module("fubon_neo.sdk")
            mode = getattr(getattr(sdk_module, "Mode"), "Normal")
            initializer(mode)
        except Exception:
            raise FubonSessionError(
                "Fubon market-data initialization failed"
            ) from None

    @staticmethod
    def _extract_session(sdk: Any) -> FubonSession:
        try:
            config = sdk.marketdata.rest_client.stock.config
            if not isinstance(config, Mapping):
                raise TypeError
            sdk_token = config.get("sdk_token")
            base_url = config.get("base_url")
        except Exception:
            raise FubonSessionError(
                "Fubon market-data REST configuration is unavailable"
            ) from None

        if not _safe_sdk_token(sdk_token):
            raise FubonSessionError(
                "Fubon market-data REST token is unavailable"
            )
        try:
            canonical_base_url = _canonical_stock_base_url(base_url)
        except ValueError:
            raise FubonSessionError(
                "Fubon market-data REST endpoint is not trusted"
            ) from None
        return FubonSession(
            base_url=canonical_base_url,
            sdk_token=sdk_token,
        )

    @staticmethod
    def _best_effort_logout(sdk: Any | None) -> None:
        if sdk is None:
            return
        try:
            logout = getattr(sdk, "logout", None)
            if callable(logout):
                logout()
        except Exception:
            return

    @classmethod
    def _bounded_best_effort_logout(cls, sdk: Any | None) -> None:
        if sdk is None:
            return
        worker = threading.Thread(
            target=cls._best_effort_logout,
            args=(sdk,),
            daemon=True,
            name="fubon-session-logout",
        )
        try:
            worker.start()
            worker.join(timeout=_BOUNDED_LOGOUT_WAIT_SECONDS)
        except RuntimeError:
            return


def _safe_credential(
    value: object,
    *,
    whitespace_allowed: bool,
) -> bool:
    if not isinstance(value, str):
        return False
    if (
        not value
        or not value.strip()
        or len(value) > _MAX_CREDENTIAL_LENGTH
    ):
        return False
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return False
    if not whitespace_allowed and any(
        character.isspace() for character in value
    ):
        return False
    return True


def _safe_path_value(value: str) -> bool:
    return (
        bool(value)
        and len(value) <= _MAX_CREDENTIAL_LENGTH
        and not any(
            ord(character) < 32 or ord(character) == 127
            for character in value
        )
    )


def _safe_sdk_token(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= _MAX_SDK_TOKEN_LENGTH
        and not any(character.isspace() for character in value)
        and not any(
            ord(character) < 32 or ord(character) == 127
            for character in value
        )
    )


def _validated_timeout(value: float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("timeout_seconds must be a positive finite number")
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            "timeout_seconds must be a positive finite number"
        ) from None
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout_seconds must be a positive finite number")
    return timeout


def _canonical_stock_base_url(value: object) -> str:
    if value != FUBON_STOCK_BASE_URL:
        raise ValueError("untrusted Fubon stock REST endpoint")

    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "api.fugle.tw"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/marketdata/v1.0/stock"
    ):
        raise ValueError("untrusted Fubon stock REST endpoint")
    return FUBON_STOCK_BASE_URL


def _authentication_breaker(scope: str) -> _AuthenticationBreaker:
    with _AUTHENTICATION_BREAKERS_LOCK:
        breaker = _AUTHENTICATION_BREAKERS.get(scope)
        if breaker is None:
            breaker = _AuthenticationBreaker()
            _AUTHENTICATION_BREAKERS[scope] = breaker
        return breaker


__all__ = [
    "FUBON_STOCK_BASE_URL",
    "FubonAuthenticationError",
    "FubonAuthenticationCooldownError",
    "FubonConfigurationError",
    "FubonSDKUnavailableError",
    "FubonSession",
    "FubonSessionError",
    "FubonSessionManager",
    "FubonSessionTimeoutError",
]
