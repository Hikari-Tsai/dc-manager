from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.config import load_config, validate_config


class ConfigRulesFileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.original_env = os.environ.copy()
        for key in [
            "RULES_FILE",
            "RULES_TEXT",
            "DISCORD_TOKEN",
            "SOURCE_CHANNEL_IDS",
            "STATS_CHANNEL_ID",
            "MOD_LOG_CHANNEL_ID",
            "OPENAI_API_KEY",
            "STATS_BACKFILL_HOURS",
        ]:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_load_config_uses_rules_file_when_configured(self) -> None:
        with TemporaryDirectory() as temp_dir:
            rules_path = Path(temp_dir) / "rules.txt"
            rules_path.write_text("禁止洗頻\n禁止人身攻擊\n", encoding="utf-8")
            os.environ["RULES_FILE"] = str(rules_path)
            os.environ["RULES_TEXT"] = "這段不應該被使用"

            config = load_config()

        self.assertEqual(config.rules_text, "禁止洗頻\n禁止人身攻擊")
        self.assertIsNone(config.rules_file_error)

    def test_validate_config_reports_missing_rules_file_when_configured(self) -> None:
        os.environ["RULES_FILE"] = "/tmp/does-not-exist-rules.txt"

        config = load_config()
        errors = validate_config(config)

        self.assertIn("RULES_FILE cannot be read: /tmp/does-not-exist-rules.txt", errors)
        self.assertNotEqual(config.rules_text, "備援文字")

    def test_load_config_uses_rules_text_when_rules_file_is_not_configured(self) -> None:
        os.environ["RULES_TEXT"] = "禁止惡意連結"

        config = load_config()

        self.assertEqual(config.rules_text, "禁止惡意連結")
        self.assertIsNone(config.rules_file_error)

    def test_load_config_reads_stats_backfill_hours(self) -> None:
        os.environ["STATS_BACKFILL_HOURS"] = "6"

        config = load_config()

        self.assertEqual(config.stats_backfill_hours, 6)

    def test_load_config_defaults_invalid_stats_backfill_hours(self) -> None:
        os.environ["STATS_BACKFILL_HOURS"] = "-1"

        config = load_config()

        self.assertEqual(config.stats_backfill_hours, 6)


if __name__ == "__main__":
    unittest.main()
