from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.bot import DiscordManagerBot
from src.config import Config


class FakeHistoryChannel:
    def __init__(self, messages: list[object]) -> None:
        self.messages = messages
        self.history_after: datetime | None = None
        self.history_oldest_first: bool | None = None

    def history(self, *, after: datetime, oldest_first: bool):
        self.history_after = after
        self.history_oldest_first = oldest_first

        async def iterator():
            for message in self.messages:
                yield message

        return iterator()


class StartupBackfillTest(unittest.IsolatedAsyncioTestCase):
    def make_config(self) -> Config:
        return Config(
            discord_token="token",
            source_channel_ids={123},
            stats_channel_id=456,
            mod_log_channel_id=789,
            openai_api_key="",
            openai_model="gpt-4.1-mini",
            stats_interval_cron="*/30 * * * *",
            stats_backfill_hours=6,
            stats_reset_after_report=True,
            keywords=["早安"],
            top_word_limit=10,
            enable_ai_moderation=False,
            moderation_action="log",
            direct_reply_text="提醒",
            delete_violating_messages=False,
            min_message_length_for_ai=3,
            rules_text="規則",
            rules_file_path=None,
            rules_file_error=None,
        )

    async def test_backfill_records_non_bot_messages_from_source_channels(self) -> None:
        user_message = SimpleNamespace(
            content="早安 大家",
            author=SimpleNamespace(id=1, bot=False),
            channel=SimpleNamespace(id=123),
        )
        bot_message = SimpleNamespace(
            content="早安",
            author=SimpleNamespace(id=2, bot=True),
            channel=SimpleNamespace(id=123),
        )
        channel = FakeHistoryChannel([user_message, bot_message])
        client = DiscordManagerBot(self.make_config())
        client.fetch_channel = AsyncMock(return_value=channel)  # type: ignore[method-assign]

        await client.backfill_startup_stats()

        self.assertEqual(client.stats.message_count, 1)
        self.assertEqual(client.stats.keyword_counts["早安"], 1)
        self.assertEqual(channel.history_oldest_first, True)
        self.assertIsNotNone(channel.history_after)
        self.assertEqual(channel.history_after.tzinfo, timezone.utc)

    async def test_stats_command_can_run_from_mod_log_channel(self) -> None:
        client = DiscordManagerBot(self.make_config())
        message = SimpleNamespace(
            guild=SimpleNamespace(id=1),
            content="!dcstats",
            author=SimpleNamespace(
                bot=False,
                guild_permissions=SimpleNamespace(manage_guild=True),
            ),
            channel=SimpleNamespace(id=789),
            reply=AsyncMock(),
        )

        await client.on_message(message)

        message.reply.assert_awaited_once()
        reply_text = message.reply.await_args.args[0]
        self.assertIn("**頻道統計摘要**", reply_text)

    async def test_stats_command_sends_followup_chunks_for_long_reports(self) -> None:
        client = DiscordManagerBot(self.make_config())
        client.stats.render_chunks = unittest.mock.Mock(return_value=["第一段", "第二段"])  # type: ignore[method-assign]
        message = SimpleNamespace(
            guild=SimpleNamespace(id=1),
            content="!dcstats",
            author=SimpleNamespace(
                bot=False,
                guild_permissions=SimpleNamespace(manage_guild=True),
            ),
            channel=SimpleNamespace(id=789, send=AsyncMock()),
            reply=AsyncMock(),
        )

        await client.on_message(message)

        message.reply.assert_awaited_once_with(
            "第一段",
            mention_author=False,
            allowed_mentions=unittest.mock.ANY,
        )
        message.channel.send.assert_awaited_once_with(
            "第二段",
            allowed_mentions=unittest.mock.ANY,
        )

    async def test_stats_command_with_hours_uses_temporary_backfill_report(self) -> None:
        client = DiscordManagerBot(self.make_config())
        report_stats = unittest.mock.Mock()
        report_stats.render_chunks.return_value = ["最近 2 小時報告"]
        client.build_history_stats = AsyncMock(return_value=report_stats)  # type: ignore[method-assign]
        message = SimpleNamespace(
            guild=SimpleNamespace(id=1),
            content="!dcstats 2",
            author=SimpleNamespace(
                bot=False,
                guild_permissions=SimpleNamespace(manage_guild=True),
            ),
            channel=SimpleNamespace(id=789, send=AsyncMock()),
            reply=AsyncMock(),
        )

        await client.on_message(message)

        client.build_history_stats.assert_awaited_once_with(2)
        message.reply.assert_awaited_once()
        self.assertEqual(message.reply.await_args.args[0], "最近 2 小時報告")

    async def test_stats_command_with_invalid_hours_replies_usage(self) -> None:
        client = DiscordManagerBot(self.make_config())
        message = SimpleNamespace(
            guild=SimpleNamespace(id=1),
            content="!dcstats abc",
            author=SimpleNamespace(
                bot=False,
                guild_permissions=SimpleNamespace(manage_guild=True),
            ),
            channel=SimpleNamespace(id=789, send=AsyncMock()),
            reply=AsyncMock(),
        )

        await client.on_message(message)

        message.reply.assert_awaited_once()
        self.assertIn("用法", message.reply.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
