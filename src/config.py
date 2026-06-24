from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv


load_dotenv()


ModerationAction = Literal["log", "reply", "both", "none"]


def parse_list(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.lower() in {"1", "true", "yes", "y", "on"}


def parse_int(value: str | None, default: int) -> int:
    try:
        return int(value or "")
    except ValueError:
        return default


def parse_non_negative_int(value: str | None, default: int) -> int:
    parsed = parse_int(value, default)
    return parsed if parsed >= 0 else default


def parse_probability(value: str | None, default: float) -> float:
    try:
        parsed = float(value or "")
    except ValueError:
        return default
    return parsed if 0 <= parsed <= 1 else default


@dataclass(frozen=True)
class Config:
    discord_token: str
    source_channel_ids: set[int]
    stats_channel_id: int | None
    mod_log_channel_id: int | None

    openai_api_key: str
    openai_model: str

    stats_interval_cron: str
    stats_backfill_hours: int
    stats_reset_after_report: bool
    keywords: list[str]
    top_word_limit: int

    enable_ai_moderation: bool
    moderation_action: ModerationAction
    direct_reply_text: str
    delete_violating_messages: bool
    min_message_length_for_ai: int
    moderation_min_confidence: float
    moderation_bypass_user_ids: set[int]
    moderation_bypass_role_ids: set[int]
    moderation_bypass_administrators: bool
    rules_text: str
    rules_file_path: str | None
    rules_file_error: str | None


def parse_channel_id(value: str | None) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_channel_id_set(value: str | None) -> set[int]:
    ids: set[int] = set()
    for item in parse_list(value):
        try:
            ids.add(int(item))
        except ValueError:
            continue
    return ids


def parse_int_set(value: str | None) -> set[int]:
    ids: set[int] = set()
    for item in parse_list(value):
        try:
            ids.add(int(item))
        except ValueError:
            continue
    return ids


def load_rules_text() -> tuple[str, str | None, str | None]:
    rules_file = (os.getenv("RULES_FILE") or "").strip()
    default_rules = "禁止人身攻擊、歧視、騷擾、洗頻、惡意連結、NSFW 內容與洩漏個資。"

    if not rules_file:
        return os.getenv("RULES_TEXT", default_rules), None, None

    try:
        rules_text = Path(rules_file).expanduser().read_text(encoding="utf-8").strip()
    except OSError:
        return "", rules_file, f"RULES_FILE cannot be read: {rules_file}"

    if not rules_text:
        return "", rules_file, f"RULES_FILE is empty: {rules_file}"

    return rules_text, rules_file, None


def load_config() -> Config:
    action = os.getenv("MODERATION_ACTION", "log")
    if action not in {"log", "reply", "both", "none"}:
        action = "log"

    rules_text, rules_file_path, rules_file_error = load_rules_text()

    return Config(
        discord_token=os.getenv("DISCORD_TOKEN", ""),
        source_channel_ids=parse_channel_id_set(os.getenv("SOURCE_CHANNEL_IDS")),
        stats_channel_id=parse_channel_id(os.getenv("STATS_CHANNEL_ID")),
        mod_log_channel_id=parse_channel_id(os.getenv("MOD_LOG_CHANNEL_ID")),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        stats_interval_cron=os.getenv("STATS_INTERVAL_CRON", "0 0 * * *"),
        stats_backfill_hours=parse_non_negative_int(os.getenv("STATS_BACKFILL_HOURS"), 6),
        stats_reset_after_report=parse_bool(os.getenv("STATS_RESET_AFTER_REPORT"), True),
        keywords=[keyword.lower() for keyword in parse_list(os.getenv("KEYWORDS"))],
        top_word_limit=parse_int(os.getenv("TOP_WORD_LIMIT"), 10),
        enable_ai_moderation=parse_bool(os.getenv("ENABLE_AI_MODERATION"), True),
        moderation_action=action,  # type: ignore[assignment]
        direct_reply_text=os.getenv(
            "DIRECT_REPLY_TEXT",
            "你的訊息可能違反版規，請調整語氣或內容。",
        ),
        delete_violating_messages=parse_bool(os.getenv("DELETE_VIOLATING_MESSAGES"), False),
        min_message_length_for_ai=parse_int(os.getenv("MIN_MESSAGE_LENGTH_FOR_AI"), 3),
        moderation_min_confidence=parse_probability(os.getenv("MODERATION_MIN_CONFIDENCE"), 0.75),
        moderation_bypass_user_ids=parse_int_set(os.getenv("MODERATION_BYPASS_USER_IDS")),
        moderation_bypass_role_ids=parse_int_set(os.getenv("MODERATION_BYPASS_ROLE_IDS")),
        moderation_bypass_administrators=parse_bool(
            os.getenv("MODERATION_BYPASS_ADMINISTRATORS"),
            True,
        ),
        rules_text=rules_text,
        rules_file_path=rules_file_path,
        rules_file_error=rules_file_error,
    )


def validate_config(config: Config) -> list[str]:
    errors: list[str] = []

    if not config.discord_token:
        errors.append("DISCORD_TOKEN is required.")
    if not config.source_channel_ids:
        errors.append("SOURCE_CHANNEL_IDS is required.")
    if config.stats_channel_id is None:
        errors.append("STATS_CHANNEL_ID is required.")
    if (
        config.enable_ai_moderation
        and config.moderation_action in {"log", "both"}
        and config.mod_log_channel_id is None
    ):
        errors.append("MOD_LOG_CHANNEL_ID is required when MODERATION_ACTION is log or both.")
    if config.rules_file_error:
        errors.append(config.rules_file_error)

    return errors
