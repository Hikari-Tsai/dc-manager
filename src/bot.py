from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import Config
from .moderation import ModerationAnalyzer
from .stats import MessageStats, TAIPEI


logger = logging.getLogger(__name__)


DEFAULT_MODERATION_REPLY_TEXT = "你的訊息可能違反版規，請調整語氣或內容。"
MODERATION_SEVERITY_LABELS = {
    "none": "無",
    "low": "低",
    "medium": "中",
    "high": "高",
}


def moderation_reply_text(configured_text: str, rule: object | None = None) -> str:
    text = (configured_text or "").strip()
    reply_text = text if any("\u4e00" <= char <= "\u9fff" for char in text) else DEFAULT_MODERATION_REPLY_TEXT
    rule_text = str(rule or "").strip()
    if not rule_text:
        return reply_text
    return f"{reply_text}\n可能違反版規：{rule_text}"


class DiscordManagerBot(discord.Client):
    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True

        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.config = config
        self.stats = MessageStats(
            keywords=config.keywords,
            top_word_limit=config.top_word_limit,
        )
        self.analyzer = ModerationAnalyzer(
            api_key=config.openai_api_key,
            model=config.openai_model,
            rules_text=config.rules_text,
        )
        self.scheduler = AsyncIOScheduler()
        self.startup_stats_backfilled = False

    async def setup_hook(self) -> None:
        trigger = CronTrigger.from_crontab(self.config.stats_interval_cron)
        self.scheduler.add_job(self.send_stats_report, trigger)
        self.scheduler.start()

    async def close(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        await super().close()

    async def on_ready(self) -> None:
        logger.info("Ready. Logged in as %s", self.user)
        if self.config.enable_ai_moderation and not self.analyzer.enabled:
            logger.warning("ENABLE_AI_MODERATION=true but OPENAI_API_KEY is empty. AI checks are skipped.")
        if not self.startup_stats_backfilled:
            self.startup_stats_backfilled = True
            await self.backfill_startup_stats()

    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return

        is_source_channel = message.channel.id in self.config.source_channel_ids
        is_mod_log_channel = message.channel.id == self.config.mod_log_channel_id

        if is_mod_log_channel:
            if await self.handle_send_command(message):
                return
            if await self.handle_stats_command(message):
                return
        if not is_source_channel:
            return

        if await self.handle_stats_command(message):
            return

        self.stats.record(message)
        await self.analyze_message(message)

    async def fetch_sendable_channel(self, channel_id: int | None) -> discord.abc.Messageable | None:
        if channel_id is None:
            return None

        channel = self.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(channel_id)
            except discord.HTTPException:
                return None

        return channel if hasattr(channel, "send") else None

    async def backfill_startup_stats(self) -> None:
        if self.config.stats_backfill_hours <= 0:
            return

        self.stats = await self.build_history_stats(self.config.stats_backfill_hours)

        logger.info(
            "Startup stats backfill completed for the last %s hour(s): %s message(s).",
            self.config.stats_backfill_hours,
            self.stats.message_count,
        )

    async def build_history_stats(self, hours: int) -> MessageStats:
        after = datetime.now(timezone.utc) - timedelta(hours=hours)
        stats = MessageStats(
            keywords=self.config.keywords,
            top_word_limit=self.config.top_word_limit,
        )
        stats.reset(started_at=after.astimezone(TAIPEI))

        for channel_id in self.config.source_channel_ids:
            try:
                channel = await self.fetch_channel(channel_id)
            except discord.HTTPException:
                logger.exception("Failed to fetch source channel %s for stats history", channel_id)
                continue

            if not hasattr(channel, "history"):
                logger.warning("Source channel %s does not support message history.", channel_id)
                continue

            try:
                async for message in channel.history(after=after, oldest_first=True):
                    if getattr(message.author, "bot", False):
                        continue
                    stats.record(message)
            except discord.HTTPException:
                logger.exception("Failed to read message history for channel %s", channel_id)

        return stats

    async def send_stats_report(self, reset: bool | None = None) -> None:
        should_reset = self.config.stats_reset_after_report if reset is None else reset
        channel = await self.fetch_sendable_channel(self.config.stats_channel_id)
        if channel is None:
            logger.error("Cannot find STATS_CHANNEL_ID=%s", self.config.stats_channel_id)
            return

        for chunk in self.stats.render_chunks():
            await channel.send(chunk, allowed_mentions=discord.AllowedMentions.none())
        if should_reset:
            self.stats.reset()

    def can_use_manager_commands(self, message: discord.Message) -> bool:
        permissions = getattr(message.author, "guild_permissions", None)
        return bool(permissions and permissions.manage_guild)

    async def handle_send_command(self, message: discord.Message) -> bool:
        parts = (message.content or "").strip().split(maxsplit=1)
        if not parts or parts[0] not in {"/send", "!send"}:
            return False

        if not self.can_use_manager_commands(message):
            await message.reply(
                "你沒有權限轉發訊息。",
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return True

        if len(parts) < 2 or not parts[1].strip():
            await message.reply(
                "用法：`/send 訊息內容` 或 `!send 訊息內容`，bot 會把訊息轉發到所有來源頻道。",
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return True

        sent_count = 0
        failed_count = 0
        outbound_content = parts[1].strip()

        for channel_id in sorted(self.config.source_channel_ids):
            channel = await self.fetch_sendable_channel(channel_id)
            if channel is None:
                failed_count += 1
                continue
            try:
                await channel.send(
                    outbound_content,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                sent_count += 1
            except discord.HTTPException:
                failed_count += 1
                logger.exception("Failed to forward /send message to channel %s", channel_id)

        result_text = f"已轉發到 {sent_count} 個來源頻道。"
        if failed_count:
            result_text += f"有 {failed_count} 個頻道無法送出。"
        await message.reply(
            result_text,
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return True

    async def handle_stats_command(self, message: discord.Message) -> bool:
        parts = (message.content or "").strip().split()
        if not parts or parts[0] != "!dcstats":
            return False

        if not self.can_use_manager_commands(message):
            await message.reply(
                "你沒有權限查看統計。",
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return True

        if len(parts) > 2:
            await self.reply_stats_usage(message)
            return True

        stats = self.stats
        if len(parts) == 2:
            try:
                hours = int(parts[1])
            except ValueError:
                await self.reply_stats_usage(message)
                return True
            if hours <= 0:
                await self.reply_stats_usage(message)
                return True
            stats = await self.build_history_stats(hours)

        chunks = stats.render_chunks()
        await message.reply(
            chunks[0],
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        for chunk in chunks[1:]:
            await message.channel.send(
                chunk,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        return True

    async def reply_stats_usage(self, message: discord.Message) -> None:
        await message.reply(
            "用法：`!dcstats` 查看目前累積統計，或 `!dcstats 小時數` 即時回抓指定小時數統計，例如 `!dcstats 6`。",
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    def is_moderation_bypassed(self, message: discord.Message) -> bool:
        if message.author.id in self.config.moderation_bypass_user_ids:
            return True

        permissions = getattr(message.author, "guild_permissions", None)
        if self.config.moderation_bypass_administrators and getattr(permissions, "administrator", False):
            return True

        role_ids = {getattr(role, "id", None) for role in getattr(message.author, "roles", [])}
        return bool(role_ids & self.config.moderation_bypass_role_ids)

    def meets_moderation_threshold(self, result: dict) -> bool:
        if not result.get("violates"):
            return False
        try:
            confidence = float(result.get("confidence", 0))
        except (TypeError, ValueError):
            return False
        return confidence >= self.config.moderation_min_confidence

    async def analyze_message(self, message: discord.Message) -> None:
        if not self.config.enable_ai_moderation or not self.analyzer.enabled:
            return
        if self.is_moderation_bypassed(message):
            return
        if len((message.content or "").strip()) < self.config.min_message_length_for_ai:
            return

        try:
            result = await self.analyzer.analyze(
                content=message.content,
                author_tag=str(message.author),
                channel_id=message.channel.id,
            )
        except Exception:
            logger.exception("AI moderation failed for message %s", message.id)
            return

        if result and self.meets_moderation_threshold(result):
            await self.notify_moderation(message, result)

    async def notify_moderation(self, message: discord.Message, result: dict) -> None:
        content = (message.content or "")[:1500].replace("```", "`\u200b``")
        confidence = round(float(result.get("confidence", 0)) * 100)
        lines = [
            "**疑似違規訊息**",
            f"使用者：{message.author} ({message.author.id})",
            f"頻道：<#{message.channel.id}>",
            f"嚴重度：{MODERATION_SEVERITY_LABELS.get(str(result.get('severity', 'none')), '無')}",
            f"信心：{confidence}%",
            f"規則：{result.get('rule') or '未指定'}",
            f"原因：{result.get('reason') or '未提供'}",
            f"訊息連結：{message.jump_url}",
            "",
            "```text",
            content,
            "```",
        ]

        if self.config.moderation_action in {"log", "both"}:
            log_channel = await self.fetch_sendable_channel(self.config.mod_log_channel_id)
            if log_channel is not None:
                await log_channel.send(
                    "\n".join(lines),
                    allowed_mentions=discord.AllowedMentions.none(),
                )

        if self.config.moderation_action in {"reply", "both"}:
            await message.reply(
                moderation_reply_text(self.config.direct_reply_text, result.get("rule")),
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )

        if self.config.delete_violating_messages:
            await self.try_delete_message(message)

    async def try_delete_message(self, message: discord.Message) -> None:
        try:
            await message.delete()
        except discord.HTTPException:
            logger.exception("Failed to delete message %s", message.id)
        except discord.Forbidden:
            logger.exception("Missing permission to delete message %s", message.id)


async def run_bot(config: Config) -> None:
    async with DiscordManagerBot(config) as client:
        await client.start(config.discord_token)


def run(config: Config) -> None:
    asyncio.run(run_bot(config))
