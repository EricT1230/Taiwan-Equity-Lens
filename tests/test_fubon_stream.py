from __future__ import annotations

import json
import threading
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from taiwan_stock_analysis.fubon_stream import (
    FubonWebSocketFeed,
    resolve_fubon_websocket_index_symbol,
)
from taiwan_stock_analysis.trading_calendar import TAIPEI


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs: float) -> None:
        self.value += timedelta(**kwargs)


class FakeWebSocketClient:
    def __init__(self) -> None:
        self.handlers: dict[str, list] = {}
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.subscribe_calls: list[dict] = []
        self.unsubscribe_calls: list[dict] = []
        self.connect_error: Exception | None = None

    def on(self, event: str, callback) -> None:
        self.handlers.setdefault(event, []).append(callback)

    def emit(self, event: str, *args) -> None:
        for callback in tuple(self.handlers.get(event, ())):
            callback(*args)

    def connect(self) -> None:
        self.connect_calls += 1
        if self.connect_error is not None:
            raise self.connect_error
        self.emit("connect")
        self.message(
            {
                "event": "authenticated",
                "data": {"message": "Authenticated successfully"},
            }
        )

    def disconnect(self) -> None:
        self.disconnect_calls += 1
        self.emit("disconnect", 1000, "normal")

    def subscribe(self, payload: dict) -> None:
        self.subscribe_calls.append(payload)

    def unsubscribe(self, payload: dict) -> None:
        self.unsubscribe_calls.append(payload)

    def message(self, payload: dict, *, add_aggregate_date: bool = True) -> None:
        safe_payload = dict(payload)
        raw_data = payload.get("data")
        if (
            add_aggregate_date
            and payload.get("event") == "data"
            and payload.get("channel") == "aggregates"
            and isinstance(raw_data, dict)
            and "date" not in raw_data
        ):
            data = dict(raw_data)
            try:
                event_time = datetime.fromtimestamp(
                    float(data.get("lastUpdated")) / 1_000_000,
                    tz=TAIPEI,
                )
            except (TypeError, ValueError, OverflowError, OSError):
                pass
            else:
                data["date"] = event_time.date().isoformat()
                safe_payload["data"] = data
        self.emit("message", json.dumps(safe_payload))


class OfficialMessageAuthClient(FakeWebSocketClient):
    """Explicit test name for the SDK's documented delivery shape."""

    pass


class CallbackOnlyAuthClient(FakeWebSocketClient):
    def connect(self) -> None:
        self.connect_calls += 1
        self.emit("connect")
        self.emit("authenticated")


class BlockingConnectClient(FakeWebSocketClient):
    def __init__(self) -> None:
        super().__init__()
        self.connect_entered = threading.Event()
        self.release_connect = threading.Event()

    def connect(self) -> None:
        self.connect_calls += 1
        self.emit("connect")
        self.connect_entered.set()
        self.release_connect.wait(timeout=5)
        self.message(
            {
                "event": "authenticated",
                "data": {"message": "Authenticated successfully"},
            }
        )

    def disconnect(self) -> None:
        self.disconnect_calls += 1
        self.release_connect.wait(timeout=5)
        self.emit("disconnect", 1000, "normal")


class FakeFugleWebSocketApp:
    """Model the SDK socket runner without invoking its legacy busy loop."""

    def __init__(self, client: "LegacyBusySpinFugleClient") -> None:
        self.client = client
        self.run_calls = 0
        self.run_entered = threading.Event()
        self.run_exited = threading.Event()
        self.stop_requested = threading.Event()

    def run_forever(self) -> None:
        self.run_calls += 1
        self.run_entered.set()
        self.run_exited.clear()
        self.stop_requested.clear()
        behavior = self.client.behaviors.pop(0)
        try:
            if behavior == "pre-open-error":
                self.client.emit("error", RuntimeError("pre-open failure"))
                return
            if behavior in {"authenticated", "authenticated-delayed-stop"}:
                self.client.emit("connect")
                self.client.message(
                    {
                        "event": "authenticated",
                        "data": {"message": "Authenticated successfully"},
                    }
                )
            self.stop_requested.wait(timeout=5)
            if behavior in {"delayed-stop", "authenticated-delayed-stop"}:
                time.sleep(1.6)
        finally:
            self.run_exited.set()

    def close(self) -> None:
        self.stop_requested.set()


class LegacyBusySpinFugleClient(FakeWebSocketClient):
    """Replicate the installed SDK's pre-open ``connect`` failure mode."""

    def __init__(self, *behaviors: str) -> None:
        super().__init__()
        self.behaviors = list(behaviors)
        self.legacy_connect_calls = 0
        self.legacy_connect_release = threading.Event()
        self.socket = FakeFugleWebSocketApp(self)
        setattr(self, "_WebSocketClient__ws", self.socket)

    def connect(self) -> None:
        # The installed SDK spins here.  This safe stand-in blocks instead so
        # a regression still fails without burning a test runner CPU core.
        self.legacy_connect_calls += 1
        self.legacy_connect_release.wait(timeout=5)

    def disconnect(self) -> None:
        self.disconnect_calls += 1
        self.socket.close()
        self.emit("disconnect", 1000, "normal")


LegacyBusySpinFugleClient.__module__ = "fugle_marketdata.websocket.stock.client"


class SilentDisconnectFugleClient(LegacyBusySpinFugleClient):
    """Model a pre-open SDK close that never emits a disconnect callback."""

    def disconnect(self) -> None:
        self.disconnect_calls += 1
        self.socket.close()


SilentDisconnectFugleClient.__module__ = "fugle_marketdata.websocket.stock.client"


def epoch_microseconds(value: datetime) -> int:
    return int(value.timestamp() * 1_000_000)


class FubonIndexSymbolTests(unittest.TestCase):
    def test_resolver_uses_only_evidence_backed_rest_to_websocket_mappings(self) -> None:
        self.assertEqual("IR0001", resolve_fubon_websocket_index_symbol("IX0001"))
        self.assertEqual("IR0043", resolve_fubon_websocket_index_symbol("IX0043"))
        self.assertEqual("IR0001", resolve_fubon_websocket_index_symbol("IR0001"))
        self.assertEqual("IX9999", resolve_fubon_websocket_index_symbol("IX9999"))

    def test_resolver_allows_explicit_validated_override(self) -> None:
        self.assertEqual(
            "IR9001",
            resolve_fubon_websocket_index_symbol(
                "IX9001",
                overrides={"IX9001": "IR9001"},
            ),
        )

    def test_resolver_rejects_invalid_override_without_guessing(self) -> None:
        for overrides in (
            {"../IX9001": "IR9001"},
            {"IX9001": "../IR9001"},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(ValueError, "override"):
                    resolve_fubon_websocket_index_symbol(
                        "IX9001",
                        overrides=overrides,
                    )


class FubonWebSocketFeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = MutableClock(datetime(2026, 8, 28, 10, 0, tzinfo=TAIPEI))
        self.client = FakeWebSocketClient()
        self.feed = FubonWebSocketFeed(
            self.client,
            clock=self.clock,
            freshness_seconds=120,
            silence_seconds=45,
        )

    def test_fresh_aggregate_is_live_after_authenticated_subscription(self) -> None:
        self.feed.subscribe(stock_symbols=["2330"])
        self.feed.connect()

        self.assertEqual(
            [{"channel": "aggregates", "symbols": ["2330"]}],
            self.client.subscribe_calls,
        )

        self.client.message(
            {
                "event": "data",
                "channel": "aggregates",
                "id": "aggregate-2330",
                "data": {
                    "symbol": "2330",
                    "type": "EQUITY",
                    "exchange": "TWSE",
                    "lastPrice": 1180.0,
                    "lastUpdated": epoch_microseconds(self.clock()),
                    "serial": 101,
                },
            }
        )

        snapshot = self.feed.overlay_snapshot()
        self.assertEqual("LIVE", snapshot["status"])
        self.assertEqual("LIVE", snapshot["aggregates"]["2330"]["status"])
        self.assertEqual(1180.0, snapshot["aggregates"]["2330"]["lastPrice"])

    def test_official_authenticated_message_triggers_pending_subscriptions(self) -> None:
        client = OfficialMessageAuthClient()
        feed = FubonWebSocketFeed(client, clock=self.clock)
        feed.subscribe(stock_symbols=["2330"], index_symbols=["IR0001"])

        feed.connect()

        self.assertEqual("AUTHENTICATED", feed.health()["transport_status"])
        self.assertEqual(
            [
                {"channel": "aggregates", "symbols": ["2330"]},
                {"channel": "indices", "symbols": ["IR0001"]},
            ],
            client.subscribe_calls,
        )

    def test_authenticated_callback_cannot_bypass_message_validation(self) -> None:
        client = CallbackOnlyAuthClient()
        feed = FubonWebSocketFeed(client, clock=self.clock)
        feed.subscribe(stock_symbols=["2330"])

        feed.connect()
        client.message({"event": "authenticated", "data": "malformed"})
        client.emit("authenticated")

        self.assertEqual("CONNECTED", feed.health()["transport_status"])
        self.assertEqual([], client.subscribe_calls)
        self.assertEqual(1, feed.health()["rejected_messages"])

    def test_blocked_provider_connect_uses_one_daemon_worker_and_close_is_prompt(
        self,
    ) -> None:
        client = BlockingConnectClient()
        feed = FubonWebSocketFeed(client, clock=self.clock)
        feed.subscribe(stock_symbols=["2330"])
        connect_returned = threading.Event()
        close_returned = threading.Event()

        def call_connect() -> None:
            feed.connect()
            connect_returned.set()

        def call_close() -> None:
            feed.close()
            close_returned.set()

        connect_caller = threading.Thread(target=call_connect)
        close_caller = threading.Thread(target=call_close)
        try:
            connect_caller.start()
            self.assertTrue(client.connect_entered.wait(timeout=0.5))
            self.assertTrue(connect_returned.wait(timeout=0.2))

            feed.connect()
            self.assertEqual(1, client.connect_calls)
            self.assertTrue(feed.health()["connect_worker_active"])

            started = time.perf_counter()
            snapshot = feed.overlay_snapshot()
            self.assertLess(time.perf_counter() - started, 0.1)
            self.assertEqual("CONNECTED", snapshot["transport_status"])

            close_caller.start()
            self.assertTrue(close_returned.wait(timeout=0.2))
            self.assertEqual("CLOSED", feed.health()["transport_status"])
            self.assertTrue(feed.health()["connect_worker_active"])
        finally:
            client.release_connect.set()
            connect_caller.join(timeout=1)
            if close_caller.ident is not None:
                close_caller.join(timeout=1)
        deadline = time.perf_counter() + 1
        while feed.health()["connect_worker_active"] and time.perf_counter() < deadline:
            time.sleep(0.005)
        self.assertFalse(feed.health()["connect_worker_active"])
        self.assertEqual([], client.subscribe_calls)

    def test_fugle_pre_open_failure_terminates_and_allows_retry(self) -> None:
        client = LegacyBusySpinFugleClient(
            "pre-open-error",
            "authenticated",
        )
        feed = FubonWebSocketFeed(client, clock=self.clock)
        feed.subscribe(stock_symbols=["2330"])

        feed.connect()

        deadline = time.perf_counter() + 1
        while feed.health()["connect_worker_active"] and time.perf_counter() < deadline:
            time.sleep(0.005)
        self.assertFalse(feed.health()["connect_worker_active"])
        self.assertEqual(0, client.legacy_connect_calls)
        self.assertEqual(1, client.socket.run_calls)
        self.assertEqual(1, feed.health()["reconnect_failures"])

        self.clock.advance(seconds=5)
        feed.connect()

        deadline = time.perf_counter() + 1
        while feed.health()["connect_worker_active"] and time.perf_counter() < deadline:
            time.sleep(0.005)
        self.assertFalse(feed.health()["connect_worker_active"])
        self.assertEqual(0, client.legacy_connect_calls)
        self.assertEqual(2, client.socket.run_calls)
        self.assertEqual("AUTHENTICATED", feed.health()["transport_status"])
        self.assertEqual(
            [{"channel": "aggregates", "symbols": ["2330"]}],
            client.subscribe_calls,
        )
        feed.close()

    def test_close_cancels_fugle_pre_open_connect_without_leaking_worker(
        self,
    ) -> None:
        client = LegacyBusySpinFugleClient("blocked-before-open")
        feed = FubonWebSocketFeed(client, clock=self.clock)

        feed.connect()
        self.assertTrue(client.socket.run_entered.wait(timeout=0.5))
        self.assertTrue(feed.health()["connect_worker_active"])

        started = time.perf_counter()
        feed.close()
        self.assertLess(time.perf_counter() - started, 0.2)

        deadline = time.perf_counter() + 1
        while feed.health()["connect_worker_active"] and time.perf_counter() < deadline:
            time.sleep(0.005)
        self.assertFalse(feed.health()["connect_worker_active"])
        self.assertTrue(client.socket.run_exited.wait(timeout=0.5))
        self.assertEqual(0, client.legacy_connect_calls)
        self.assertEqual(1, client.disconnect_calls)
        self.assertEqual("CLOSED", feed.health()["transport_status"])

    def test_disconnect_finalizes_silent_pre_open_cancel_and_allows_retry(
        self,
    ) -> None:
        client = SilentDisconnectFugleClient(
            "blocked-before-open",
            "authenticated",
        )
        feed = FubonWebSocketFeed(client, clock=self.clock)
        feed.subscribe(stock_symbols=["2330"])

        feed.connect()
        self.assertTrue(client.socket.run_entered.wait(timeout=0.5))

        started = time.perf_counter()
        feed.disconnect()
        self.assertLess(time.perf_counter() - started, 0.2)

        deadline = time.perf_counter() + 1
        while feed.health()["connect_worker_active"] and time.perf_counter() < deadline:
            time.sleep(0.005)
        self.assertFalse(feed.health()["connect_worker_active"])
        self.assertTrue(client.socket.run_exited.wait(timeout=0.5))
        self.assertEqual("DISCONNECTED", feed.health()["transport_status"])
        self.assertEqual(0, feed.health()["reconnect_failures"])

        client.emit("connect")
        client.message(
            {
                "event": "authenticated",
                "data": {"message": "late authentication"},
            }
        )
        client.emit("error", RuntimeError("late error"))
        client.emit("unauthenticated")
        self.assertEqual("DISCONNECTED", feed.health()["transport_status"])
        self.assertEqual([], client.subscribe_calls)

        feed.connect()
        deadline = time.perf_counter() + 1
        while feed.health()["connect_worker_active"] and time.perf_counter() < deadline:
            time.sleep(0.005)
        self.assertFalse(feed.health()["connect_worker_active"])
        self.assertEqual(2, client.socket.run_calls)
        self.assertEqual("AUTHENTICATED", feed.health()["transport_status"])
        self.assertEqual(
            [{"channel": "aggregates", "symbols": ["2330"]}],
            client.subscribe_calls,
        )
        feed.close()

    def test_disconnect_waits_for_delayed_provider_runner_before_reconnect(
        self,
    ) -> None:
        client = SilentDisconnectFugleClient(
            "delayed-stop",
            "authenticated",
        )
        feed = FubonWebSocketFeed(client, clock=self.clock)
        feed.subscribe(stock_symbols=["2330"])

        feed.connect()
        self.assertTrue(client.socket.run_entered.wait(timeout=0.5))

        started = time.perf_counter()
        feed.disconnect()
        self.assertLess(time.perf_counter() - started, 0.2)
        self.assertEqual("DISCONNECTING", feed.health()["transport_status"])
        self.assertTrue(feed.health()["connect_worker_active"])

        feed.connect()
        health = feed.health()
        self.assertEqual("DISCONNECTING", health["transport_status"])
        self.assertTrue(health["connect_worker_active"])
        self.assertEqual(0, health["reconnect_failures"])
        self.assertEqual(1, client.socket.run_calls)

        time.sleep(0.4)
        self.assertFalse(client.socket.run_exited.is_set())
        health = feed.health()
        self.assertEqual("DISCONNECTING", health["transport_status"])
        self.assertTrue(health["connect_worker_active"])
        self.assertEqual(0, health["reconnect_failures"])

        self.assertTrue(client.socket.run_exited.wait(timeout=2.5))
        deadline = time.perf_counter() + 1
        while feed.health()["connect_worker_active"] and time.perf_counter() < deadline:
            time.sleep(0.005)
        self.assertFalse(feed.health()["connect_worker_active"])
        self.assertEqual("DISCONNECTED", feed.health()["transport_status"])
        self.assertEqual(0, feed.health()["reconnect_failures"])

        feed.connect()
        deadline = time.perf_counter() + 1
        while feed.health()["connect_worker_active"] and time.perf_counter() < deadline:
            time.sleep(0.005)
        self.assertFalse(feed.health()["connect_worker_active"])
        self.assertEqual(2, client.socket.run_calls)
        self.assertEqual("AUTHENTICATED", feed.health()["transport_status"])
        self.assertEqual(
            [{"channel": "aggregates", "symbols": ["2330"]}],
            client.subscribe_calls,
        )
        feed.close()

    def test_authenticated_disconnect_waits_for_runner_before_reconnect(
        self,
    ) -> None:
        client = SilentDisconnectFugleClient(
            "authenticated-delayed-stop",
            "authenticated",
        )
        feed = FubonWebSocketFeed(client, clock=self.clock)
        feed.subscribe(stock_symbols=["2330"])

        feed.connect()
        deadline = time.perf_counter() + 1
        while feed.health()["connect_worker_active"] and time.perf_counter() < deadline:
            time.sleep(0.005)
        self.assertFalse(feed.health()["connect_worker_active"])
        self.assertEqual("AUTHENTICATED", feed.health()["transport_status"])
        self.assertFalse(client.socket.run_exited.is_set())

        started = time.perf_counter()
        feed.disconnect()
        self.assertLess(time.perf_counter() - started, 0.2)
        self.assertEqual("DISCONNECTING", feed.health()["transport_status"])
        self.assertTrue(feed.health()["connect_worker_active"])

        feed.connect()
        health = feed.health()
        self.assertEqual("DISCONNECTING", health["transport_status"])
        self.assertTrue(health["connect_worker_active"])
        self.assertEqual(0, health["reconnect_failures"])
        self.assertEqual(1, client.socket.run_calls)

        time.sleep(0.4)
        self.assertFalse(client.socket.run_exited.is_set())
        health = feed.health()
        self.assertEqual("DISCONNECTING", health["transport_status"])
        self.assertTrue(health["connect_worker_active"])
        self.assertEqual(0, health["reconnect_failures"])

        self.assertTrue(client.socket.run_exited.wait(timeout=2.5))
        deadline = time.perf_counter() + 1
        while feed.health()["connect_worker_active"] and time.perf_counter() < deadline:
            time.sleep(0.005)
        self.assertFalse(feed.health()["connect_worker_active"])
        self.assertEqual("DISCONNECTED", feed.health()["transport_status"])
        self.assertEqual(0, feed.health()["reconnect_failures"])

        feed.connect()
        deadline = time.perf_counter() + 1
        while feed.health()["connect_worker_active"] and time.perf_counter() < deadline:
            time.sleep(0.005)
        self.assertFalse(feed.health()["connect_worker_active"])
        self.assertEqual(2, client.socket.run_calls)
        self.assertEqual("AUTHENTICATED", feed.health()["transport_status"])
        self.assertEqual(
            [
                {"channel": "aggregates", "symbols": ["2330"]},
                {"channel": "aggregates", "symbols": ["2330"]},
            ],
            client.subscribe_calls,
        )
        feed.close()

    def test_authenticated_disconnect_cleanup_start_failure_is_terminal(
        self,
    ) -> None:
        client = SilentDisconnectFugleClient(
            "authenticated",
            "authenticated",
        )
        feed = FubonWebSocketFeed(client, clock=self.clock)
        feed.subscribe(stock_symbols=["2330"])
        feed.connect()
        self.assertEqual("AUTHENTICATED", feed.health()["transport_status"])

        started = time.perf_counter()
        with patch.object(
            threading.Thread,
            "start",
            side_effect=RuntimeError("credential-shaped thread failure"),
        ):
            feed.disconnect()
        self.assertLess(time.perf_counter() - started, 0.2)

        health = feed.health()
        self.assertEqual("ERROR", health["transport_status"])
        self.assertFalse(health["connect_worker_active"])
        self.assertEqual(1, health["reconnect_failures"])
        self.assertEqual(5.0, health["retry_after_seconds"])
        self.assertNotIn("credential-shaped", json.dumps(health))
        self.assertEqual(1, client.disconnect_calls)
        self.assertTrue(client.socket.run_exited.wait(timeout=0.5))

        feed.connect()
        self.assertEqual(1, client.socket.run_calls)
        self.clock.advance(seconds=5)
        feed.connect()
        deadline = time.perf_counter() + 1
        while feed.health()["connect_worker_active"] and time.perf_counter() < deadline:
            time.sleep(0.005)
        self.assertFalse(feed.health()["connect_worker_active"])
        self.assertEqual(2, client.socket.run_calls)
        self.assertEqual("AUTHENTICATED", feed.health()["transport_status"])
        feed.close()

    def test_fresh_index_is_live_and_saved_separately(self) -> None:
        self.feed.subscribe(index_symbols=["IR0001"])
        self.feed.connect()

        self.assertEqual(
            [{"channel": "indices", "symbols": ["IR0001"]}],
            self.client.subscribe_calls,
        )

        self.client.message(
            {
                "event": "data",
                "channel": "indices",
                "id": "index-twse",
                "data": {
                    "symbol": "IR0001",
                    "type": "INDEX",
                    "exchange": "TWSE",
                    "index": 24980.25,
                    "time": epoch_microseconds(self.clock()),
                },
            }
        )

        snapshot = self.feed.overlay_snapshot()
        self.assertEqual("LIVE", snapshot["status"])
        self.assertEqual("LIVE", snapshot["indices"]["IR0001"]["status"])
        self.assertEqual(24980.25, snapshot["indices"]["IR0001"]["index"])

    def test_non_finite_market_value_is_rejected_as_malformed(self) -> None:
        self.feed.connect()
        self.client.message(
            {
                "event": "data",
                "channel": "aggregates",
                "id": "bad-aggregate",
                "data": {
                    "symbol": "2330",
                    "type": "EQUITY",
                    "exchange": "TWSE",
                    "lastPrice": float("nan"),
                    "lastUpdated": epoch_microseconds(self.clock()),
                    "serial": 102,
                },
            }
        )

        snapshot = self.feed.overlay_snapshot()
        self.assertEqual("UNAVAILABLE", snapshot["status"])
        self.assertEqual({}, snapshot["aggregates"])

    def test_zero_market_value_is_rejected_instead_of_filling_missing_quote(self) -> None:
        self.feed.connect()
        self.client.message(
            {
                "event": "data",
                "channel": "indices",
                "data": {
                    "symbol": "IR0001",
                    "type": "INDEX",
                    "exchange": "TWSE",
                    "index": 0,
                    "time": epoch_microseconds(self.clock()),
                },
            }
        )

        snapshot = self.feed.overlay_snapshot()
        self.assertEqual("UNAVAILABLE", snapshot["status"])
        self.assertEqual({}, snapshot["indices"])

    def test_future_event_is_rejected_without_overwriting_valid_quote(self) -> None:
        self.feed.subscribe(stock_symbols=["2330"])
        self.feed.connect()
        self.client.message(
            {
                "event": "data",
                "channel": "aggregates",
                "data": {
                    "symbol": "2330",
                    "type": "EQUITY",
                    "exchange": "TWSE",
                    "lastPrice": 1180.0,
                    "lastUpdated": epoch_microseconds(self.clock()),
                    "serial": 101,
                },
            }
        )
        self.client.message(
            {
                "event": "data",
                "channel": "aggregates",
                "data": {
                    "symbol": "2330",
                    "type": "EQUITY",
                    "exchange": "TWSE",
                    "lastPrice": 9999.0,
                    "lastUpdated": epoch_microseconds(
                        self.clock() + timedelta(minutes=1)
                    ),
                    "serial": 102,
                },
            }
        )

        snapshot = self.feed.overlay_snapshot()
        row = snapshot["aggregates"]["2330"]
        self.assertEqual(1180.0, row["lastPrice"])
        self.assertEqual(101, row["serial"])
        self.assertEqual("STALE", snapshot["status"])
        self.assertEqual("STALE", row["status"])

        self.clock.advance(seconds=1)
        self.client.message(
            {
                "event": "data",
                "channel": "aggregates",
                "data": {
                    "symbol": "2330",
                    "type": "EQUITY",
                    "exchange": "TWSE",
                    "lastPrice": 1181.0,
                    "lastUpdated": epoch_microseconds(self.clock()),
                    "serial": 103,
                },
            }
        )
        recovered = self.feed.overlay_snapshot()
        self.assertEqual("LIVE", recovered["status"])
        self.assertEqual(1181.0, recovered["aggregates"]["2330"]["lastPrice"])

    def test_aggregate_requires_date_matching_last_updated_taipei_date(self) -> None:
        for supplied_date in (None, "2026-08-27", "2026-8-28", "invalid"):
            with self.subTest(supplied_date=supplied_date):
                client = FakeWebSocketClient()
                feed = FubonWebSocketFeed(client, clock=self.clock)
                feed.subscribe(stock_symbols=["2330"])
                feed.connect()
                data = {
                    "symbol": "2330",
                    "type": "EQUITY",
                    "exchange": "TWSE",
                    "lastPrice": 1180.0,
                    "lastUpdated": epoch_microseconds(self.clock()),
                    "serial": 101,
                }
                if supplied_date is not None:
                    data["date"] = supplied_date

                client.message(
                    {
                        "event": "data",
                        "channel": "aggregates",
                        "data": data,
                    },
                    add_aggregate_date=False,
                )

                snapshot = feed.overlay_snapshot()
                self.assertEqual("STALE", snapshot["status"])
                self.assertEqual({}, snapshot["aggregates"])
                self.assertEqual(1, feed.health()["rejected_messages"])

    def test_huge_json_integer_never_escapes_message_callback(self) -> None:
        huge_integer = int("9" * 4000)
        for field in ("lastUpdated", "lastPrice"):
            with self.subTest(field=field):
                client = FakeWebSocketClient()
                feed = FubonWebSocketFeed(client, clock=self.clock)
                feed.subscribe(stock_symbols=["2330"])
                feed.connect()
                client.message(
                    {
                        "event": "data",
                        "channel": "aggregates",
                        "data": {
                            "symbol": "2330",
                            "type": "EQUITY",
                            "exchange": "TWSE",
                            "date": self.clock().date().isoformat(),
                            "lastPrice": (
                                huge_integer if field == "lastPrice" else 1180.0
                            ),
                            "lastUpdated": (
                                huge_integer
                                if field == "lastUpdated"
                                else epoch_microseconds(self.clock())
                            ),
                            "serial": 101,
                        },
                    },
                    add_aggregate_date=False,
                )

                snapshot = feed.overlay_snapshot()
                self.assertEqual("STALE", snapshot["status"])
                self.assertEqual({}, snapshot["aggregates"])
                self.assertEqual(1, feed.health()["rejected_messages"])

    def test_regressing_aggregate_serial_is_rejected(self) -> None:
        self.feed.subscribe(stock_symbols=["2330"])
        self.feed.connect()
        for seconds_ago, price, serial in ((10, 1180.0, 102), (5, 1170.0, 101)):
            self.client.message(
                {
                    "event": "data",
                    "channel": "aggregates",
                    "data": {
                        "symbol": "2330",
                        "type": "EQUITY",
                        "exchange": "TWSE",
                        "lastPrice": price,
                        "lastUpdated": epoch_microseconds(
                            self.clock() - timedelta(seconds=seconds_ago)
                        ),
                        "serial": serial,
                    },
                }
            )

        snapshot = self.feed.overlay_snapshot()
        row = snapshot["aggregates"]["2330"]
        self.assertEqual(1180.0, row["lastPrice"])
        self.assertEqual(102, row["serial"])
        self.assertEqual("STALE", snapshot["status"])
        self.assertEqual("STALE", row["status"])

        self.client.message(
            {
                "event": "data",
                "channel": "aggregates",
                "data": {
                    "symbol": "2330",
                    "type": "EQUITY",
                    "exchange": "TWSE",
                    "lastPrice": 1182.0,
                    "lastUpdated": epoch_microseconds(self.clock()),
                    "serial": 103,
                },
            }
        )
        self.assertEqual("LIVE", self.feed.overlay_snapshot()["status"])

    def test_explicit_close_evidence_is_eod(self) -> None:
        self.clock.value = datetime(2026, 8, 28, 14, 10, tzinfo=TAIPEI)
        self.feed.subscribe(stock_symbols=["2330"])
        self.feed.connect()
        self.client.message(
            {
                "event": "data",
                "channel": "aggregates",
                "data": {
                    "symbol": "2330",
                    "type": "EQUITY",
                    "exchange": "TWSE",
                    "lastPrice": 1190.0,
                    "lastUpdated": epoch_microseconds(
                        datetime(2026, 8, 28, 13, 31, tzinfo=TAIPEI)
                    ),
                    "serial": 999,
                    "isClose": True,
                },
            }
        )

        snapshot = self.feed.overlay_snapshot()
        self.assertEqual("EOD", snapshot["status"])
        self.assertEqual("EOD", snapshot["aggregates"]["2330"]["status"])

    def test_payload_must_explicitly_mark_delayed_market_data(self) -> None:
        self.feed.subscribe(stock_symbols=["2330"])
        self.feed.connect()
        self.client.message(
            {
                "event": "data",
                "channel": "aggregates",
                "data": {
                    "symbol": "2330",
                    "type": "EQUITY",
                    "exchange": "TWSE",
                    "lastPrice": 1180.0,
                    "lastUpdated": epoch_microseconds(self.clock()),
                    "serial": 101,
                    "isDelayed": True,
                },
            }
        )

        snapshot = self.feed.overlay_snapshot()
        self.assertEqual("DELAYED", snapshot["status"])
        self.assertEqual("DELAYED", snapshot["aggregates"]["2330"]["status"])

    def test_provider_metadata_can_explicitly_mark_delayed_feed(self) -> None:
        client = FakeWebSocketClient()
        feed = FubonWebSocketFeed(
            client,
            clock=self.clock,
            provider_delay_seconds=900,
        )
        feed.subscribe(index_symbols=["IR0001"])
        feed.connect()
        client.message(
            {
                "event": "data",
                "channel": "indices",
                "data": {
                    "symbol": "IR0001",
                    "type": "INDEX",
                    "exchange": "TWSE",
                    "index": 24980.25,
                    "time": epoch_microseconds(self.clock()),
                },
            }
        )

        row = feed.overlay_snapshot()["indices"]["IR0001"]
        self.assertEqual("DELAYED", row["status"])
        self.assertEqual(900.0, row["provider_delay_seconds"])

    def test_disconnect_demotes_existing_live_data_to_stale(self) -> None:
        self.feed.subscribe(index_symbols=["IR0001"])
        self.feed.connect()
        self.client.message(
            {
                "event": "data",
                "channel": "indices",
                "data": {
                    "symbol": "IR0001",
                    "type": "INDEX",
                    "exchange": "TWSE",
                    "index": 24980.25,
                    "time": epoch_microseconds(self.clock()),
                },
            }
        )
        self.client.disconnect()

        snapshot = self.feed.overlay_snapshot()
        self.assertEqual("STALE", snapshot["status"])
        self.assertEqual("STALE", snapshot["indices"]["IR0001"]["status"])
        self.assertEqual("STALE", self.feed.health()["status"])

    def test_overlay_recomputes_event_age_from_current_clock(self) -> None:
        client = FakeWebSocketClient()
        feed = FubonWebSocketFeed(
            client,
            clock=self.clock,
            freshness_seconds=30,
            silence_seconds=300,
        )
        feed.subscribe(index_symbols=["IR0001"])
        feed.connect()
        client.message(
            {
                "event": "data",
                "channel": "indices",
                "data": {
                    "symbol": "IR0001",
                    "type": "INDEX",
                    "exchange": "TWSE",
                    "index": 24980.25,
                    "time": epoch_microseconds(self.clock()),
                },
            }
        )
        self.clock.advance(seconds=31)

        row = feed.overlay_snapshot()["indices"]["IR0001"]
        self.assertEqual("STALE", row["status"])
        self.assertEqual(31.0, row["age_seconds"])

    def test_transport_silence_demotes_otherwise_fresh_event(self) -> None:
        client = FakeWebSocketClient()
        feed = FubonWebSocketFeed(
            client,
            clock=self.clock,
            freshness_seconds=300,
            silence_seconds=30,
        )
        feed.subscribe(index_symbols=["IR0001"])
        feed.connect()
        client.message(
            {
                "event": "data",
                "channel": "indices",
                "data": {
                    "symbol": "IR0001",
                    "type": "INDEX",
                    "exchange": "TWSE",
                    "index": 24980.25,
                    "time": epoch_microseconds(self.clock()),
                },
            }
        )
        self.clock.advance(seconds=31)

        snapshot = feed.overlay_snapshot()
        self.assertEqual("STALE", snapshot["status"])
        self.assertEqual(31.0, feed.health()["quiet_seconds"])

    def test_heartbeat_refreshes_transport_silence_only(self) -> None:
        client = FakeWebSocketClient()
        feed = FubonWebSocketFeed(
            client,
            clock=self.clock,
            freshness_seconds=300,
            silence_seconds=30,
        )
        feed.subscribe(index_symbols=["IR0001"])
        feed.connect()
        client.message(
            {
                "event": "data",
                "channel": "indices",
                "data": {
                    "symbol": "IR0001",
                    "type": "INDEX",
                    "exchange": "TWSE",
                    "index": 24980.25,
                    "time": epoch_microseconds(self.clock()),
                },
            }
        )
        self.clock.advance(seconds=25)
        client.message({"event": "heartbeat"})
        self.clock.advance(seconds=20)

        snapshot = feed.overlay_snapshot()
        self.assertEqual("LIVE", snapshot["status"])
        self.assertEqual(20.0, snapshot["quiet_seconds"])
        self.assertEqual(45.0, snapshot["indices"]["IR0001"]["age_seconds"])

    def test_error_and_unauthenticated_callbacks_demote_live_data(self) -> None:
        for event, args, expected_transport in (
            ("error", (RuntimeError("credential-shaped detail"),), "ERROR"),
            ("unauthenticated", (), "UNAUTHENTICATED"),
        ):
            with self.subTest(event=event):
                client = FakeWebSocketClient()
                feed = FubonWebSocketFeed(client, clock=self.clock)
                feed.subscribe(index_symbols=["IR0001"])
                feed.connect()
                client.message(
                    {
                        "event": "data",
                        "channel": "indices",
                        "data": {
                            "symbol": "IR0001",
                            "type": "INDEX",
                            "exchange": "TWSE",
                            "index": 24980.25,
                            "time": epoch_microseconds(self.clock()),
                        },
                    }
                )
                client.emit(event, *args)

                health = feed.health()
                self.assertEqual("STALE", health["status"])
                self.assertEqual(expected_transport, health["transport_status"])
                self.assertNotIn("credential-shaped detail", json.dumps(health))

    def test_stock_subscription_limit_is_180_and_fails_closed(self) -> None:
        allowed = [f"{index:04d}" for index in range(180)]
        self.feed.subscribe(stock_symbols=allowed)

        with self.assertRaisesRegex(ValueError, "180"):
            self.feed.subscribe(stock_symbols=["9999"])

        self.feed.connect()
        subscribed = self.client.subscribe_calls[0]
        self.assertEqual("aggregates", subscribed["channel"])
        self.assertEqual(180, len(subscribed["symbols"]))
        self.assertNotIn("9999", subscribed["symbols"])

    def test_index_subscription_limit_is_16_and_fails_closed(self) -> None:
        allowed = [f"IR{index:04d}" for index in range(16)]
        self.feed.subscribe(index_symbols=allowed)

        with self.assertRaisesRegex(ValueError, "index subscription limit is 16"):
            self.feed.subscribe(index_symbols=["IR9999"])

        self.feed.connect()
        subscribed = self.client.subscribe_calls[0]
        self.assertEqual("indices", subscribed["channel"])
        self.assertEqual(16, len(subscribed["symbols"]))
        self.assertNotIn("IR9999", subscribed["symbols"])

    def test_subscribe_sends_only_new_symbols(self) -> None:
        self.feed.connect()
        self.feed.subscribe(
            stock_symbols=["2330", "2317"],
            index_symbols=["IR0001"],
        )
        self.feed.subscribe(
            stock_symbols=["2330", "2454"],
            index_symbols=["IR0001"],
        )

        self.assertEqual(
            [
                {"channel": "aggregates", "symbols": ["2317", "2330"]},
                {"channel": "indices", "symbols": ["IR0001"]},
                {"channel": "aggregates", "symbols": ["2454"]},
            ],
            self.client.subscribe_calls,
        )

    def test_unsubscribe_uses_acknowledged_ids_and_only_removes_difference(self) -> None:
        self.feed.connect()
        self.feed.subscribe(stock_symbols=["2330", "2317"])
        self.client.message(
            {
                "event": "subscribed",
                "data": {
                    "id": "aggregate-2330",
                    "channel": "aggregates",
                    "symbol": "2330",
                },
            }
        )
        self.client.message(
            {
                "event": "subscribed",
                "data": {
                    "id": "aggregate-2317",
                    "channel": "aggregates",
                    "symbol": "2317",
                },
            }
        )

        self.feed.unsubscribe(stock_symbols=["2330", "9999"])
        self.feed.unsubscribe(stock_symbols=["2330"])

        self.assertEqual(
            [{"ids": ["aggregate-2330"]}],
            self.client.unsubscribe_calls,
        )
        self.assertEqual(1, self.feed.health()["desired_stock_count"])

    def test_oversized_subscription_id_is_rejected_and_never_retained(self) -> None:
        self.feed.connect()
        self.feed.subscribe(stock_symbols=["2330"])
        self.client.message(
            {
                "event": "subscribed",
                "data": {
                    "id": "x" * 129,
                    "channel": "aggregates",
                    "symbol": "2330",
                },
            }
        )

        self.feed.unsubscribe(stock_symbols=["2330"])

        self.assertEqual([], self.client.unsubscribe_calls)
        self.assertEqual(1, self.feed.health()["rejected_messages"])

    def test_close_is_idempotent_and_clears_subscriptions_and_overlay(self) -> None:
        self.feed.subscribe(
            stock_symbols=["2330"],
            index_symbols=["IR0001"],
        )
        self.feed.connect()
        self.client.message(
            {
                "event": "data",
                "channel": "indices",
                "data": {
                    "symbol": "IR0001",
                    "type": "INDEX",
                    "exchange": "TWSE",
                    "index": 24980.25,
                    "time": epoch_microseconds(self.clock()),
                },
            }
        )

        self.feed.close()
        self.feed.close()

        snapshot = self.feed.overlay_snapshot()
        health = self.feed.health()
        self.assertEqual(1, self.client.disconnect_calls)
        self.assertEqual("CLOSED", snapshot["transport_status"])
        self.assertEqual("UNAVAILABLE", snapshot["status"])
        self.assertEqual({}, snapshot["aggregates"])
        self.assertEqual({}, snapshot["indices"])
        self.assertEqual(0, health["desired_stock_count"])
        self.assertEqual(0, health["desired_index_count"])

    def test_malformed_raw_json_is_counted_and_never_enters_overlay(self) -> None:
        self.feed.connect()
        self.client.emit("message", "{not-json")

        snapshot = self.feed.overlay_snapshot()
        health = self.feed.health()
        self.assertEqual("UNAVAILABLE", snapshot["status"])
        self.assertEqual({}, snapshot["aggregates"])
        self.assertEqual({}, snapshot["indices"])
        self.assertEqual(1, health["rejected_messages"])

    def test_parser_recursion_payload_is_rejected_without_escaping_callback(self) -> None:
        self.feed.connect()
        deeply_nested = (
            '{"event":"heartbeat","payload":'
            + "[" * 1_100
            + "0"
            + "]" * 1_100
            + "}"
        )

        self.client.emit("message", deeply_nested)

        snapshot = self.feed.overlay_snapshot()
        self.assertEqual("UNAVAILABLE", snapshot["status"])
        self.assertEqual(1, self.feed.health()["rejected_messages"])

    def test_first_malformed_data_for_desired_symbol_reports_stale(self) -> None:
        self.feed.subscribe(stock_symbols=["2330"])
        self.feed.connect()

        self.client.message(
            {
                "event": "data",
                "channel": "aggregates",
                "data": ["malformed"],
            }
        )

        snapshot = self.feed.overlay_snapshot()
        self.assertEqual("STALE", snapshot["status"])
        self.assertEqual(["2330"], snapshot["coverage"]["missing_aggregates"])

    def test_malformed_event_name_is_rejected_instead_of_ignored(self) -> None:
        self.feed.connect()

        self.client.message({"event": [], "data": {}})

        self.assertEqual(1, self.feed.health()["rejected_messages"])

    def test_oversized_raw_message_is_rejected_and_taints_existing_overlay(self) -> None:
        self.feed.subscribe(index_symbols=["IR0001"])
        self.feed.connect()
        self.client.message(
            {
                "event": "data",
                "channel": "indices",
                "data": {
                    "symbol": "IR0001",
                    "type": "INDEX",
                    "exchange": "TWSE",
                    "index": 24980.25,
                    "time": epoch_microseconds(self.clock()),
                },
            }
        )

        oversized = json.dumps(
            {"event": "heartbeat", "padding": "x" * 300_000}
        )
        self.client.emit("message", oversized)

        snapshot = self.feed.overlay_snapshot()
        self.assertEqual("STALE", snapshot["status"])
        self.assertEqual("STALE", snapshot["indices"]["IR0001"]["status"])
        self.assertEqual(1, self.feed.health()["rejected_messages"])

    def test_deep_or_wide_payload_is_rejected_without_replacing_quote(self) -> None:
        deep: dict = {}
        for _ in range(9):
            deep = {"child": deep}
        for extra in (
            {"nested": deep},
            {"items": list(range(300))},
        ):
            with self.subTest(shape=next(iter(extra))):
                client = FakeWebSocketClient()
                feed = FubonWebSocketFeed(client, clock=self.clock)
                feed.subscribe(stock_symbols=["2330"])
                feed.connect()
                client.message(
                    {
                        "event": "data",
                        "channel": "aggregates",
                        "data": {
                            "symbol": "2330",
                            "type": "EQUITY",
                            "exchange": "TWSE",
                            "lastPrice": 1180.0,
                            "lastUpdated": epoch_microseconds(self.clock()),
                            "serial": 101,
                        },
                    }
                )
                client.message(
                    {
                        "event": "data",
                        "channel": "aggregates",
                        "data": {
                            "symbol": "2330",
                            "type": "EQUITY",
                            "exchange": "TWSE",
                            "lastPrice": 9999.0,
                            "lastUpdated": epoch_microseconds(self.clock()),
                            "serial": 102,
                            **extra,
                        },
                    }
                )

                snapshot = feed.overlay_snapshot()
                self.assertEqual("STALE", snapshot["status"])
                self.assertEqual(1180.0, snapshot["aggregates"]["2330"]["lastPrice"])
                self.assertEqual(1, feed.health()["rejected_messages"])

    def test_retained_aggregate_contains_only_bounded_quote_fields(self) -> None:
        self.feed.subscribe(stock_symbols=["2330"])
        self.feed.connect()
        self.client.message(
            {
                "event": "data",
                "channel": "aggregates",
                "data": {
                    "symbol": "2330",
                    "type": "EQUITY",
                    "exchange": "TWSE",
                    "name": "台積電",
                    "lastPrice": 1180.0,
                    "lastUpdated": epoch_microseconds(self.clock()),
                    "serial": 101,
                    "total": {
                        "tradeVolume": 12345,
                        "tradeValue": 14_566_410_000,
                        "secret": "drop-me",
                    },
                    "lastTrade": {"price": 1180.0, "secret": "drop-me"},
                    "bids": [
                        {"price": 1179.0, "secret": "drop-me"},
                        {"price": 1178.0},
                    ],
                    "asks": [{"price": 1181.0, "secret": "drop-me"}],
                    "credential": "drop-me",
                    "unexpected": {"nested": "drop-me"},
                },
            }
        )

        row = self.feed.overlay_snapshot()["aggregates"]["2330"]
        self.assertNotIn("credential", row)
        self.assertNotIn("unexpected", row)
        self.assertEqual(
            {"tradeVolume": 12345, "tradeValue": 14_566_410_000},
            row["total"],
        )
        self.assertEqual({"price": 1180.0}, row["lastTrade"])
        self.assertEqual([{"price": 1179.0}], row["bids"])
        self.assertEqual([{"price": 1181.0}], row["asks"])
        self.assertLess(len(json.dumps(row, ensure_ascii=False)), 4096)

    def test_fresh_weekend_event_is_not_live(self) -> None:
        self.clock.value = datetime(2026, 8, 29, 10, 0, tzinfo=TAIPEI)
        self.feed.subscribe(index_symbols=["IR0001"])
        self.feed.connect()
        self.client.message(
            {
                "event": "data",
                "channel": "indices",
                "data": {
                    "symbol": "IR0001",
                    "type": "INDEX",
                    "exchange": "TWSE",
                    "index": 24980.25,
                    "time": epoch_microseconds(self.clock()),
                },
            }
        )

        snapshot = self.feed.overlay_snapshot()
        self.assertEqual("STALE", snapshot["status"])
        self.assertEqual("STALE", snapshot["indices"]["IR0001"]["status"])

    def test_delayed_open_and_close_flags_never_mean_delayed_feed(self) -> None:
        self.feed.subscribe(stock_symbols=["2330"])
        self.feed.connect()
        self.client.message(
            {
                "event": "data",
                "channel": "aggregates",
                "data": {
                    "symbol": "2330",
                    "type": "EQUITY",
                    "exchange": "TWSE",
                    "lastPrice": 1180.0,
                    "lastUpdated": epoch_microseconds(self.clock()),
                    "serial": 101,
                    "isDelayedOpen": True,
                    "isDelayedClose": True,
                },
            }
        )

        row = self.feed.overlay_snapshot()["aggregates"]["2330"]
        self.assertEqual("LIVE", row["status"])

    def test_channel_type_mismatch_is_rejected(self) -> None:
        for channel, symbol, wrong_type, value_fields, target in (
            (
                "aggregates",
                "2330",
                "INDEX",
                {
                    "lastPrice": 1180.0,
                    "lastUpdated": epoch_microseconds(self.clock()),
                    "serial": 101,
                },
                "aggregates",
            ),
            (
                "indices",
                "IR0001",
                "EQUITY",
                {
                    "index": 24980.25,
                    "time": epoch_microseconds(self.clock()),
                },
                "indices",
            ),
        ):
            with self.subTest(channel=channel):
                client = FakeWebSocketClient()
                feed = FubonWebSocketFeed(client, clock=self.clock)
                feed.connect()
                client.message(
                    {
                        "event": "data",
                        "channel": channel,
                        "data": {
                            "symbol": symbol,
                            "type": wrong_type,
                            "exchange": "TWSE",
                            **value_fields,
                        },
                    }
                )

                self.assertEqual({}, feed.overlay_snapshot()[target])
                self.assertEqual(1, feed.health()["rejected_messages"])

    def test_same_day_eod_survives_websocket_silence(self) -> None:
        self.clock.value = datetime(2026, 8, 28, 14, 10, tzinfo=TAIPEI)
        self.feed.subscribe(stock_symbols=["2330"])
        self.feed.connect()
        self.client.message(
            {
                "event": "data",
                "channel": "aggregates",
                "data": {
                    "symbol": "2330",
                    "type": "EQUITY",
                    "exchange": "TWSE",
                    "lastPrice": 1190.0,
                    "lastUpdated": epoch_microseconds(
                        datetime(2026, 8, 28, 13, 31, tzinfo=TAIPEI)
                    ),
                    "serial": 999,
                    "isClose": True,
                },
            }
        )
        self.clock.advance(seconds=60)

        snapshot = self.feed.overlay_snapshot()
        self.assertGreater(snapshot["quiet_seconds"], 45)
        self.assertEqual("EOD", snapshot["status"])
        self.assertEqual("EOD", snapshot["aggregates"]["2330"]["status"])

    def test_multi_symbol_subscription_acknowledgement_preserves_all_ids(self) -> None:
        self.feed.connect()
        self.feed.subscribe(stock_symbols=["2330", "2317"])
        self.client.message(
            {
                "event": "subscribed",
                "data": [
                    {
                        "id": "aggregate-2330",
                        "channel": "aggregates",
                        "symbol": "2330",
                    },
                    {
                        "id": "aggregate-2317",
                        "channel": "aggregates",
                        "symbol": "2317",
                    },
                ],
            }
        )

        self.feed.unsubscribe(stock_symbols=["2330", "2317"])

        self.assertEqual(
            [{"ids": ["aggregate-2317", "aggregate-2330"]}],
            self.client.unsubscribe_calls,
        )

    def test_close_only_aggregate_is_valid_eod_quote(self) -> None:
        self.clock.value = datetime(2026, 8, 28, 14, 10, tzinfo=TAIPEI)
        self.feed.subscribe(stock_symbols=["2330"])
        self.feed.connect()
        self.client.message(
            {
                "event": "data",
                "channel": "aggregates",
                "data": {
                    "symbol": "2330",
                    "type": "EQUITY",
                    "exchange": "TWSE",
                    "close": 1190.0,
                    "lastUpdated": epoch_microseconds(
                        datetime(2026, 8, 28, 13, 31, tzinfo=TAIPEI)
                    ),
                    "serial": 999,
                    "isClose": True,
                },
            }
        )

        row = self.feed.overlay_snapshot()["aggregates"]["2330"]
        self.assertEqual("EOD", row["status"])
        self.assertEqual(1190.0, row["close"])

    def test_close_price_only_aggregate_is_valid_eod_quote(self) -> None:
        self.clock.value = datetime(2026, 8, 28, 14, 10, tzinfo=TAIPEI)
        self.feed.subscribe(stock_symbols=["2330"])
        self.feed.connect()
        self.client.message(
            {
                "event": "data",
                "channel": "aggregates",
                "data": {
                    "symbol": "2330",
                    "type": "EQUITY",
                    "exchange": "TWSE",
                    "closePrice": 1190.0,
                    "lastUpdated": epoch_microseconds(
                        datetime(2026, 8, 28, 13, 31, tzinfo=TAIPEI)
                    ),
                    "serial": 999,
                    "isClose": True,
                },
            }
        )

        row = self.feed.overlay_snapshot()["aggregates"]["2330"]
        self.assertEqual("EOD", row["status"])
        self.assertEqual(1190.0, row["closePrice"])

    def test_zero_last_price_does_not_mask_valid_close_price(self) -> None:
        self.clock.value = datetime(2026, 8, 28, 14, 10, tzinfo=TAIPEI)
        self.feed.subscribe(stock_symbols=["2330"])
        self.feed.connect()
        self.client.message(
            {
                "event": "data",
                "channel": "aggregates",
                "data": {
                    "symbol": "2330",
                    "type": "EQUITY",
                    "exchange": "TWSE",
                    "lastPrice": 0,
                    "closePrice": 1190.0,
                    "lastUpdated": epoch_microseconds(
                        datetime(2026, 8, 28, 13, 31, tzinfo=TAIPEI)
                    ),
                    "serial": 999,
                    "isClose": True,
                },
            }
        )

        row = self.feed.overlay_snapshot()["aggregates"]["2330"]
        self.assertEqual("EOD", row["status"])
        self.assertEqual(1190.0, row["closePrice"])

    def test_mixed_live_and_eod_collection_fails_closed_as_stale(self) -> None:
        self.feed.subscribe(
            stock_symbols=["2330"],
            index_symbols=["IR0001"],
        )
        self.feed.connect()
        for channel, data in (
            (
                "aggregates",
                {
                    "symbol": "2330",
                    "type": "EQUITY",
                    "exchange": "TWSE",
                    "lastPrice": 1180.0,
                    "lastUpdated": epoch_microseconds(self.clock()),
                    "serial": 101,
                    "isClose": True,
                },
            ),
            (
                "indices",
                {
                    "symbol": "IR0001",
                    "type": "INDEX",
                    "exchange": "TWSE",
                    "index": 24980.25,
                    "time": epoch_microseconds(self.clock()),
                },
            ),
        ):
            self.client.message(
                {"event": "data", "channel": channel, "data": data}
            )

        snapshot = self.feed.overlay_snapshot()
        self.assertEqual("STALE", snapshot["status"])
        self.assertEqual("EOD", snapshot["aggregates"]["2330"]["status"])
        self.assertEqual("LIVE", snapshot["indices"]["IR0001"]["status"])

    def test_late_callbacks_after_close_cannot_reopen_feed(self) -> None:
        self.feed.connect()
        self.feed.close()

        self.client.emit("authenticated")
        self.client.emit("error", RuntimeError("late"))
        self.client.message(
            {
                "event": "data",
                "channel": "indices",
                "data": {
                    "symbol": "IR0001",
                    "type": "INDEX",
                    "exchange": "TWSE",
                    "index": 24980.25,
                    "time": epoch_microseconds(self.clock()),
                },
            }
        )

        snapshot = self.feed.overlay_snapshot()
        self.assertEqual("CLOSED", snapshot["transport_status"])
        self.assertEqual("UNAVAILABLE", snapshot["status"])
        self.assertEqual({}, snapshot["indices"])

    def test_recent_event_after_live_session_is_stale(self) -> None:
        self.clock.value = datetime(2026, 8, 28, 13, 41, tzinfo=TAIPEI)
        self.feed.subscribe(index_symbols=["IR0001"])
        self.feed.connect()
        self.client.message(
            {
                "event": "data",
                "channel": "indices",
                "data": {
                    "symbol": "IR0001",
                    "type": "INDEX",
                    "exchange": "TWSE",
                    "index": 24980.25,
                    "time": epoch_microseconds(
                        datetime(2026, 8, 28, 13, 39, 30, tzinfo=TAIPEI)
                    ),
                },
            }
        )

        snapshot = self.feed.overlay_snapshot()
        self.assertEqual("STALE", snapshot["status"])
        self.assertEqual("STALE", snapshot["indices"]["IR0001"]["status"])

    def test_late_data_after_unsubscribe_does_not_recreate_overlay(self) -> None:
        self.feed.connect()
        self.feed.subscribe(stock_symbols=["2330"])
        self.feed.unsubscribe(stock_symbols=["2330"])

        self.client.message(
            {
                "event": "data",
                "channel": "aggregates",
                "data": {
                    "symbol": "2330",
                    "type": "EQUITY",
                    "exchange": "TWSE",
                    "lastPrice": 1180.0,
                    "lastUpdated": epoch_microseconds(self.clock()),
                    "serial": 101,
                },
            }
        )

        self.assertEqual({}, self.feed.overlay_snapshot()["aggregates"])

    def test_explicit_payload_delay_window_keeps_delayed_status(self) -> None:
        self.clock.value = datetime(2026, 8, 28, 10, 15, tzinfo=TAIPEI)
        self.feed.subscribe(index_symbols=["IR0001"])
        self.feed.connect()
        self.client.message(
            {
                "event": "data",
                "channel": "indices",
                "data": {
                    "symbol": "IR0001",
                    "type": "INDEX",
                    "exchange": "TWSE",
                    "index": 24980.25,
                    "time": epoch_microseconds(
                        datetime(2026, 8, 28, 10, 0, tzinfo=TAIPEI)
                    ),
                    "isDelayed": True,
                    "delaySeconds": 900,
                },
            }
        )

        row = self.feed.overlay_snapshot()["indices"]["IR0001"]
        self.assertEqual("DELAYED", row["status"])
        self.assertEqual(900.0, row["delay_seconds"])

    def test_invalid_symbol_or_exchange_cannot_enter_overlay(self) -> None:
        self.feed.connect()
        for symbol, exchange in (("../2330", "TWSE"), ("2330", "UNKNOWN")):
            self.client.message(
                {
                    "event": "data",
                    "channel": "aggregates",
                    "data": {
                        "symbol": symbol,
                        "type": "EQUITY",
                        "exchange": exchange,
                        "lastPrice": 1180.0,
                        "lastUpdated": epoch_microseconds(self.clock()),
                        "serial": 101,
                    },
                }
            )

        self.assertEqual({}, self.feed.overlay_snapshot()["aggregates"])
        self.assertEqual(2, self.feed.health()["rejected_messages"])

    def test_connect_failures_use_bounded_exponential_backoff(self) -> None:
        self.client.connect_error = RuntimeError("offline")

        for attempt, expected_delay in enumerate((5, 10, 20, 40, 60, 60), 1):
            with self.subTest(attempt=attempt):
                self.feed.connect()

                health = self.feed.health()
                self.assertEqual("ERROR", health["transport_status"])
                self.assertEqual(expected_delay, health["retry_after_seconds"])
                self.assertEqual(attempt, health["reconnect_failures"])
                self.assertEqual(attempt, self.client.connect_calls)

                self.feed.connect()
                self.assertEqual(attempt, self.client.connect_calls)
                self.clock.advance(seconds=expected_delay)

    def test_authenticated_event_resets_reconnect_backoff(self) -> None:
        self.client.connect_error = RuntimeError("offline")
        self.feed.connect()
        self.clock.advance(seconds=5)
        self.client.connect_error = None
        self.feed.connect()

        health = self.feed.health()
        self.assertEqual("AUTHENTICATED", self.feed.health()["transport_status"])
        self.assertEqual(0.0, health["retry_after_seconds"])
        self.assertEqual(0, health["reconnect_failures"])
        self.assertEqual(2, self.client.connect_calls)

        self.client.emit("error", RuntimeError("credential-shaped detail"))
        health = self.feed.health()
        self.assertEqual(5.0, health["retry_after_seconds"])
        self.assertEqual(1, health["reconnect_failures"])
        self.assertNotIn("credential-shaped detail", json.dumps(health))

    def test_error_and_disconnect_callbacks_count_as_one_failure_incident(self) -> None:
        self.feed.connect()

        self.client.emit("error", RuntimeError("first callback"))
        self.client.emit("disconnect", 1006, "second callback")

        health = self.feed.health()
        self.assertEqual("DISCONNECTED", health["transport_status"])
        self.assertEqual(5.0, health["retry_after_seconds"])
        self.assertEqual(1, health["reconnect_failures"])
        self.assertNotIn("first callback", json.dumps(health))
        self.assertNotIn("second callback", json.dumps(health))

    def test_intentional_disconnect_and_close_do_not_add_backoff(self) -> None:
        self.feed.connect()

        self.feed.disconnect()
        health = self.feed.health()
        self.assertEqual(0.0, health["retry_after_seconds"])
        self.assertEqual(0, health["reconnect_failures"])

    def test_noisy_callbacks_during_intentional_disconnect_do_not_add_backoff(
        self,
    ) -> None:
        self.feed.connect()

        def noisy_disconnect() -> None:
            self.client.disconnect_calls += 1
            self.client.emit("error", RuntimeError("shutdown noise"))
            self.client.emit("unauthenticated")
            self.client.emit("disconnect", 1000, "normal")

        self.client.disconnect = noisy_disconnect
        self.feed.disconnect()

        health = self.feed.health()
        self.assertEqual("DISCONNECTED", health["transport_status"])
        self.assertEqual(0.0, health["retry_after_seconds"])
        self.assertEqual(0, health["reconnect_failures"])
        self.assertNotIn("shutdown noise", json.dumps(health))

        self.feed.connect()
        self.feed.close()
        health = self.feed.health()
        self.assertEqual(0.0, health["retry_after_seconds"])
        self.assertEqual(0, health["reconnect_failures"])

    def test_explicit_disconnect_demotes_eod_even_when_same_day(self) -> None:
        self.clock.value = datetime(2026, 8, 28, 14, 10, tzinfo=TAIPEI)
        self.feed.subscribe(stock_symbols=["2330"])
        self.feed.connect()
        self.client.message(
            {
                "event": "data",
                "channel": "aggregates",
                "data": {
                    "symbol": "2330",
                    "type": "EQUITY",
                    "exchange": "TWSE",
                    "close": 1190.0,
                    "lastUpdated": epoch_microseconds(
                        datetime(2026, 8, 28, 13, 31, tzinfo=TAIPEI)
                    ),
                    "serial": 999,
                    "isClose": True,
                },
            }
        )
        self.client.disconnect()

        snapshot = self.feed.overlay_snapshot()
        self.assertEqual("STALE", snapshot["status"])
        self.assertEqual("STALE", snapshot["aggregates"]["2330"]["status"])

    def test_partial_desired_coverage_is_stale_and_not_ready(self) -> None:
        self.feed.connect()
        self.feed.subscribe(stock_symbols=["2330", "2317"])
        self.client.message(
            {
                "event": "data",
                "channel": "aggregates",
                "data": {
                    "symbol": "2330",
                    "type": "EQUITY",
                    "exchange": "TWSE",
                    "lastPrice": 1180.0,
                    "lastUpdated": epoch_microseconds(self.clock()),
                    "serial": 101,
                },
            }
        )

        snapshot = self.feed.overlay_snapshot()
        health = self.feed.health()
        self.assertEqual("STALE", snapshot["status"])
        self.assertFalse(snapshot["coverage"]["complete"])
        self.assertEqual(["2317"], snapshot["coverage"]["missing_aggregates"])
        self.assertFalse(health["ready"])

    def test_unrequested_symbol_is_rejected_when_feed_owns_subscriptions(self) -> None:
        self.feed.connect()
        self.feed.subscribe(stock_symbols=["2330"])
        self.client.message(
            {
                "event": "data",
                "channel": "aggregates",
                "data": {
                    "symbol": "9999",
                    "type": "EQUITY",
                    "exchange": "TWSE",
                    "lastPrice": 50.0,
                    "lastUpdated": epoch_microseconds(self.clock()),
                    "serial": 101,
                },
            }
        )

        snapshot = self.feed.overlay_snapshot()
        self.assertEqual({}, snapshot["aggregates"])
        self.assertEqual(["2330"], snapshot["coverage"]["missing_aggregates"])
        self.assertEqual(1, self.feed.health()["rejected_messages"])

    def test_data_without_any_desired_subscription_is_rejected(self) -> None:
        self.feed.connect()
        self.client.message(
            {
                "event": "data",
                "channel": "indices",
                "data": {
                    "symbol": "IR0001",
                    "type": "INDEX",
                    "exchange": "TWSE",
                    "index": 24980.25,
                    "time": epoch_microseconds(self.clock()),
                },
            }
        )

        snapshot = self.feed.overlay_snapshot()
        self.assertEqual("UNAVAILABLE", snapshot["status"])
        self.assertEqual({}, snapshot["indices"])
        self.assertEqual(1, self.feed.health()["rejected_messages"])

    def test_malformed_subscription_ack_cannot_refresh_transport_silence(self) -> None:
        self.feed.subscribe(index_symbols=["IR0001"])
        self.feed.connect()
        self.client.message(
            {
                "event": "data",
                "channel": "indices",
                "data": {
                    "symbol": "IR0001",
                    "type": "INDEX",
                    "exchange": "TWSE",
                    "index": 24980.25,
                    "time": epoch_microseconds(self.clock()),
                },
            }
        )
        self.clock.advance(seconds=25)
        self.client.message({"event": "subscribed", "data": {}})
        self.clock.advance(seconds=21)

        snapshot = self.feed.overlay_snapshot()
        self.assertEqual("STALE", snapshot["status"])
        self.assertEqual(46.0, snapshot["quiet_seconds"])
        self.assertEqual(1, self.feed.health()["rejected_messages"])

    def test_malformed_unsubscribe_ack_taints_without_refreshing_silence(self) -> None:
        self.feed.subscribe(index_symbols=["IR0001"])
        self.feed.connect()
        self.client.message(
            {
                "event": "data",
                "channel": "indices",
                "data": {
                    "symbol": "IR0001",
                    "type": "INDEX",
                    "exchange": "TWSE",
                    "index": 24980.25,
                    "time": epoch_microseconds(self.clock()),
                },
            }
        )
        self.clock.advance(seconds=10)

        self.client.message({"event": "unsubscribed", "data": {}})

        snapshot = self.feed.overlay_snapshot()
        self.assertEqual("STALE", snapshot["status"])
        self.assertEqual(10.0, snapshot["quiet_seconds"])
        self.assertEqual(1, self.feed.health()["rejected_messages"])

    def test_malformed_control_or_data_taints_until_next_valid_data_event(self) -> None:
        self.feed.subscribe(index_symbols=["IR0001"])
        self.feed.connect()
        self.client.message(
            {
                "event": "data",
                "channel": "indices",
                "data": {
                    "symbol": "IR0001",
                    "type": "INDEX",
                    "exchange": "TWSE",
                    "index": 24980.25,
                    "time": epoch_microseconds(self.clock()),
                },
            }
        )

        self.client.message({"event": "subscribed", "data": {}})
        self.assertEqual("STALE", self.feed.overlay_snapshot()["status"])

        self.client.message({"event": "heartbeat"})
        self.assertEqual("STALE", self.feed.overlay_snapshot()["status"])

        self.client.message(
            {
                "event": "data",
                "channel": "indices",
                "data": ["malformed"],
            }
        )
        self.assertEqual("STALE", self.feed.overlay_snapshot()["status"])

        self.clock.advance(seconds=1)
        self.client.message(
            {
                "event": "data",
                "channel": "indices",
                "data": {
                    "symbol": "IR0001",
                    "type": "INDEX",
                    "exchange": "TWSE",
                    "index": 24981.0,
                    "time": epoch_microseconds(self.clock()),
                },
            }
        )
        recovered = self.feed.overlay_snapshot()
        self.assertEqual("LIVE", recovered["status"])
        self.assertEqual(24981.0, recovered["indices"]["IR0001"]["index"])

    def test_malformed_authenticated_message_does_not_unlock_subscriptions(self) -> None:
        client = FakeWebSocketClient()
        feed = FubonWebSocketFeed(client, clock=self.clock)
        feed.subscribe(stock_symbols=["2330"])
        client.emit("connect")

        client.message({"event": "authenticated", "data": "unexpected"})

        self.assertEqual([], client.subscribe_calls)
        self.assertEqual(1, feed.health()["rejected_messages"])

    def test_raw_provider_error_fails_closed_without_exposing_message(self) -> None:
        self.feed.subscribe(index_symbols=["IR0001"])
        self.feed.connect()
        self.client.message(
            {
                "event": "data",
                "channel": "indices",
                "data": {
                    "symbol": "IR0001",
                    "type": "INDEX",
                    "exchange": "TWSE",
                    "index": 24980.25,
                    "time": epoch_microseconds(self.clock()),
                },
            }
        )
        self.client.message(
            {
                "event": "error",
                "data": {"message": "credential-shaped provider detail"},
            }
        )

        health = self.feed.health()
        self.assertEqual("STALE", health["status"])
        self.assertEqual("ERROR", health["transport_status"])
        self.assertNotIn("credential-shaped provider detail", json.dumps(health))

    def test_invalid_subscription_symbol_fails_closed_for_whole_batch(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid stock symbol"):
            self.feed.subscribe(stock_symbols=["2330", "../9999"])

        health = self.feed.health()
        self.assertEqual(0, health["desired_stock_count"])
        self.assertEqual([], self.client.subscribe_calls)


if __name__ == "__main__":
    unittest.main()
