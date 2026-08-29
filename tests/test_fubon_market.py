import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from taiwan_stock_analysis.fubon_market import (
    FUBON_STOCK_BASE_URL,
    FubonAuthenticationError,
    FubonAuthenticationCooldownError,
    FubonConfigurationError,
    FubonSDKUnavailableError,
    FubonSessionError,
    FubonSessionManager,
    FubonSessionTimeoutError,
)


PERSONAL_ID = "PERS-ID-7f1cdb"
API_KEY = "api-key-5394d2"
CERT_PASSWORD = "cert-password-8bc390"
SDK_TOKEN = "sdk-token-3e98c1"
ACCOUNT_NUMBER = "account-284391"
ACCOUNT_NAME = "customer-name-b6a512"


class _FakeSDK:
    def __init__(
        self,
        *,
        sdk_token=SDK_TOKEN,
        base_url=FUBON_STOCK_BASE_URL,
        login_result=None,
        login_error=None,
        init_error=None,
    ):
        self.sdk_token = sdk_token
        self.base_url = base_url
        self.login_result = login_result or SimpleNamespace(is_success=True)
        self.login_error = login_error
        self.init_error = init_error
        self.login_calls = 0
        self.init_calls = 0
        self.init_modes = []
        self.logout_calls = 0
        self.login_arguments = []
        self._lock = threading.Lock()

    def apikey_login(
        self,
        personal_id,
        api_key,
        cert_path,
        cert_password,
    ):
        with self._lock:
            self.login_calls += 1
            self.login_arguments.append(
                (personal_id, api_key, cert_path, cert_password)
            )
        time.sleep(0.01)
        if self.login_error is not None:
            raise self.login_error
        return self.login_result

    def init_realtime(self, mode=None):
        self.init_calls += 1
        self.init_modes.append(mode)
        if self.init_error is not None:
            raise self.init_error
        self.stock_websocket = SimpleNamespace(name="normal-stock-websocket")
        self.marketdata = SimpleNamespace(
            rest_client=SimpleNamespace(
                stock=SimpleNamespace(
                    config={
                        "base_url": self.base_url,
                        "sdk_token": self.sdk_token,
                    }
                )
            ),
            websocket_client=SimpleNamespace(stock=self.stock_websocket),
        )

    def logout(self):
        self.logout_calls += 1


class _BlockingSDK(_FakeSDK):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.login_started = threading.Event()
        self.login_release = threading.Event()
        self.logout_finished = threading.Event()

    def apikey_login(
        self,
        personal_id,
        api_key,
        cert_path,
        cert_password,
    ):
        with self._lock:
            self.login_calls += 1
            self.login_arguments.append(
                (personal_id, api_key, cert_path, cert_password)
            )
        self.login_started.set()
        self.login_release.wait()
        if self.login_error is not None:
            raise self.login_error
        return self.login_result

    def logout(self):
        super().logout()
        self.logout_finished.set()


class _HungLogoutSDK(_FakeSDK):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.logout_started = threading.Event()
        self.logout_release = threading.Event()
        self.logout_finished = threading.Event()

    def logout(self):
        self.logout_calls += 1
        self.logout_started.set()
        self.logout_release.wait()
        self.logout_finished.set()


class _CollectingFactory:
    def __init__(self):
        self.instances = []
        self._lock = threading.Lock()

    def __call__(self):
        with self._lock:
            ordinal = len(self.instances) + 1
            sdk = _FakeSDK(sdk_token=f"{SDK_TOKEN}-{ordinal}")
            self.instances.append(sdk)
            return sdk


class _SequenceFactory:
    def __init__(self, instances):
        self.instances = list(instances)
        self.calls = 0
        self._lock = threading.Lock()

    def __call__(self):
        with self._lock:
            instance = self.instances[self.calls]
            self.calls += 1
            return instance


class _FakeMonotonic:
    def __init__(self):
        self.value = 0.0
        self._lock = threading.Lock()

    def __call__(self):
        with self._lock:
            return self.value

    def advance(self, seconds):
        with self._lock:
            self.value += seconds


class FubonSessionManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.certificate_path = Path(self.temp_directory.name) / "client.pfx"
        self.certificate_path.write_bytes(b"fixture certificate")

    def manager(self, *, sdk_factory=None, **overrides):
        configuration = {
            "personal_id": PERSONAL_ID,
            "api_key": API_KEY,
            "cert_path": self.certificate_path,
            "cert_password": CERT_PASSWORD,
        }
        configuration.update(overrides)
        return FubonSessionManager(
            **configuration,
            sdk_factory=sdk_factory,
        )

    def assert_no_sensitive_values(self, message):
        for sensitive_value in (
            PERSONAL_ID,
            API_KEY,
            str(self.certificate_path),
            CERT_PASSWORD,
            SDK_TOKEN,
            ACCOUNT_NUMBER,
            ACCOUNT_NAME,
        ):
            self.assertNotIn(sensitive_value, message)

    def test_authenticated_session_initializes_normal_mode_and_exposes_stock_websocket(self):
        sdk = _FakeSDK()
        manager = self.manager(sdk_factory=lambda: sdk)

        websocket = manager.stock_websocket_client(timeout_seconds=1)

        self.assertIs(sdk.stock_websocket, websocket)
        self.assertEqual(1, sdk.init_calls)
        self.assertEqual("normal", sdk.init_modes[0].value)

    def test_missing_configuration_is_reported_and_rejected(self):
        cases = (
            ("personal_id", None),
            ("api_key", ""),
            ("cert_path", None),
            ("cert_password", ""),
        )

        for field_name, missing_value in cases:
            with self.subTest(field_name=field_name):
                manager = self.manager(
                    sdk_factory=_FakeSDK,
                    **{field_name: missing_value},
                )

                self.assertIn(field_name, manager.configuration_error())
                with self.assertRaises(FubonConfigurationError) as raised:
                    manager.session()
                self.assert_no_sensitive_values(str(raised.exception))

    def test_sdk_unavailable_is_lazy_and_sanitized(self):
        manager = self.manager()
        imported = []

        def missing_sdk(module_name):
            imported.append(module_name)
            raise ModuleNotFoundError(
                f"{PERSONAL_ID} {API_KEY} {CERT_PASSWORD}"
            )

        self.assertEqual([], imported)
        with (
            patch(
                "taiwan_stock_analysis.fubon_market.importlib.metadata.version",
                return_value="2.2.8",
            ),
            patch(
                "taiwan_stock_analysis.fubon_market.importlib.import_module",
                side_effect=missing_sdk,
            ),
        ):
            self.assertFalse(manager.sdk_available())
            with self.assertRaises(FubonSDKUnavailableError) as raised:
                manager.session()

        self.assertEqual(
            ["fubon_neo.sdk", "fubon_neo.sdk"],
            imported,
        )
        self.assert_no_sensitive_values(str(raised.exception))

    def test_supported_sdk_version_is_available(self):
        manager = self.manager()
        sdk_module = SimpleNamespace(
            FubonSDK=_FakeSDK,
            Mode=SimpleNamespace(
                Normal=SimpleNamespace(value="normal")
            ),
        )

        with (
            patch(
                "taiwan_stock_analysis.fubon_market.importlib.metadata.version",
                return_value="2.2.8",
            ),
            patch(
                "taiwan_stock_analysis.fubon_market.importlib.import_module",
                return_value=sdk_module,
            ),
        ):
            self.assertTrue(manager.sdk_available())
            session = manager.session()

        self.assertEqual(SDK_TOKEN, session.sdk_token)

    def test_wrong_sdk_version_is_unavailable(self):
        manager = self.manager()
        sdk_module = SimpleNamespace(FubonSDK=_FakeSDK)

        with (
            patch(
                "taiwan_stock_analysis.fubon_market.importlib.metadata.version",
                return_value="2.2.7",
            ),
            patch(
                "taiwan_stock_analysis.fubon_market.importlib.import_module",
                return_value=sdk_module,
            ),
        ):
            self.assertFalse(manager.sdk_available())
            with self.assertRaises(FubonSDKUnavailableError) as raised:
                manager.session()

        self.assert_no_sensitive_values(str(raised.exception))

    def test_nonexistent_certificate_is_rejected_before_sdk_creation(self):
        factory_calls = []
        missing_certificate = Path(self.temp_directory.name) / "missing.pfx"
        manager = self.manager(
            cert_path=missing_certificate,
            sdk_factory=lambda: factory_calls.append(True),
        )

        self.assertIn("regular file", manager.configuration_error())
        with self.assertRaises(FubonConfigurationError) as raised:
            manager.session()

        self.assertEqual([], factory_calls)
        self.assertNotIn(str(missing_certificate), str(raised.exception))

    def test_success_is_thread_safe_and_authenticates_only_once(self):
        sdk = _FakeSDK()
        manager = self.manager(sdk_factory=lambda: sdk)

        with ThreadPoolExecutor(max_workers=8) as executor:
            sessions = list(executor.map(lambda _: manager.session(), range(24)))

        self.assertTrue(all(session is sessions[0] for session in sessions))
        self.assertEqual(1, sdk.login_calls)
        self.assertEqual(1, sdk.init_calls)
        self.assertEqual(
            (
                PERSONAL_ID,
                API_KEY,
                str(self.certificate_path.resolve()),
                CERT_PASSWORD,
            ),
            sdk.login_arguments[0],
        )
        self.assertEqual(FUBON_STOCK_BASE_URL, sessions[0].base_url)
        self.assertEqual(SDK_TOKEN, sessions[0].sdk_token)
        self.assertNotIn(SDK_TOKEN, repr(sessions[0]))

    def test_relative_certificate_path_is_resolved_from_repository_root(self):
        with TemporaryDirectory() as repository:
            certificate = Path(repository) / "secrets" / "client.pfx"
            certificate.parent.mkdir()
            certificate.write_bytes(b"fixture certificate")
            sdk = _FakeSDK()
            manager = self.manager(
                cert_path=Path("secrets") / "client.pfx",
                sdk_factory=lambda: sdk,
            )

            with patch(
                "taiwan_stock_analysis.fubon_market._REPO_ROOT",
                Path(repository),
            ):
                manager.session()

        self.assertEqual(str(certificate.resolve()), sdk.login_arguments[0][2])

    def test_authentication_and_initialization_failures_do_not_leak(self):
        sensitive_message = " ".join(
            (
                PERSONAL_ID,
                API_KEY,
                str(self.certificate_path),
                CERT_PASSWORD,
                ACCOUNT_NUMBER,
                ACCOUNT_NAME,
            )
        )
        failed_result = SimpleNamespace(
            is_success=False,
            message=sensitive_message,
            data=[
                SimpleNamespace(
                    account=ACCOUNT_NUMBER,
                    name=ACCOUNT_NAME,
                )
            ],
        )
        scenarios = (
            (
                _FakeSDK(login_result=failed_result),
                FubonAuthenticationError,
            ),
            (
                _FakeSDK(login_error=RuntimeError(sensitive_message)),
                FubonAuthenticationError,
            ),
            (
                _FakeSDK(init_error=RuntimeError(sensitive_message)),
                FubonSessionError,
            ),
        )

        for scenario_index, (sdk, exception_type) in enumerate(scenarios):
            with self.subTest(exception_type=exception_type.__name__):
                manager = self.manager(
                    api_key=f"{API_KEY}-{scenario_index}",
                    sdk_factory=lambda sdk=sdk: sdk,
                )
                with self.assertRaises(exception_type) as raised:
                    manager.session()

                self.assert_no_sensitive_values(str(raised.exception))
                self.assertEqual(1, sdk.logout_calls)

    def test_malicious_rest_base_url_is_rejected_without_disclosure(self):
        malicious_url = (
            "https://api.fugle.tw.evil.example/"
            f"marketdata/v1.0/stock/{ACCOUNT_NUMBER}/{ACCOUNT_NAME}"
        )
        sdk = _FakeSDK(base_url=malicious_url)
        manager = self.manager(sdk_factory=lambda: sdk)

        with self.assertRaises(FubonSessionError) as raised:
            manager.session()

        self.assertIn("not trusted", str(raised.exception))
        self.assert_no_sensitive_values(str(raised.exception))
        self.assertNotIn(malicious_url, str(raised.exception))
        self.assertEqual(1, sdk.logout_calls)

    def test_invalid_sdk_token_is_rejected_without_disclosure(self):
        sdk = _FakeSDK(sdk_token=f"{SDK_TOKEN} invalid")
        manager = self.manager(sdk_factory=lambda: sdk)

        with self.assertRaises(FubonSessionError) as raised:
            manager.session()

        self.assertIn("token is unavailable", str(raised.exception))
        self.assert_no_sensitive_values(str(raised.exception))
        self.assertEqual(1, sdk.logout_calls)

    def test_trailing_slash_variant_is_rejected(self):
        sdk = _FakeSDK(base_url=f"{FUBON_STOCK_BASE_URL}/")
        manager = self.manager(
            sdk_factory=lambda: sdk
        )

        with self.assertRaisesRegex(FubonSessionError, "not trusted"):
            manager.session()
        self.assertEqual(1, sdk.logout_calls)

    def test_invalidate_logs_out_and_reauthenticates(self):
        factory = _CollectingFactory()
        manager = self.manager(sdk_factory=factory)

        first = manager.session()
        manager.invalidate()
        second = manager.session()

        self.assertNotEqual(first.sdk_token, second.sdk_token)
        self.assertEqual(2, len(factory.instances))
        self.assertEqual(1, factory.instances[0].login_calls)
        self.assertEqual(1, factory.instances[0].logout_calls)
        self.assertEqual(1, factory.instances[1].login_calls)
        self.assertEqual(0, factory.instances[1].logout_calls)

    def test_authentication_cooldown_is_shared_across_manager_instances(self):
        failed_sdks = [
            _FakeSDK(
                login_result=SimpleNamespace(is_success=False),
            )
            for _ in range(8)
        ]
        factory = _SequenceFactory(failed_sdks)
        clock = _FakeMonotonic()
        managers = [
            self.manager(
                sdk_factory=factory,
                monotonic_clock=clock,
            )
            for _ in range(8)
        ]

        def attempt(manager):
            try:
                manager.session()
            except FubonAuthenticationError as error:
                return error
            self.fail("authentication unexpectedly succeeded")

        with ThreadPoolExecutor(max_workers=8) as executor:
            errors = list(executor.map(attempt, managers))

        self.assertEqual(1, factory.calls)
        self.assertEqual(1, sum(sdk.login_calls for sdk in failed_sdks))
        self.assertEqual(
            7,
            sum(
                isinstance(error, FubonAuthenticationCooldownError)
                for error in errors
            ),
        )
        for error in errors:
            self.assert_no_sensitive_values(str(error))

    def test_backoff_doubles_and_success_resets_the_breaker(self):
        first_failure = _FakeSDK(
            login_result=SimpleNamespace(is_success=False),
        )
        second_failure = _FakeSDK(
            login_result=SimpleNamespace(is_success=False),
        )
        first_success = _FakeSDK(sdk_token=f"{SDK_TOKEN}-success-1")
        second_success = _FakeSDK(sdk_token=f"{SDK_TOKEN}-success-2")
        factory = _SequenceFactory(
            (
                first_failure,
                second_failure,
                first_success,
                second_success,
            )
        )
        clock = _FakeMonotonic()
        managers = [
            self.manager(
                sdk_factory=factory,
                monotonic_clock=clock,
            )
            for _ in range(4)
        ]

        with self.assertRaises(FubonAuthenticationError):
            managers[0].session()
        with self.assertRaises(
            FubonAuthenticationCooldownError
        ) as first_cooldown:
            managers[1].session()
        self.assertEqual(60.0, first_cooldown.exception.retry_after_seconds)
        self.assertEqual(1, factory.calls)

        clock.advance(60.0)
        with self.assertRaises(FubonAuthenticationError):
            managers[1].session()
        clock.advance(119.0)
        with self.assertRaises(
            FubonAuthenticationCooldownError
        ) as second_cooldown:
            managers[2].session()
        self.assertEqual(1.0, second_cooldown.exception.retry_after_seconds)
        self.assertEqual(2, factory.calls)

        clock.advance(1.0)
        self.assertEqual(
            f"{SDK_TOKEN}-success-1",
            managers[2].session().sdk_token,
        )

        managers[2].invalidate(authentication_failure=True)
        with self.assertRaises(
            FubonAuthenticationCooldownError
        ) as reset_cooldown:
            managers[3].session()
        self.assertEqual(60.0, reset_cooldown.exception.retry_after_seconds)
        self.assertEqual(3, factory.calls)

        clock.advance(60.0)
        self.assertEqual(
            f"{SDK_TOKEN}-success-2",
            managers[3].session().sdk_token,
        )
        self.assertEqual(4, factory.calls)

    def test_backoff_is_bounded_at_fifteen_minutes(self):
        failed_sdks = [
            _FakeSDK(
                login_result=SimpleNamespace(is_success=False),
            )
            for _ in range(6)
        ]
        factory = _SequenceFactory(failed_sdks)
        clock = _FakeMonotonic()
        expected_cooldowns = (60.0, 120.0, 240.0, 480.0, 900.0, 900.0)

        for attempt_index, expected_cooldown in enumerate(
            expected_cooldowns
        ):
            manager = self.manager(
                sdk_factory=factory,
                monotonic_clock=clock,
            )
            observer = self.manager(
                sdk_factory=factory,
                monotonic_clock=clock,
            )
            with self.assertRaises(FubonAuthenticationError):
                manager.session()
            with self.assertRaises(
                FubonAuthenticationCooldownError
            ) as cooldown:
                observer.session()

            self.assertEqual(
                expected_cooldown,
                cooldown.exception.retry_after_seconds,
                msg=f"attempt {attempt_index + 1}",
            )
            clock.advance(expected_cooldown)

        self.assertEqual(6, factory.calls)

    def test_invalid_market_session_opens_shared_cooldown(self):
        scenarios = (
            _FakeSDK(init_error=RuntimeError(API_KEY)),
            _FakeSDK(sdk_token=f"{SDK_TOKEN} invalid"),
        )

        for scenario_index, failed_sdk in enumerate(scenarios):
            with self.subTest(scenario_index=scenario_index):
                clock = _FakeMonotonic()
                unused_sdk = _FakeSDK()
                factory = _SequenceFactory((failed_sdk, unused_sdk))
                first_manager = self.manager(
                    api_key=f"{API_KEY}-market-{scenario_index}",
                    sdk_factory=factory,
                    monotonic_clock=clock,
                )
                second_manager = self.manager(
                    api_key=f"{API_KEY}-market-{scenario_index}",
                    sdk_factory=factory,
                    monotonic_clock=clock,
                )

                with self.assertRaises(FubonSessionError):
                    first_manager.session()
                with self.assertRaises(FubonAuthenticationCooldownError):
                    second_manager.session()

                self.assertEqual(1, factory.calls)
                self.assertEqual(0, unused_sdk.login_calls)

    def test_session_timeout_is_bounded_and_worker_can_finish_later(self):
        sdk = _BlockingSDK()
        self.addCleanup(sdk.login_release.set)
        manager = self.manager(sdk_factory=lambda: sdk)

        started_at = time.monotonic()
        with self.assertRaises(FubonSessionTimeoutError):
            manager.session(timeout_seconds=0.05)
        elapsed = time.monotonic() - started_at

        self.assertLess(elapsed, 0.5)
        self.assertTrue(sdk.login_started.is_set())
        self.assertEqual(1, sdk.login_calls)

        sdk.login_release.set()
        session = manager.session(timeout_seconds=1.0)
        self.assertEqual(SDK_TOKEN, session.sdk_token)
        self.assertEqual(1, sdk.login_calls)
        manager.close()

    def test_close_returns_promptly_and_wakes_waiter_during_hung_login(self):
        sdk = _BlockingSDK()
        self.addCleanup(sdk.login_release.set)
        manager = self.manager(sdk_factory=lambda: sdk)

        with ThreadPoolExecutor(max_workers=1) as executor:
            waiting_session = executor.submit(manager.session)
            self.assertTrue(sdk.login_started.wait(timeout=1.0))

            started_at = time.monotonic()
            manager.close()
            elapsed = time.monotonic() - started_at

            self.assertLess(elapsed, 0.5)
            with self.assertRaisesRegex(FubonSessionError, "closed"):
                waiting_session.result(timeout=0.5)

        sdk.login_release.set()
        self.assertTrue(sdk.logout_finished.wait(timeout=1.0))
        self.assertEqual(1, sdk.logout_calls)
        with self.assertRaisesRegex(FubonSessionError, "closed"):
            manager.session(timeout_seconds=0.1)

    def test_close_returns_promptly_when_sdk_logout_hangs(self):
        sdk = _HungLogoutSDK()
        self.addCleanup(sdk.logout_release.set)
        manager = self.manager(sdk_factory=lambda: sdk)
        manager.session()

        started_at = time.monotonic()
        manager.close()
        elapsed = time.monotonic() - started_at

        self.assertLess(elapsed, 0.5)
        self.assertTrue(sdk.logout_started.wait(timeout=1.0))
        self.assertFalse(sdk.logout_finished.is_set())
        with self.assertRaisesRegex(FubonSessionError, "closed"):
            manager.session(timeout_seconds=0.1)

        sdk.logout_release.set()
        self.assertTrue(sdk.logout_finished.wait(timeout=1.0))
        self.assertEqual(1, sdk.logout_calls)

    def test_invalidate_discards_and_logs_out_late_worker_result(self):
        blocked_sdk = _BlockingSDK(sdk_token=f"{SDK_TOKEN}-late")
        replacement_sdk = _FakeSDK(sdk_token=f"{SDK_TOKEN}-replacement")
        self.addCleanup(blocked_sdk.login_release.set)
        factory = _SequenceFactory((blocked_sdk, replacement_sdk))
        manager = self.manager(sdk_factory=factory)

        with ThreadPoolExecutor(max_workers=1) as executor:
            waiting_session = executor.submit(manager.session)
            self.assertTrue(blocked_sdk.login_started.wait(timeout=1.0))
            manager.invalidate()
            with self.assertRaisesRegex(FubonSessionError, "invalidated"):
                waiting_session.result(timeout=0.5)

        blocked_sdk.login_release.set()
        self.assertTrue(blocked_sdk.logout_finished.wait(timeout=1.0))
        self.assertEqual(1, blocked_sdk.logout_calls)

        replacement = manager.session(timeout_seconds=1.0)
        self.assertEqual(
            f"{SDK_TOKEN}-replacement",
            replacement.sdk_token,
        )
        self.assertEqual(2, factory.calls)
        self.assertEqual(1, replacement_sdk.login_calls)
        manager.close()

    def test_invalidate_returns_promptly_when_sdk_logout_hangs(self):
        old_sdk = _HungLogoutSDK(sdk_token=f"{SDK_TOKEN}-old")
        replacement_sdk = _FakeSDK(
            sdk_token=f"{SDK_TOKEN}-replacement"
        )
        self.addCleanup(old_sdk.logout_release.set)
        factory = _SequenceFactory((old_sdk, replacement_sdk))
        manager = self.manager(sdk_factory=factory)
        old_session = manager.session()

        started_at = time.monotonic()
        manager.invalidate()
        elapsed = time.monotonic() - started_at

        self.assertLess(elapsed, 0.5)
        self.assertTrue(old_sdk.logout_started.wait(timeout=1.0))
        self.assertFalse(old_sdk.logout_finished.is_set())

        replacement_session = manager.session(timeout_seconds=1.0)
        self.assertIsNot(old_session, replacement_session)
        self.assertEqual(
            f"{SDK_TOKEN}-replacement",
            replacement_session.sdk_token,
        )
        self.assertEqual(2, factory.calls)
        self.assertEqual(1, old_sdk.login_calls)
        self.assertEqual(1, replacement_sdk.login_calls)

        old_sdk.logout_release.set()
        self.assertTrue(old_sdk.logout_finished.wait(timeout=1.0))
        self.assertEqual(1, old_sdk.logout_calls)
        manager.close()

    def test_authentication_invalidation_installs_cooldown_before_relogin(self):
        initial_sdk = _FakeSDK(sdk_token=f"{SDK_TOKEN}-initial")
        forbidden_relogin = _BlockingSDK(
            sdk_token=f"{SDK_TOKEN}-forbidden"
        )
        self.addCleanup(forbidden_relogin.login_release.set)
        factory = _SequenceFactory((initial_sdk, forbidden_relogin))
        manager = self.manager(sdk_factory=factory)
        manager.session()

        record_started = threading.Event()
        allow_record = threading.Event()
        self.addCleanup(allow_record.set)
        original_record = manager._record_authentication_failure

        def blocked_record(breaker):
            record_started.set()
            allow_record.wait()
            original_record(breaker)

        with (
            patch.object(
                manager,
                "_record_authentication_failure",
                side_effect=blocked_record,
            ),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            invalidation = executor.submit(
                manager.invalidate,
                authentication_failure=True,
            )
            self.assertTrue(record_started.wait(timeout=1.0))

            concurrent_session = executor.submit(
                manager.session,
                1.0,
            )
            self.assertFalse(
                forbidden_relogin.login_started.wait(timeout=0.1)
            )
            self.assertEqual(1, factory.calls)

            allow_record.set()
            invalidation.result(timeout=1.0)
            with self.assertRaises(FubonAuthenticationCooldownError):
                concurrent_session.result(timeout=1.0)

        self.assertEqual(1, factory.calls)
        self.assertEqual(0, forbidden_relogin.login_calls)

    def test_authentication_invalidation_gate_is_shared_across_managers(self):
        initial_sdk = _FakeSDK(sdk_token=f"{SDK_TOKEN}-initial")
        forbidden_relogin = _BlockingSDK(
            sdk_token=f"{SDK_TOKEN}-forbidden"
        )
        self.addCleanup(forbidden_relogin.login_release.set)
        invalidating_manager = self.manager(
            sdk_factory=lambda: initial_sdk
        )
        competing_manager = self.manager(
            sdk_factory=lambda: forbidden_relogin
        )
        invalidating_manager.session()

        record_started = threading.Event()
        allow_record = threading.Event()
        self.addCleanup(allow_record.set)
        original_install = (
            invalidating_manager._install_authentication_failure
        )

        def blocked_install(breaker):
            record_started.set()
            allow_record.wait()
            original_install(breaker)

        with (
            patch.object(
                invalidating_manager,
                "_install_authentication_failure",
                side_effect=blocked_install,
            ),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            invalidation = executor.submit(
                invalidating_manager.invalidate,
                authentication_failure=True,
            )
            self.assertTrue(record_started.wait(timeout=1.0))

            competing_session = executor.submit(
                competing_manager.session,
                1.0,
            )
            with self.assertRaises(FubonAuthenticationCooldownError):
                competing_session.result(timeout=1.0)
            self.assertEqual(0, forbidden_relogin.login_calls)

            allow_record.set()
            invalidation.result(timeout=1.0)

        with self.assertRaises(FubonAuthenticationCooldownError):
            competing_manager.session(timeout_seconds=0.1)
        self.assertEqual(0, forbidden_relogin.login_calls)

    def test_preexisting_cross_manager_login_cannot_clear_invalidation(self):
        clock = _FakeMonotonic()
        blocked_sdk = _BlockingSDK(
            sdk_token=f"{SDK_TOKEN}-must-not-publish"
        )
        self.addCleanup(blocked_sdk.login_release.set)
        invalidating_manager = self.manager(
            sdk_factory=_FakeSDK,
            monotonic_clock=clock,
        )
        inflight_manager = self.manager(
            sdk_factory=lambda: blocked_sdk,
            monotonic_clock=clock,
        )

        with ThreadPoolExecutor(max_workers=1) as executor:
            inflight_session = executor.submit(
                inflight_manager.session,
                1.0,
            )
            self.assertTrue(blocked_sdk.login_started.wait(timeout=1.0))

            invalidating_manager.invalidate(authentication_failure=True)
            breaker = invalidating_manager._current_breaker()
            self.assertIsNotNone(breaker)
            with breaker.condition:
                invalidation_epoch = breaker.invalidation_epoch
                failures_before_release = breaker.consecutive_failures
                blocked_until_before_release = breaker.blocked_until

            self.assertGreaterEqual(invalidation_epoch, 1)
            self.assertEqual(1, failures_before_release)
            self.assertEqual(60.0, blocked_until_before_release)

            blocked_sdk.login_release.set()
            with self.assertRaises(FubonAuthenticationCooldownError):
                inflight_session.result(timeout=1.0)

        self.assertTrue(blocked_sdk.logout_finished.wait(timeout=1.0))
        self.assertEqual(1, blocked_sdk.login_calls)
        self.assertEqual(1, blocked_sdk.logout_calls)
        self.assertIsNone(inflight_manager._session)
        self.assertIsNone(inflight_manager._sdk)

        with breaker.condition:
            self.assertEqual(
                failures_before_release,
                breaker.consecutive_failures,
            )
            self.assertEqual(
                blocked_until_before_release,
                breaker.blocked_until,
            )
            self.assertEqual(
                invalidation_epoch,
                breaker.invalidation_epoch,
            )
        with self.assertRaises(FubonAuthenticationCooldownError):
            inflight_manager.session(timeout_seconds=0.1)
        self.assertEqual(1, blocked_sdk.login_calls)

    def test_epoch_is_rechecked_atomically_at_session_publish(self):
        clock = _FakeMonotonic()
        blocked_sdk = _BlockingSDK(
            sdk_token=f"{SDK_TOKEN}-publish-race"
        )
        self.addCleanup(blocked_sdk.login_release.set)
        invalidating_manager = self.manager(
            sdk_factory=_FakeSDK,
            monotonic_clock=clock,
        )
        inflight_manager = self.manager(
            sdk_factory=lambda: blocked_sdk,
            monotonic_clock=clock,
        )
        reset_completed = threading.Event()
        original_reset = inflight_manager._reset_authentication_breaker

        def reset_and_signal(breaker):
            original_reset(breaker)
            reset_completed.set()

        with (
            patch.object(
                inflight_manager,
                "_reset_authentication_breaker",
                side_effect=reset_and_signal,
            ),
            ThreadPoolExecutor(max_workers=1) as executor,
        ):
            inflight_session = executor.submit(
                inflight_manager.session,
                1.0,
            )
            self.assertTrue(blocked_sdk.login_started.wait(timeout=1.0))

            with inflight_manager._lock:
                blocked_sdk.login_release.set()
                self.assertTrue(reset_completed.wait(timeout=1.0))
                invalidating_manager.invalidate(
                    authentication_failure=True
                )

            with self.assertRaises(FubonAuthenticationCooldownError):
                inflight_session.result(timeout=1.0)

        self.assertTrue(blocked_sdk.logout_finished.wait(timeout=1.0))
        self.assertIsNone(inflight_manager._session)
        self.assertIsNone(inflight_manager._sdk)
        self.assertIsNone(inflight_manager._session_invalidation_epoch)
        self.assertEqual(1, blocked_sdk.login_calls)
        self.assertEqual(1, blocked_sdk.logout_calls)

    def test_cached_session_epoch_is_checked_before_caller_return(self):
        sdk = _FakeSDK(sdk_token=f"{SDK_TOKEN}-cached-race")
        invalidating_manager = self.manager(sdk_factory=_FakeSDK)
        session_manager = self.manager(sdk_factory=lambda: sdk)
        cache_check_started = threading.Event()
        allow_cache_check = threading.Event()
        self.addCleanup(allow_cache_check.set)
        original_check = session_manager._validated_cached_session_locked

        def blocked_cache_check():
            cache_check_started.set()
            allow_cache_check.wait()
            return original_check()

        with (
            patch.object(
                session_manager,
                "_validated_cached_session_locked",
                side_effect=blocked_cache_check,
            ),
            ThreadPoolExecutor(max_workers=1) as executor,
        ):
            pending_session = executor.submit(
                session_manager.session,
                1.0,
            )
            self.assertTrue(cache_check_started.wait(timeout=1.0))

            invalidating_manager.invalidate(authentication_failure=True)
            allow_cache_check.set()
            with self.assertRaises(FubonAuthenticationCooldownError):
                pending_session.result(timeout=1.0)

        self.assertIsNone(session_manager._session)
        self.assertIsNone(session_manager._sdk)
        self.assertIsNone(session_manager._session_invalidation_epoch)
        self.assertEqual(1, sdk.login_calls)
        self.assertEqual(1, sdk.logout_calls)

    def test_auth_failure_finishes_before_hung_logout_cleanup(self):
        sdk = _HungLogoutSDK(
            login_result=SimpleNamespace(is_success=False)
        )
        self.addCleanup(sdk.logout_release.set)
        manager = self.manager(sdk_factory=lambda: sdk)

        started_at = time.monotonic()
        with self.assertRaises(FubonAuthenticationError):
            manager.session(timeout_seconds=0.5)
        elapsed = time.monotonic() - started_at

        self.assertLess(elapsed, 0.5)
        self.assertTrue(sdk.logout_started.wait(timeout=1.0))
        self.assertFalse(sdk.logout_finished.is_set())
        self.assertIsNone(manager._attempt)
        with self.assertRaises(FubonAuthenticationCooldownError):
            manager.session(timeout_seconds=0.1)

        sdk.logout_release.set()
        self.assertTrue(sdk.logout_finished.wait(timeout=1.0))
        self.assertEqual(1, sdk.logout_calls)

    def test_concurrent_bounded_callers_share_one_daemon_attempt(self):
        sdk = _BlockingSDK()
        self.addCleanup(sdk.login_release.set)
        factory = _SequenceFactory((sdk,))
        manager = self.manager(sdk_factory=factory)

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [
                executor.submit(manager.session, 1.0)
                for _ in range(8)
            ]
            self.assertTrue(sdk.login_started.wait(timeout=1.0))
            self.assertEqual(1, factory.calls)
            self.assertEqual(1, sdk.login_calls)
            sdk.login_release.set()
            sessions = [future.result(timeout=1.0) for future in futures]

        self.assertTrue(all(session is sessions[0] for session in sessions))
        self.assertEqual(1, factory.calls)
        self.assertEqual(1, sdk.login_calls)
        manager.close()

    def test_session_timeout_must_be_positive_and_finite(self):
        manager = self.manager(sdk_factory=_FakeSDK)

        for value in (0, -1, float("inf"), float("nan"), True, "invalid"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "positive finite"):
                    manager.session(timeout_seconds=value)

    def test_close_is_idempotent_and_best_effort_logs_out(self):
        sdk = _FakeSDK()
        manager = self.manager(sdk_factory=lambda: sdk)
        manager.session()

        manager.close()
        manager.close()

        self.assertEqual(1, sdk.logout_calls)
        with self.assertRaisesRegex(FubonSessionError, "closed"):
            manager.session()


if __name__ == "__main__":
    unittest.main()
