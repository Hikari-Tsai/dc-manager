from __future__ import annotations

import unittest
from dataclasses import replace
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
            moderation_min_confidence=0.75,
            moderation_bypass_user_ids=set(),
            moderation_bypass_role_ids=set(),
            moderation_bypass_administrators=True,
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

    async def test_send_command_forwards_message_from_mod_log_channel(self) -> None:
        client = DiscordManagerBot(replace(self.make_config(), source_channel_ids={123, 124}))
        first_channel = SimpleNamespace(send=AsyncMock())
        second_channel = SimpleNamespace(send=AsyncMock())
        channels = {123: first_channel, 124: second_channel}
        client.fetch_sendable_channel = AsyncMock(side_effect=lambda channel_id: channels[channel_id])  # type: ignore[method-assign]
        message = SimpleNamespace(
            guild=SimpleNamespace(id=1),
            content="/send 今天晚上 8 點開台",
            author=SimpleNamespace(
                bot=False,
                guild_permissions=SimpleNamespace(manage_guild=True),
            ),
            channel=SimpleNamespace(id=789),
            reply=AsyncMock(),
        )

        await client.on_message(message)

        first_channel.send.assert_awaited_once_with(
            "今天晚上 8 點開台",
            allowed_mentions=unittest.mock.ANY,
        )
        second_channel.send.assert_awaited_once_with(
            "今天晚上 8 點開台",
            allowed_mentions=unittest.mock.ANY,
        )
        message.reply.assert_awaited_once()
        self.assertIn("已轉發到 2 個來源頻道", message.reply.await_args.args[0])

    async def test_bang_send_command_forwards_message_from_mod_log_channel(self) -> None:
        client = DiscordManagerBot(self.make_config())
        channel = SimpleNamespace(send=AsyncMock())
        client.fetch_sendable_channel = AsyncMock(return_value=channel)  # type: ignore[method-assign]
        message = SimpleNamespace(
            guild=SimpleNamespace(id=1),
            content="!send 今天晚上 8 點開台",
            author=SimpleNamespace(
                bot=False,
                guild_permissions=SimpleNamespace(manage_guild=True),
            ),
            channel=SimpleNamespace(id=789),
            reply=AsyncMock(),
        )

        await client.on_message(message)

        channel.send.assert_awaited_once_with(
            "今天晚上 8 點開台",
            allowed_mentions=unittest.mock.ANY,
        )
        message.reply.assert_awaited_once()

    async def test_send_command_requires_manage_guild_permission(self) -> None:
        client = DiscordManagerBot(self.make_config())
        client.fetch_sendable_channel = AsyncMock()  # type: ignore[method-assign]
        message = SimpleNamespace(
            guild=SimpleNamespace(id=1),
            content="/send 測試",
            author=SimpleNamespace(
                bot=False,
                guild_permissions=SimpleNamespace(manage_guild=False),
            ),
            channel=SimpleNamespace(id=789),
            reply=AsyncMock(),
        )

        await client.on_message(message)

        client.fetch_sendable_channel.assert_not_awaited()
        message.reply.assert_awaited_once()
        self.assertIn("沒有權限", message.reply.await_args.args[0])

    async def test_send_command_requires_message_content(self) -> None:
        client = DiscordManagerBot(self.make_config())
        client.fetch_sendable_channel = AsyncMock()  # type: ignore[method-assign]
        message = SimpleNamespace(
            guild=SimpleNamespace(id=1),
            content="/send",
            author=SimpleNamespace(
                bot=False,
                guild_permissions=SimpleNamespace(manage_guild=True),
            ),
            channel=SimpleNamespace(id=789),
            reply=AsyncMock(),
        )

        await client.on_message(message)

        client.fetch_sendable_channel.assert_not_awaited()
        message.reply.assert_awaited_once()
        self.assertIn("用法", message.reply.await_args.args[0])

    async def test_send_command_is_ignored_outside_mod_log_channel(self) -> None:
        client = DiscordManagerBot(self.make_config())
        client.fetch_sendable_channel = AsyncMock()  # type: ignore[method-assign]
        client.analyze_message = AsyncMock()  # type: ignore[method-assign]
        message = SimpleNamespace(
            guild=SimpleNamespace(id=1),
            content="/send 測試",
            author=SimpleNamespace(
                id=7,
                bot=False,
                guild_permissions=SimpleNamespace(manage_guild=True),
            ),
            channel=SimpleNamespace(id=123),
            reply=AsyncMock(),
        )

        await client.on_message(message)

        client.fetch_sendable_channel.assert_not_awaited()
        message.reply.assert_not_awaited()
        client.analyze_message.assert_awaited_once_with(message)

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

    async def test_analyze_message_skips_bypassed_user(self) -> None:
        config = replace(
            self.make_config(),
            openai_api_key="test-key",
            enable_ai_moderation=True,
            moderation_bypass_user_ids={42},
        )
        client = DiscordManagerBot(config)
        client.analyzer.analyze = AsyncMock(return_value={"violates": True})  # type: ignore[method-assign]
        client.notify_moderation = AsyncMock()  # type: ignore[method-assign]
        message = SimpleNamespace(
            id=1,
            content="這是一段會被跳過的訊息",
            author=SimpleNamespace(
                id=42,
                roles=[],
                guild_permissions=SimpleNamespace(administrator=False),
            ),
            channel=SimpleNamespace(id=123),
        )

        await client.analyze_message(message)

        client.analyzer.analyze.assert_not_awaited()
        client.notify_moderation.assert_not_awaited()

    async def test_analyze_message_skips_bypassed_role(self) -> None:
        config = replace(
            self.make_config(),
            openai_api_key="test-key",
            enable_ai_moderation=True,
            moderation_bypass_role_ids={99},
        )
        client = DiscordManagerBot(config)
        client.analyzer.analyze = AsyncMock(return_value={"violates": True})  # type: ignore[method-assign]
        message = SimpleNamespace(
            id=1,
            content="這是一段會被跳過的訊息",
            author=SimpleNamespace(
                id=7,
                roles=[SimpleNamespace(id=99)],
                guild_permissions=SimpleNamespace(administrator=False),
            ),
            channel=SimpleNamespace(id=123),
        )

        await client.analyze_message(message)

        client.analyzer.analyze.assert_not_awaited()

    async def test_analyze_message_skips_administrator_by_default(self) -> None:
        config = replace(
            self.make_config(),
            openai_api_key="test-key",
            enable_ai_moderation=True,
        )
        client = DiscordManagerBot(config)
        client.analyzer.analyze = AsyncMock(return_value={"violates": True})  # type: ignore[method-assign]
        message = SimpleNamespace(
            id=1,
            content="這是一段會被跳過的訊息",
            author=SimpleNamespace(
                id=7,
                roles=[],
                guild_permissions=SimpleNamespace(administrator=True),
            ),
            channel=SimpleNamespace(id=123),
        )

        await client.analyze_message(message)

        client.analyzer.analyze.assert_not_awaited()

    async def test_analyze_message_skips_violations_below_confidence_threshold(self) -> None:
        config = replace(
            self.make_config(),
            openai_api_key="test-key",
            enable_ai_moderation=True,
            moderation_min_confidence=0.8,
        )
        client = DiscordManagerBot(config)
        client.analyzer.analyze = AsyncMock(
            return_value={"violates": True, "confidence": 0.79}
        )  # type: ignore[method-assign]
        client.notify_moderation = AsyncMock()  # type: ignore[method-assign]
        message = SimpleNamespace(
            id=1,
            content="這是一段低信心疑似違規訊息",
            author=SimpleNamespace(
                id=7,
                roles=[],
                guild_permissions=SimpleNamespace(administrator=False),
            ),
            channel=SimpleNamespace(id=123),
        )

        await client.analyze_message(message)

        client.analyzer.analyze.assert_awaited_once()
        client.notify_moderation.assert_not_awaited()

    async def test_analyze_message_notifies_violations_at_confidence_threshold(self) -> None:
        config = replace(
            self.make_config(),
            openai_api_key="test-key",
            enable_ai_moderation=True,
            moderation_min_confidence=0.8,
        )
        client = DiscordManagerBot(config)
        result = {"violates": True, "confidence": 0.8}
        client.analyzer.analyze = AsyncMock(return_value=result)  # type: ignore[method-assign]
        client.notify_moderation = AsyncMock()  # type: ignore[method-assign]
        message = SimpleNamespace(
            id=1,
            content="這是一段高信心違規訊息",
            author=SimpleNamespace(
                id=7,
                roles=[],
                guild_permissions=SimpleNamespace(administrator=False),
            ),
            channel=SimpleNamespace(id=123),
        )

        await client.analyze_message(message)

        client.notify_moderation.assert_awaited_once_with(message, result)

    async def test_notify_moderation_uses_traditional_chinese_labels_and_severity(self) -> None:
        config = replace(
            self.make_config(),
            moderation_action="both",
            direct_reply_text="Please adjust your message.",
        )
        client = DiscordManagerBot(config)
        log_channel = SimpleNamespace(send=AsyncMock())
        client.fetch_sendable_channel = AsyncMock(return_value=log_channel)  # type: ignore[method-assign]
        message = SimpleNamespace(
            content="測試違規訊息",
            author=SimpleNamespace(id=1, __str__=lambda self: "測試使用者"),
            channel=SimpleNamespace(id=123),
            jump_url="https://discord.example/messages/1",
            reply=AsyncMock(),
        )

        await client.notify_moderation(
            message,
            {
                "confidence": 0.87,
                "severity": "high",
                "rule": "",
                "reason": "",
            },
        )

        log_channel.send.assert_awaited_once()
        log_text = log_channel.send.await_args.args[0]
        self.assertIn("嚴重度：高", log_text)
        self.assertIn("規則：未指定", log_text)
        self.assertIn("原因：未提供", log_text)
        self.assertNotIn("high", log_text)
        message.reply.assert_awaited_once_with(
            "你的訊息可能違反版規，請調整語氣或內容。",
            mention_author=False,
            allowed_mentions=unittest.mock.ANY,
        )

    async def test_notify_moderation_reply_includes_violated_rule(self) -> None:
        config = replace(
            self.make_config(),
            moderation_action="reply",
            direct_reply_text="請調整你的訊息內容。",
        )
        client = DiscordManagerBot(config)
        message = SimpleNamespace(
            content="測試違規訊息",
            author=SimpleNamespace(id=1),
            channel=SimpleNamespace(id=123),
            jump_url="https://discord.example/messages/1",
            reply=AsyncMock(),
        )

        await client.notify_moderation(
            message,
            {
                "confidence": 0.87,
                "severity": "medium",
                "rule": "禁止人身攻擊",
                "reason": "使用了針對個人的攻擊性措辭。",
            },
        )

        message.reply.assert_awaited_once_with(
            "請調整你的訊息內容。\n可能違反版規：禁止人身攻擊",
            mention_author=False,
            allowed_mentions=unittest.mock.ANY,
        )


if __name__ == "__main__":
    unittest.main()
