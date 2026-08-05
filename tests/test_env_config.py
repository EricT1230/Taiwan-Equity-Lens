import os
import traceback
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from taiwan_stock_analysis.env_config import load_project_env, project_env_path


SUPPORTED_ENV_KEYS = (
    "FUBON_API_KEY",
    "FUBON_CERT_PASSWORD",
    "FUBON_CERT_PATH",
    "FUBON_MARKET_DATA_ONLY_CONFIRMED",
    "FUBON_PERSONAL_ID",
    "FUBON_REDISPLAY_LICENSED",
    "FUBON_TAIEX_SYMBOL",
    "FUBON_TPEX_SYMBOL",
    "FUGLE_API_KEY",
    "MARKET_DATA_PROVIDER",
    "FUGLE_REDISPLAY_LICENSED",
    "FUGLE_TAIEX_SYMBOL",
    "FUGLE_TPEX_SYMBOL",
)


class ProjectEnvPathTests(unittest.TestCase):
    def test_project_env_path_is_repo_root_independent_of_working_directory(self):
        expected = Path(__file__).resolve().parents[1] / ".env"
        original_working_directory = Path.cwd()

        with TemporaryDirectory() as temporary_directory:
            try:
                os.chdir(temporary_directory)
                actual = project_env_path()
            finally:
                os.chdir(original_working_directory)

        self.assertEqual(expected, actual)


class LoadProjectEnvTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.env_path = Path(self.temporary_directory.name) / ".env"

    def write_env(self, content: str) -> None:
        self.env_path.write_text(content, encoding="utf-8")

    def test_missing_file_is_a_noop(self):
        missing_path = Path(self.temporary_directory.name) / "missing.env"
        original_environment = {
            "FUGLE_API_KEY": "process-secret",
            "UNRELATED": "preserve-me",
        }

        with patch.dict(os.environ, original_environment, clear=True):
            loaded = load_project_env(missing_path)

            self.assertEqual((), loaded)
            self.assertEqual(original_environment, dict(os.environ))

    def test_default_path_uses_project_env_path(self):
        self.write_env("MARKET_DATA_PROVIDER=fugle\n")

        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "taiwan_stock_analysis.env_config.project_env_path",
                return_value=self.env_path,
            ),
        ):
            loaded = load_project_env()

            self.assertEqual(("MARKET_DATA_PROVIDER",), loaded)
            self.assertEqual("fugle", os.environ["MARKET_DATA_PROVIDER"])

    def test_loads_supported_syntax_and_ignores_unknown_variables(self):
        self.write_env(
            "\n"
            "  # project market-data settings\n"
            'FUBON_API_KEY = "fubon key #1=primary"\n'
            "FUBON_CERT_PASSWORD = cert-pass\n"
            "FUBON_CERT_PATH = certificates/user.pfx\n"
            "FUBON_MARKET_DATA_ONLY_CONFIRMED = 1\n"
            "FUBON_PERSONAL_ID = A123456789\n"
            "FUBON_REDISPLAY_LICENSED = 0\n"
            "FUBON_TAIEX_SYMBOL = IX0001\n"
            "FUBON_TPEX_SYMBOL = IX0043\n"
            'export FUGLE_API_KEY = "api key #1=primary" # operator note\n'
            "MARKET_DATA_PROVIDER=fubon # selected provider\n"
            "FUGLE_REDISPLAY_LICENSED = '1' # licensed\n"
            'FUGLE_TAIEX_SYMBOL="台灣 加權 # 指數 📈"\n'
            "FUGLE_TPEX_SYMBOL = o00\n"
            "UNSUPPORTED_SECRET=must-not-be-loaded\n"
        )

        with patch.dict(os.environ, {}, clear=True):
            loaded = load_project_env(self.env_path)

            self.assertEqual(SUPPORTED_ENV_KEYS, loaded)
            self.assertEqual("fubon key #1=primary", os.environ["FUBON_API_KEY"])
            self.assertEqual("cert-pass", os.environ["FUBON_CERT_PASSWORD"])
            self.assertEqual("certificates/user.pfx", os.environ["FUBON_CERT_PATH"])
            self.assertEqual(
                "1",
                os.environ["FUBON_MARKET_DATA_ONLY_CONFIRMED"],
            )
            self.assertEqual("A123456789", os.environ["FUBON_PERSONAL_ID"])
            self.assertEqual("0", os.environ["FUBON_REDISPLAY_LICENSED"])
            self.assertEqual("IX0001", os.environ["FUBON_TAIEX_SYMBOL"])
            self.assertEqual("IX0043", os.environ["FUBON_TPEX_SYMBOL"])
            self.assertEqual("api key #1=primary", os.environ["FUGLE_API_KEY"])
            self.assertEqual("fubon", os.environ["MARKET_DATA_PROVIDER"])
            self.assertEqual("1", os.environ["FUGLE_REDISPLAY_LICENSED"])
            self.assertEqual("台灣 加權 # 指數 📈", os.environ["FUGLE_TAIEX_SYMBOL"])
            self.assertEqual("o00", os.environ["FUGLE_TPEX_SYMBOL"])
            self.assertNotIn("UNSUPPORTED_SECRET", os.environ)

    def test_existing_process_values_win_even_when_empty(self):
        self.write_env(
            "FUGLE_API_KEY=file-secret\n"
            "MARKET_DATA_PROVIDER=fugle\n"
            "FUGLE_REDISPLAY_LICENSED=1\n"
        )

        with patch.dict(
            os.environ,
            {
                "FUGLE_API_KEY": "process-secret",
                "MARKET_DATA_PROVIDER": "",
            },
            clear=True,
        ):
            loaded = load_project_env(self.env_path)

            self.assertEqual(("FUGLE_REDISPLAY_LICENSED",), loaded)
            self.assertEqual("process-secret", os.environ["FUGLE_API_KEY"])
            self.assertEqual("", os.environ["MARKET_DATA_PROVIDER"])
            self.assertEqual("1", os.environ["FUGLE_REDISPLAY_LICENSED"])

    def test_invalid_shadowed_file_values_do_not_block_process_values(self):
        self.write_env(
            "MARKET_DATA_PROVIDER=not-a-provider\n"
            "FUGLE_REDISPLAY_LICENSED=maybe\n"
        )
        original_environment = {
            "MARKET_DATA_PROVIDER": "fugle",
            "FUGLE_REDISPLAY_LICENSED": "0",
        }

        with patch.dict(
            os.environ,
            original_environment,
            clear=True,
        ):
            loaded = load_project_env(self.env_path)

            self.assertEqual((), loaded)
            self.assertEqual(original_environment, dict(os.environ))

    def test_utf8_bom_is_accepted(self):
        self.write_env("\ufeffFUGLE_TAIEX_SYMBOL=IX0001\n")

        with patch.dict(os.environ, {}, clear=True):
            loaded = load_project_env(self.env_path)

            self.assertEqual(("FUGLE_TAIEX_SYMBOL",), loaded)
            self.assertEqual("IX0001", os.environ["FUGLE_TAIEX_SYMBOL"])

    def test_invalid_known_settings_are_rejected(self):
        invalid_values = (
            ("MARKET_DATA_PROVIDER=not-a-provider\n", "MARKET_DATA_PROVIDER"),
            (
                "FUBON_MARKET_DATA_ONLY_CONFIRMED=maybe\n",
                "FUBON_MARKET_DATA_ONLY_CONFIRMED",
            ),
            ("FUBON_REDISPLAY_LICENSED=maybe\n", "FUBON_REDISPLAY_LICENSED"),
            ("FUGLE_REDISPLAY_LICENSED=maybe\n", "FUGLE_REDISPLAY_LICENSED"),
        )

        for content, setting_name in invalid_values:
            with self.subTest(setting_name=setting_name):
                self.write_env(content)
                with patch.dict(os.environ, {}, clear=True):
                    with self.assertRaises(ValueError) as raised:
                        load_project_env(self.env_path)

                    self.assertNotIn(setting_name, os.environ)
                self.assertIn(setting_name, str(raised.exception))
                self.assertNotIn("not-a-provider", str(raised.exception))
                self.assertNotIn("maybe", str(raised.exception))

    def test_invalid_files_fail_before_modifying_environment(self):
        oversized = Path(self.temporary_directory.name) / "oversized.env"
        oversized.write_bytes(
            b"FUGLE_API_KEY=" + (b"x" * (64 * 1024))
        )
        invalid_utf8 = Path(self.temporary_directory.name) / "invalid.env"
        invalid_utf8.write_bytes(b"FUGLE_API_KEY=\xff")
        directory = Path(self.temporary_directory.name) / "directory.env"
        directory.mkdir()

        for path in (oversized, invalid_utf8, directory):
            with self.subTest(path=path.name):
                original_environment = {"UNRELATED": "preserve-me"}
                with patch.dict(
                    os.environ,
                    original_environment,
                    clear=True,
                ):
                    with self.assertRaises(ValueError) as raised:
                        load_project_env(path)
                    self.assertEqual(
                        original_environment,
                        dict(os.environ),
                    )
                self.assertIsNone(raised.exception.__cause__)

    def test_decoded_nul_value_fails_atomically(self):
        self.write_env(
            "MARKET_DATA_PROVIDER=fugle\n"
            'FUGLE_API_KEY="secret\\u0000suffix"\n'
        )

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as raised:
                load_project_env(self.env_path)
            self.assertNotIn("MARKET_DATA_PROVIDER", os.environ)
            self.assertNotIn("FUGLE_API_KEY", os.environ)

        self.assertNotIn("secret", str(raised.exception))

    def test_shell_metacharacters_are_loaded_as_literal_text(self):
        literal_value = r"$(whoami) `${HOME}` %USERNAME%"
        self.write_env(f'FUGLE_API_KEY="{literal_value}"\n')

        with patch.dict(os.environ, {}, clear=True):
            load_project_env(self.env_path)

            self.assertEqual(literal_value, os.environ["FUGLE_API_KEY"])

    def test_malformed_input_fails_atomically_without_disclosing_secrets(self):
        secret = "do-not-leak-this-secret"
        malformed_line = 'FUGLE_API_KEY="unterminated-secret-value'
        self.write_env(
            "MARKET_DATA_PROVIDER=fugle\n"
            f"{malformed_line}\n"
            f"FUGLE_TPEX_SYMBOL={secret}\n"
        )
        original_environment = {
            "FUGLE_REDISPLAY_LICENSED": "existing-value",
            "UNRELATED": "preserve-me",
        }

        with patch.dict(os.environ, original_environment, clear=True):
            with self.assertRaises(ValueError) as raised:
                load_project_env(self.env_path)

            self.assertEqual(original_environment, dict(os.environ))

        message = str(raised.exception)
        self.assertNotIn(secret, message)
        self.assertNotIn("unterminated-secret-value", message)
        self.assertNotIn(malformed_line, message)
        self.assertIn("2", message)

    def test_chained_parse_traceback_does_not_disclose_secret_value(self):
        secret = "do-not-leak-through-traceback"
        self.write_env(f'FUGLE_API_KEY="{secret}\\q"\n')

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as raised:
                load_project_env(self.env_path)

        formatted = "".join(
            traceback.format_exception(raised.exception)
        )
        self.assertNotIn(secret, formatted)
        self.assertIsNone(raised.exception.__cause__)


if __name__ == "__main__":
    unittest.main()
