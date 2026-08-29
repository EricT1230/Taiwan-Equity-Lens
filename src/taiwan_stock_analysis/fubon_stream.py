"""Thread-safe Fubon WebSocket quote overlay.

The feed accepts an already-created Fubon stock WebSocket client.  It never
owns credentials, performs login, or calls account/trading APIs.
"""

from __future__ import annotations

import copy
import json
import math
import re
import threading
from datetime import date, datetime, time, timedelta, timezone
from time import monotonic
from typing import Any, Callable, Iterable, Mapping

from taiwan_stock_analysis.trading_calendar import TAIPEI


Clock = Callable[[], datetime]
MAX_STOCK_SUBSCRIPTIONS = 180
MAX_INDEX_SUBSCRIPTIONS = 16
MAX_WEBSOCKET_MESSAGE_CHARS = 256 * 1024
MAX_WEBSOCKET_MESSAGE_BYTES = 256 * 1024
FUBON_WEBSOCKET_INDEX_SYMBOL_MAP = {
    "IX0001": "IR0001",
    "IX0043": "IR0043",
}
_SYMBOL_RE = re.compile(r"^[0-9A-Za-z._-]{1,32}$")
_SUPPORTED_EXCHANGES = {"TWSE", "TPEX"}
_RECONNECT_INITIAL_SECONDS = 5.0
_RECONNECT_MAX_SECONDS = 60.0
_CONNECT_START_WAIT_SECONDS = 0.05
_PROVIDER_CONNECT_TIMEOUT_SECONDS = 8.0
_PROVIDER_CONNECT_WAIT_SECONDS = 0.05
_MAX_PAYLOAD_ARRAY_LENGTH = 256
_MAX_PAYLOAD_DEPTH = 8
_MAX_PAYLOAD_NODES = 2_048
_MAX_PAYLOAD_OBJECT_FIELDS = 128
_MAX_PAYLOAD_KEY_CHARS = 128
_MAX_RETAINED_STRING_CHARS = 128
_MAX_EVENT_NAME_CHARS = 64
_MAX_SUBSCRIPTION_ID_CHARS = 128
__all__ = [
    "FUBON_WEBSOCKET_INDEX_SYMBOL_MAP",
    "FubonWebSocketFeed",
    "MAX_INDEX_SUBSCRIPTIONS",
    "MAX_STOCK_SUBSCRIPTIONS",
    "MAX_WEBSOCKET_MESSAGE_BYTES",
    "MAX_WEBSOCKET_MESSAGE_CHARS",
    "resolve_fubon_websocket_index_symbol",
]


def resolve_fubon_websocket_index_symbol(
    rest_symbol: str,
    overrides: Mapping[str, str] | None = None,
) -> str:
    """Resolve a REST index identity to the licensed WebSocket identity.

    Only evidence-backed defaults are translated.  Unknown symbols pass
    through unchanged so the adapter never invents a provider identifier.
    """

    normalized = str(rest_symbol).strip().upper()
    if not _SYMBOL_RE.fullmatch(normalized):
        raise ValueError("invalid REST index symbol")
    resolved = dict(FUBON_WEBSOCKET_INDEX_SYMBOL_MAP)
    for source, target in (overrides or {}).items():
        normalized_source = str(source).strip().upper()
        normalized_target = str(target).strip().upper()
        if not _SYMBOL_RE.fullmatch(normalized_source) or not _SYMBOL_RE.fullmatch(
            normalized_target
        ):
            raise ValueError("invalid WebSocket index symbol override")
        resolved[normalized_source] = normalized_target
    return resolved.get(normalized, normalized)


class _ProviderConnectCancelled(Exception):
    """Internal control flow for an intentionally cancelled connection."""


class _FugleSdkConnectAdapter:
    """Bound the legacy Fugle SDK connection without its busy-wait loop.

    Fugle market-data 2.4.x starts ``WebSocketApp.run_forever`` and then spins
    in Python until authentication changes state.  A TCP/TLS failure before
    ``on_open`` leaves that state pending forever.  The WebSocket app already
    owns all SDK callbacks, authentication, and health checks, so running it in
    a daemon thread and waiting on feed callback events preserves those
    semantics while adding cancellation and a hard termination condition.
    """

    def __init__(self, client: Any, websocket_app: Any) -> None:
        self._client = client
        self._websocket_app = websocket_app
        self._lock = threading.Lock()
        self._runner: threading.Thread | None = None

    @classmethod
    def from_client(cls, client: Any) -> "_FugleSdkConnectAdapter | None":
        current = client
        seen: set[int] = set()
        for _ in range(4):
            identity = id(current)
            if identity in seen:
                break
            seen.add(identity)
            module = str(type(current).__module__ or "")
            websocket_app = getattr(current, "_WebSocketClient__ws", None)
            if (
                module.startswith("fugle_marketdata.websocket")
                and websocket_app is not None
                and callable(getattr(websocket_app, "run_forever", None))
                and callable(getattr(websocket_app, "close", None))
            ):
                return cls(client, websocket_app)
            nested = getattr(current, "_client", None)
            if nested is None or nested is current:
                break
            current = nested
        return None

    def connect(
        self,
        *,
        cancelled: threading.Event,
        terminal: threading.Event,
    ) -> None:
        if cancelled.is_set():
            raise _ProviderConnectCancelled()
        runner_done = threading.Event()

        def run_provider_socket() -> None:
            try:
                self._websocket_app.run_forever()
            except Exception:
                # Provider exception text can contain connection details.  The
                # feed reports only a fixed ERROR state and never redisplays it.
                pass
            finally:
                runner_done.set()

        with self._lock:
            previous = self._runner
            if previous is not None and previous.is_alive():
                raise RuntimeError("provider socket runner is still active")
            runner = threading.Thread(
                target=run_provider_socket,
                daemon=True,
                name="fubon-websocket-socket",
            )
            self._runner = runner
        if cancelled.is_set():
            raise _ProviderConnectCancelled()
        runner.start()
        deadline = monotonic() + _PROVIDER_CONNECT_TIMEOUT_SECONDS
        while True:
            if cancelled.is_set():
                raise _ProviderConnectCancelled()
            if terminal.is_set():
                return
            if runner_done.is_set():
                if terminal.is_set():
                    return
                raise RuntimeError("provider socket stopped before authentication")
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError("provider authentication did not complete")
            terminal.wait(min(_PROVIDER_CONNECT_WAIT_SECONDS, remaining))

    def stop(self) -> None:
        self.request_stop()
        with self._lock:
            runner = self._runner
        if (
            runner is not None
            and runner.ident is not None
            and runner is not threading.current_thread()
        ):
            # This runs only on the daemon connection worker.  Do not publish
            # DISCONNECTED while the provider socket can still emit callbacks
            # or reject a new run_forever attempt.  The public disconnect()
            # call remains non-blocking because it only signals this worker.
            runner.join()

    def request_stop(self) -> None:
        """Best-effort provider stop without waiting for socket teardown."""

        try:
            self._client.disconnect()
        except Exception:
            pass


class FubonWebSocketFeed:
    """Maintain a validated overlay from Normal-mode market-data channels."""

    def __init__(
        self,
        client: Any,
        *,
        clock: Clock | None = None,
        freshness_seconds: float = 120.0,
        silence_seconds: float = 45.0,
        provider_delay_seconds: float | None = None,
    ) -> None:
        self._client = client
        self._clock = clock or (lambda: datetime.now(TAIPEI))
        self._freshness_seconds = max(1.0, float(freshness_seconds))
        self._silence_seconds = max(1.0, float(silence_seconds))
        parsed_provider_delay = (
            _finite(provider_delay_seconds)
            if provider_delay_seconds is not None
            else None
        )
        if provider_delay_seconds is not None and (
            parsed_provider_delay is None or parsed_provider_delay <= 0
        ):
            raise ValueError("provider_delay_seconds must be a positive number")
        self._provider_delay_seconds = parsed_provider_delay
        self._lock = threading.RLock()
        self._closed = False
        self._transport_status = "DISCONNECTED"
        self._last_message_at: datetime | None = None
        self._rejected_messages = 0
        self._data_tainted = False
        self._reconnect_failures = 0
        self._retry_not_before: datetime | None = None
        self._failure_incident_active = False
        self._intentional_disconnect = False
        self._connect_worker: threading.Thread | None = None
        self._connect_cancelled = threading.Event()
        self._connect_terminal = threading.Event()
        self._provider_connect_adapter = _FugleSdkConnectAdapter.from_client(client)
        self._stock_symbols: set[str] = set()
        self._index_symbols: set[str] = set()
        self._sent_stock_symbols: set[str] = set()
        self._sent_index_symbols: set[str] = set()
        self._subscription_ids: dict[tuple[str, str], str] = {}
        self._aggregates: dict[str, dict[str, Any]] = {}
        self._indices: dict[str, dict[str, Any]] = {}

        client.on("connect", self._on_connect)
        client.on("unauthenticated", self._on_unauthenticated)
        client.on("disconnect", self._on_disconnect)
        client.on("error", self._on_error)
        client.on("message", self._on_message)

    def subscribe(
        self,
        *,
        stock_symbols: Iterable[str] = (),
        index_symbols: Iterable[str] = (),
    ) -> None:
        requested_stocks = _validated_symbols(
            stock_symbols,
            kind="stock",
            limit=MAX_STOCK_SUBSCRIPTIONS,
        )
        requested_indices = _validated_symbols(
            index_symbols,
            kind="index",
            limit=MAX_INDEX_SUBSCRIPTIONS,
        )
        should_send = False
        with self._lock:
            if self._closed:
                raise RuntimeError("feed is closed")
            next_stocks = self._stock_symbols | requested_stocks
            next_indices = self._index_symbols | requested_indices
            if len(next_stocks) > MAX_STOCK_SUBSCRIPTIONS:
                raise ValueError(
                    f"stock subscription limit is {MAX_STOCK_SUBSCRIPTIONS}"
                )
            if len(next_indices) > MAX_INDEX_SUBSCRIPTIONS:
                raise ValueError(
                    f"index subscription limit is {MAX_INDEX_SUBSCRIPTIONS}"
                )
            self._stock_symbols = next_stocks
            self._index_symbols = next_indices
            if self._transport_status in {"AUTHENTICATED", "STREAMING"}:
                should_send = True
        if should_send:
            self._send_subscriptions()

    def unsubscribe(
        self,
        *,
        stock_symbols: Iterable[str] = (),
        index_symbols: Iterable[str] = (),
    ) -> None:
        requested_stocks = _validated_symbols(
            stock_symbols,
            kind="stock",
            limit=MAX_STOCK_SUBSCRIPTIONS,
        )
        requested_indices = _validated_symbols(
            index_symbols,
            kind="index",
            limit=MAX_INDEX_SUBSCRIPTIONS,
        )
        with self._lock:
            removed_stocks = self._stock_symbols & requested_stocks
            removed_indices = self._index_symbols & requested_indices
            self._stock_symbols.difference_update(removed_stocks)
            self._index_symbols.difference_update(removed_indices)
            self._sent_stock_symbols.difference_update(removed_stocks)
            self._sent_index_symbols.difference_update(removed_indices)
            self._aggregates = {
                symbol: row
                for symbol, row in self._aggregates.items()
                if symbol not in removed_stocks
            }
            self._indices = {
                symbol: row
                for symbol, row in self._indices.items()
                if symbol not in removed_indices
            }
            keys = [
                *(('aggregates', symbol) for symbol in removed_stocks),
                *(('indices', symbol) for symbol in removed_indices),
            ]
            subscription_ids = sorted(
                subscription_id
                for key in keys
                if (subscription_id := self._subscription_ids.pop(key, None))
            )
        if subscription_ids:
            self._client.unsubscribe({"ids": subscription_ids})

    def connect(self) -> None:
        now = self._now()
        completed = threading.Event()
        with self._lock:
            if self._closed:
                raise RuntimeError("feed is closed")
            if self._connect_worker is not None:
                return
            if self._transport_status not in {
                "DISCONNECTED",
                "ERROR",
                "UNAUTHENTICATED",
            }:
                return
            if self._retry_after_locked(now) > 0:
                return
            self._failure_incident_active = False
            self._intentional_disconnect = False
            self._connect_cancelled.clear()
            self._connect_terminal.clear()
            self._transport_status = "CONNECTING"
            worker = threading.Thread(
                target=self._run_connect_worker,
                args=(completed,),
                daemon=True,
                name="fubon-websocket-connect",
            )
            self._connect_worker = worker
        try:
            worker.start()
        except RuntimeError:
            with self._lock:
                if self._connect_worker is worker:
                    self._connect_worker = None
                if self._closed:
                    self._transport_status = "CLOSED"
                else:
                    self._transport_status = "ERROR"
                    self._record_reconnect_failure_locked(self._now())
            completed.set()
            return
        completed.wait(timeout=_CONNECT_START_WAIT_SECONDS)

    def disconnect(self) -> None:
        cleanup_worker: threading.Thread | None = None
        with self._lock:
            if self._closed or self._transport_status == "DISCONNECTED":
                return
            self._intentional_disconnect = True
            self._transport_status = "DISCONNECTING"
            managed_connect_active = bool(
                self._connect_worker is not None
                and self._provider_connect_adapter is not None
            )
            if managed_connect_active:
                self._connect_cancelled.set()
                self._connect_terminal.set()
            elif self._provider_connect_adapter is not None:
                cleanup_worker = threading.Thread(
                    target=self._run_provider_disconnect_worker,
                    daemon=True,
                    name="fubon-websocket-disconnect",
                )
                self._connect_worker = cleanup_worker
        if managed_connect_active:
            return
        if cleanup_worker is not None:
            try:
                cleanup_worker.start()
            except RuntimeError:
                with self._lock:
                    if self._connect_worker is cleanup_worker:
                        self._connect_worker = None
                adapter = self._provider_connect_adapter
                if adapter is not None:
                    adapter.request_stop()
                with self._lock:
                    if self._closed:
                        self._transport_status = "CLOSED"
                    else:
                        self._transport_status = "ERROR"
                        self._record_reconnect_failure_locked(self._now())
            return
        try:
            self._client.disconnect()
        finally:
            with self._lock:
                if not self._closed:
                    self._transport_status = "DISCONNECTED"
                    self._sent_stock_symbols.clear()
                    self._sent_index_symbols.clear()
                    self._subscription_ids.clear()

    def _run_provider_disconnect_worker(self) -> None:
        worker = threading.current_thread()
        adapter = self._provider_connect_adapter
        try:
            if adapter is not None:
                adapter.stop()
        finally:
            with self._lock:
                if not self._closed and self._intentional_disconnect:
                    self._transport_status = "DISCONNECTED"
                    self._sent_stock_symbols.clear()
                    self._sent_index_symbols.clear()
                    self._subscription_ids.clear()
                if self._connect_worker is worker:
                    self._connect_worker = None

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            should_disconnect = bool(
                self._transport_status != "DISCONNECTED"
                and self._connect_worker is None
            )
            self._closed = True
            self._transport_status = "CLOSING"
            self._connect_cancelled.set()
            self._connect_terminal.set()
        try:
            if should_disconnect:
                self._client.disconnect()
        finally:
            with self._lock:
                self._stock_symbols.clear()
                self._index_symbols.clear()
                self._sent_stock_symbols.clear()
                self._sent_index_symbols.clear()
                self._subscription_ids.clear()
                self._aggregates.clear()
                self._indices.clear()
                self._last_message_at = None
                self._data_tainted = False
                self._reconnect_failures = 0
                self._retry_not_before = None
                self._failure_incident_active = False
                self._intentional_disconnect = False
                self._transport_status = "CLOSED"

    def overlay_snapshot(self) -> dict[str, Any]:
        with self._lock:
            aggregates = copy.deepcopy(self._aggregates)
            indices = copy.deepcopy(self._indices)
            transport_status = self._transport_status
            last_message_at = self._last_message_at
            desired_stocks = set(self._stock_symbols)
            desired_indices = set(self._index_symbols)
            data_tainted = self._data_tainted
        now = self._now()
        quiet_seconds = (
            max(0.0, (now - last_message_at).total_seconds())
            if last_message_at is not None
            else None
        )
        transport_fresh = bool(
            transport_status == "STREAMING"
            and quiet_seconds is not None
            and quiet_seconds <= self._silence_seconds
        )
        for row in (*aggregates.values(), *indices.values()):
            event_time = _iso_datetime(row.get("source_event_time"))
            if event_time is None:
                row["status"] = "STALE"
                continue
            age_seconds = max(0.0, (now - event_time).total_seconds())
            row["age_seconds"] = age_seconds
            observed_status = str(row.get("status") or "UNAVAILABLE")
            if data_tainted or transport_status != "STREAMING":
                row["status"] = "STALE"
            elif observed_status == "EOD":
                row["status"] = (
                    "EOD" if event_time.date() == now.date() else "STALE"
                )
            elif not transport_fresh:
                row["status"] = "STALE"
            elif observed_status == "DELAYED":
                allowed_age = self._freshness_seconds + float(
                    row.get("delay_seconds") or 0.0
                )
                row["status"] = "DELAYED" if age_seconds <= allowed_age else "STALE"
            elif (
                observed_status == "LIVE"
                and _is_live_session_event(event_time, now)
                and age_seconds <= self._freshness_seconds
            ):
                row["status"] = "LIVE"
            else:
                row["status"] = "STALE"
        statuses = {
            str(row.get("status") or "UNAVAILABLE")
            for row in (*aggregates.values(), *indices.values())
        }
        missing_aggregates = sorted(desired_stocks - set(aggregates))
        missing_indices = sorted(desired_indices - set(indices))
        coverage_complete = not missing_aggregates and not missing_indices
        if not statuses:
            status = (
                "STALE"
                if data_tainted and (desired_stocks or desired_indices)
                else "UNAVAILABLE"
            )
        elif not coverage_complete:
            status = "STALE"
        elif len(statuses) == 1:
            status = next(iter(statuses))
        else:
            status = "STALE"
        return {
            "status": status,
            "transport_status": transport_status,
            "last_message_at": (
                last_message_at.isoformat() if last_message_at is not None else None
            ),
            "quiet_seconds": quiet_seconds,
            "coverage": {
                "complete": coverage_complete,
                "desired_aggregate_count": len(desired_stocks),
                "desired_index_count": len(desired_indices),
                "missing_aggregates": missing_aggregates,
                "missing_indices": missing_indices,
            },
            "aggregates": aggregates,
            "indices": indices,
        }

    def health(self) -> dict[str, Any]:
        snapshot = self.overlay_snapshot()
        status = str(snapshot["status"])
        with self._lock:
            rejected_messages = self._rejected_messages
            reconnect_failures = self._reconnect_failures
            retry_after_seconds = self._retry_after_locked(self._now())
            connect_worker_active = self._connect_worker is not None
        coverage = snapshot["coverage"]
        return {
            "ok": status in {"LIVE", "EOD"},
            "ready": status in {"LIVE", "EOD"},
            "usable": status in {"LIVE", "DELAYED", "EOD"},
            "status": status,
            "transport_status": snapshot["transport_status"],
            "last_message_at": snapshot["last_message_at"],
            "quiet_seconds": snapshot["quiet_seconds"],
            "coverage_complete": coverage["complete"],
            "aggregate_count": len(snapshot["aggregates"]),
            "index_count": len(snapshot["indices"]),
            "desired_stock_count": coverage["desired_aggregate_count"],
            "desired_index_count": coverage["desired_index_count"],
            "rejected_messages": rejected_messages,
            "reconnect_failures": reconnect_failures,
            "retry_after_seconds": retry_after_seconds,
            "connect_worker_active": connect_worker_active,
        }

    def _run_connect_worker(self, completed: threading.Event) -> None:
        worker = threading.current_thread()
        provider_connected = False
        adapter = self._provider_connect_adapter
        try:
            if adapter is None:
                self._client.connect()
                provider_connected = True
            else:
                adapter.connect(
                    cancelled=self._connect_cancelled,
                    terminal=self._connect_terminal,
                )
                with self._lock:
                    provider_connected = self._transport_status in {
                        "AUTHENTICATED",
                        "STREAMING",
                    }
                if not provider_connected:
                    adapter.stop()
        except _ProviderConnectCancelled:
            if adapter is not None:
                adapter.stop()
        except Exception:
            if adapter is not None:
                adapter.stop()
            with self._lock:
                if not self._closed:
                    self._transport_status = "ERROR"
                    self._record_reconnect_failure_locked(self._now())
        finally:
            with self._lock:
                if not self._closed and self._intentional_disconnect:
                    self._transport_status = "DISCONNECTED"
                    self._sent_stock_symbols.clear()
                    self._sent_index_symbols.clear()
                    self._subscription_ids.clear()
                closed = self._closed
                if self._connect_worker is worker:
                    self._connect_worker = None
            if provider_connected and closed:
                try:
                    self._client.disconnect()
                except Exception:
                    pass
            completed.set()

    def _on_connect(self, *_args: Any) -> None:
        with self._lock:
            if self._closed:
                return
            if self._transport_status == "CONNECTING":
                self._transport_status = "CONNECTED"

    def _on_authenticated(self, *_args: Any) -> None:
        with self._lock:
            if self._closed or self._intentional_disconnect:
                self._connect_terminal.set()
                return
            if self._transport_status not in {"AUTHENTICATED", "STREAMING"}:
                self._sent_stock_symbols.clear()
                self._sent_index_symbols.clear()
            self._reconnect_failures = 0
            self._retry_not_before = None
            self._failure_incident_active = False
            self._intentional_disconnect = False
            self._transport_status = "AUTHENTICATED"
        self._connect_terminal.set()
        self._send_subscriptions()

    def _on_disconnect(self, *_args: Any) -> None:
        with self._lock:
            if self._closed:
                self._transport_status = "CLOSED"
            elif (
                self._intentional_disconnect
                and self._connect_worker is not None
                and self._provider_connect_adapter is not None
            ):
                self._transport_status = "DISCONNECTING"
            else:
                self._transport_status = "DISCONNECTED"
                if not self._intentional_disconnect:
                    self._record_reconnect_failure_locked(self._now())
            self._sent_stock_symbols.clear()
            self._sent_index_symbols.clear()
            self._subscription_ids.clear()
        self._connect_terminal.set()

    def _on_unauthenticated(self, *_args: Any) -> None:
        with self._lock:
            if self._closed or self._intentional_disconnect:
                self._connect_terminal.set()
                return
            self._transport_status = "UNAUTHENTICATED"
            if not self._intentional_disconnect:
                self._record_reconnect_failure_locked(self._now())
            self._sent_stock_symbols.clear()
            self._sent_index_symbols.clear()
            self._subscription_ids.clear()
        self._connect_terminal.set()

    def _on_error(self, *_args: Any) -> None:
        with self._lock:
            if self._closed or self._intentional_disconnect:
                self._connect_terminal.set()
                return
            self._transport_status = "ERROR"
            if not self._intentional_disconnect:
                self._record_reconnect_failure_locked(self._now())
            self._sent_stock_symbols.clear()
            self._sent_index_symbols.clear()
            self._subscription_ids.clear()
        self._connect_terminal.set()

    def _record_reconnect_failure_locked(self, now: datetime) -> None:
        if self._failure_incident_active:
            return
        self._failure_incident_active = True
        self._reconnect_failures = min(self._reconnect_failures + 1, 64)
        exponent = min(self._reconnect_failures - 1, 4)
        cooldown = min(
            _RECONNECT_MAX_SECONDS,
            _RECONNECT_INITIAL_SECONDS * (2**exponent),
        )
        self._retry_not_before = now + timedelta(seconds=cooldown)

    def _retry_after_locked(self, now: datetime) -> float:
        if self._retry_not_before is None:
            return 0.0
        return min(
            _RECONNECT_MAX_SECONDS,
            max(0.0, (self._retry_not_before - now).total_seconds()),
        )

    def _send_subscriptions(self) -> None:
        with self._lock:
            if self._closed or self._transport_status not in {
                "AUTHENTICATED",
                "STREAMING",
            }:
                return
            new_stocks = self._stock_symbols - self._sent_stock_symbols
            new_indices = self._index_symbols - self._sent_index_symbols
            self._sent_stock_symbols.update(new_stocks)
            self._sent_index_symbols.update(new_indices)
        pending = (
            ("aggregates", new_stocks, self._sent_stock_symbols),
            ("indices", new_indices, self._sent_index_symbols),
        )
        for channel, symbols, sent_symbols in pending:
            if not symbols:
                continue
            try:
                self._client.subscribe(
                    {
                        "channel": channel,
                        "symbols": sorted(symbols),
                    }
                )
            except Exception:
                with self._lock:
                    sent_symbols.difference_update(symbols)
                raise

    def _on_message(self, raw: object) -> None:
        with self._lock:
            if self._closed:
                return
        if not _raw_message_within_limits(raw):
            self._reject_message()
            return
        try:
            envelope = json.loads(raw)
        except (TypeError, ValueError, RecursionError):
            self._reject_message()
            return
        if not isinstance(envelope, dict) or not _payload_within_limits(envelope):
            self._reject_message()
            return
        raw_event = envelope.get("event")
        if (
            not isinstance(raw_event, str)
            or not raw_event.strip()
            or len(raw_event) > _MAX_EVENT_NAME_CHARS
        ):
            self._reject_message()
            return
        event = raw_event.strip()
        if event == "error":
            self._on_error()
            return
        if event == "unauthenticated":
            self._on_unauthenticated()
            return
        if event == "authenticated":
            authentication = envelope.get("data")
            if (
                not isinstance(authentication, dict)
                or not isinstance(authentication.get("message"), str)
                or not str(authentication.get("message") or "").strip()
            ):
                self._reject_message()
                return
            self._on_authenticated()
            return
        if event == "subscribed":
            raw_data = envelope.get("data")
            items = raw_data if isinstance(raw_data, list) else [raw_data]
            if not items or any(not isinstance(item, dict) for item in items):
                self._reject_message()
                return
            parsed_items: list[tuple[str, str, str]] = []
            for item in items:
                channel = str(
                    item.get("channel") or envelope.get("channel") or ""
                )
                symbol = str(item.get("symbol") or "").strip()
                subscription_id = str(
                    item.get("id") or envelope.get("id") or ""
                ).strip()
                if (
                    channel not in {"aggregates", "indices"}
                    or not _SYMBOL_RE.fullmatch(symbol)
                    or not _valid_subscription_id(subscription_id)
                ):
                    self._reject_message()
                    return
                parsed_items.append((channel, symbol, subscription_id))
            stale_ids: list[str] = []
            with self._lock:
                self._last_message_at = self._now()
                for channel, symbol, subscription_id in parsed_items:
                    desired = (
                        symbol in self._stock_symbols
                        if channel == "aggregates"
                        else symbol in self._index_symbols
                    )
                    if desired:
                        self._subscription_ids[(channel, symbol)] = subscription_id
                    else:
                        stale_ids.append(subscription_id)
            if stale_ids:
                self._client.unsubscribe({"ids": sorted(stale_ids)})
            return
        if event == "unsubscribed":
            raw_data = envelope.get("data")
            items = raw_data if isinstance(raw_data, list) else [raw_data]
            if (
                not items
                or any(not isinstance(item, dict) for item in items)
                or any(
                    not _valid_subscription_id(
                        str(item.get("id") or envelope.get("id") or "").strip()
                    )
                    for item in items
                )
            ):
                self._reject_message()
                return
            with self._lock:
                self._last_message_at = self._now()
            return
        if event in {"heartbeat", "pong"}:
            with self._lock:
                self._last_message_at = self._now()
            return
        if event != "data":
            return
        channel = str(envelope.get("channel") or "")
        if channel not in {"aggregates", "indices"}:
            self._reject_message()
            return
        data = envelope.get("data")
        if not isinstance(data, dict):
            self._reject_message()
            return
        expected_type = "EQUITY" if channel == "aggregates" else "INDEX"
        if str(data.get("type") or "").upper() != expected_type:
            self._reject_message()
            return
        symbol = str(data.get("symbol") or "").strip()
        exchange = str(data.get("exchange") or "").strip().upper()
        event_time = _epoch_microseconds(
            data.get("lastUpdated") if channel == "aggregates" else data.get("time")
        )
        aggregate_date = (
            _strict_iso_date(data.get("date"))
            if channel == "aggregates"
            else None
        )
        market_value = (
            _aggregate_market_value(data)
            if channel == "aggregates"
            else _finite(data.get("index"))
        )
        if (
            not _SYMBOL_RE.fullmatch(symbol)
            or exchange not in _SUPPORTED_EXCHANGES
            or event_time is None
            or (
                channel == "aggregates"
                and (
                    aggregate_date is None
                    or aggregate_date != event_time.date()
                )
            )
            or market_value is None
            or market_value <= 0
        ):
            self._reject_message()
            return
        now = self._now()
        if event_time > now:
            self._reject_message()
            return
        delay_seconds = _explicit_delay_seconds(
            data,
            provider_delay_seconds=self._provider_delay_seconds,
        )
        if delay_seconds is not None:
            status = "DELAYED"
        elif channel == "aggregates" and data.get("isClose") is True:
            status = "EOD"
        else:
            status = (
                "LIVE"
                if _is_live_session_event(event_time, now)
                and 0
                <= (now - event_time).total_seconds()
                <= self._freshness_seconds
                else "STALE"
            )
        normalized = _project_provider_data(channel, data)
        normalized.update(
            {
                "channel": channel,
                "status": status,
                "source_event_time": event_time.isoformat(),
                "received_at": now.isoformat(),
            }
        )
        if self._provider_delay_seconds is not None:
            normalized["provider_delay_seconds"] = self._provider_delay_seconds
        if delay_seconds is not None:
            normalized["delay_seconds"] = delay_seconds
        with self._lock:
            if self._closed or self._transport_status not in {
                "AUTHENTICATED",
                "STREAMING",
            }:
                return
            target = self._aggregates if channel == "aggregates" else self._indices
            desired_symbols = (
                self._stock_symbols
                if channel == "aggregates"
                else self._index_symbols
            )
            if symbol not in desired_symbols:
                self._rejected_messages += 1
                return
            previous = target.get(symbol)
            if previous is not None:
                previous_time = _iso_datetime(previous.get("source_event_time"))
                if previous_time is not None and event_time <= previous_time:
                    self._rejected_messages += 1
                    self._data_tainted = True
                    return
                previous_serial = _integer(previous.get("serial"))
                current_serial = _integer(data.get("serial"))
                if (
                    channel == "aggregates"
                    and previous_time is not None
                    and event_time.date() == previous_time.date()
                    and previous_serial is not None
                    and current_serial is not None
                    and current_serial <= previous_serial
                ):
                    self._rejected_messages += 1
                    self._data_tainted = True
                    return
            target[symbol] = normalized
            self._data_tainted = False
            self._last_message_at = now
            self._transport_status = "STREAMING"

    def _reject_message(self) -> None:
        with self._lock:
            self._rejected_messages += 1
            self._data_tainted = True

    def _now(self) -> datetime:
        current = self._clock()
        if current.tzinfo is None:
            return current.replace(tzinfo=TAIPEI)
        return current.astimezone(TAIPEI)


def _raw_message_within_limits(raw: object) -> bool:
    if isinstance(raw, str):
        if len(raw) > MAX_WEBSOCKET_MESSAGE_CHARS:
            return False
        try:
            return len(raw.encode("utf-8")) <= MAX_WEBSOCKET_MESSAGE_BYTES
        except UnicodeEncodeError:
            return False
    if isinstance(raw, (bytes, bytearray)):
        return len(raw) <= MAX_WEBSOCKET_MESSAGE_BYTES
    return False


def _payload_within_limits(payload: object) -> bool:
    stack: list[tuple[object, int]] = [(payload, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > _MAX_PAYLOAD_NODES or depth > _MAX_PAYLOAD_DEPTH:
            return False
        if isinstance(current, dict):
            if len(current) > _MAX_PAYLOAD_OBJECT_FIELDS:
                return False
            for key, value in current.items():
                if (
                    not isinstance(key, str)
                    or len(key) > _MAX_PAYLOAD_KEY_CHARS
                ):
                    return False
                stack.append((value, depth + 1))
        elif isinstance(current, list):
            if len(current) > _MAX_PAYLOAD_ARRAY_LENGTH:
                return False
            stack.extend((value, depth + 1) for value in current)
        elif isinstance(current, float) and not math.isfinite(current):
            return False
        elif not isinstance(current, (str, int, float, bool, type(None))):
            return False
    return True


def _project_provider_data(
    channel: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    string_fields = (
        "symbol",
        "type",
        "exchange",
        "market",
        "name",
        "date",
        "dataStatus",
    )
    aggregate_number_fields = (
        "lastPrice",
        "closePrice",
        "close",
        "referencePrice",
        "previousClose",
        "change",
        "changePercent",
        "openPrice",
        "highPrice",
        "lowPrice",
        "lastUpdated",
        "serial",
        "delaySeconds",
        "delayMinutes",
    )
    index_number_fields = (
        "index",
        "time",
        "delaySeconds",
        "delayMinutes",
    )
    for field in string_fields:
        retained = _retained_string(data.get(field))
        if retained is not None:
            projected[field] = retained
    for field in (
        aggregate_number_fields if channel == "aggregates" else index_number_fields
    ):
        retained_number = _retained_number(data.get(field))
        if retained_number is not None:
            projected[field] = retained_number
    for field in (
        ("isClose", "isDelayed")
        if channel == "aggregates"
        else ("isDelayed",)
    ):
        if isinstance(data.get(field), bool):
            projected[field] = data[field]
    if channel == "aggregates":
        _project_numeric_child(projected, data, "total", "tradeVolume")
        _project_numeric_child(projected, data, "total", "tradeValue")
        _project_numeric_child(projected, data, "lastTrade", "price")
        for field in ("bids", "asks"):
            levels = data.get(field)
            if not isinstance(levels, list) or not levels:
                continue
            first = levels[0]
            if not isinstance(first, dict):
                continue
            price = _retained_number(first.get("price"))
            if price is not None:
                projected[field] = [{"price": price}]
    return projected


def _project_numeric_child(
    target: dict[str, Any],
    source: dict[str, Any],
    parent: str,
    child: str,
) -> None:
    raw_parent = source.get(parent)
    if not isinstance(raw_parent, dict):
        return
    retained = _retained_number(raw_parent.get(child))
    if retained is not None:
        retained_parent = target.setdefault(parent, {})
        retained_parent[child] = retained


def _retained_number(value: object) -> int | float | None:
    number = _finite(value)
    if number is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return number


def _retained_string(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > _MAX_RETAINED_STRING_CHARS:
        return None
    return value


def _valid_subscription_id(value: str) -> bool:
    return bool(
        value
        and len(value) <= _MAX_SUBSCRIPTION_ID_CHARS
        and value.isprintable()
    )


def _epoch_microseconds(value: object) -> datetime | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    try:
        return datetime.fromtimestamp(
            number / 1_000_000,
            tz=timezone.utc,
        ).astimezone(TAIPEI)
    except (OSError, OverflowError, ValueError):
        return None


def _finite(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _strict_iso_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _aggregate_market_value(data: dict[str, Any]) -> float | None:
    last_trade = data.get("lastTrade")
    candidates = [
        data.get("lastPrice"),
        data.get("closePrice"),
        data.get("close"),
        last_trade.get("price") if isinstance(last_trade, dict) else None,
        data.get("referencePrice"),
    ]
    for candidate in candidates:
        number = _finite(candidate)
        if number is not None and number > 0:
            return number
    return None


def _integer(value: object) -> int | None:
    number = _finite(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _iso_datetime(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=TAIPEI)
    return parsed.astimezone(TAIPEI)


def _is_live_session_event(event_time: datetime, now: datetime) -> bool:
    return bool(
        event_time.date() == now.date()
        and event_time.weekday() < 5
        and time(9, 0) <= event_time.time() <= time(13, 40)
        and time(9, 0) <= now.time() <= time(13, 40)
    )


def _explicit_delay_seconds(
    data: dict[str, Any],
    *,
    provider_delay_seconds: float | None,
) -> float | None:
    if provider_delay_seconds is not None:
        return provider_delay_seconds
    delay_seconds = _finite(data.get("delaySeconds"))
    if delay_seconds is None:
        delay_minutes = _finite(data.get("delayMinutes"))
        if delay_minutes is not None:
            delay_seconds = delay_minutes * 60.0
    explicitly_delayed = bool(
        data.get("isDelayed") is True
        or str(data.get("dataStatus") or "").upper() == "DELAYED"
        or (delay_seconds is not None and delay_seconds > 0)
    )
    if not explicitly_delayed:
        return None
    return max(0.0, float(delay_seconds or 0.0))


def _validated_symbols(
    symbols: Iterable[str],
    *,
    kind: str,
    limit: int,
) -> set[str]:
    normalized: set[str] = set()
    for raw_symbol in symbols:
        symbol = str(raw_symbol).strip()
        if not _SYMBOL_RE.fullmatch(symbol):
            raise ValueError(f"invalid {kind} symbol")
        normalized.add(symbol)
        if len(normalized) > limit:
            raise ValueError(f"{kind} subscription limit is {limit}")
    return normalized
