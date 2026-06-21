from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import discord


WORD_PATTERN = re.compile(r"[\w#@-]{2,}", re.UNICODE)
TAIPEI = ZoneInfo("Asia/Taipei")
MAX_KEYWORD_CONTENT_LENGTH = 500


@dataclass(frozen=True)
class KeywordMention:
    keyword: str
    author_id: int
    content: str


class MessageStats:
    def __init__(self, keywords: list[str] | None = None, top_word_limit: int = 10) -> None:
        self.keywords = keywords or []
        self.top_word_limit = top_word_limit
        self.reset()

    def reset(self, started_at: datetime | None = None) -> None:
        self.started_at = started_at or datetime.now(TAIPEI)
        self.message_count = 0
        self.user_counts: Counter[int] = Counter()
        self.channel_counts: Counter[int] = Counter()
        self.keyword_counts: Counter[str] = Counter({keyword: 0 for keyword in self.keywords})
        self.keyword_mentions: list[KeywordMention] = []
        self.word_counts: Counter[str] = Counter()

    def record(self, message: discord.Message) -> None:
        content = message.content or ""
        normalized = content.lower()

        self.message_count += 1
        self.user_counts[message.author.id] += 1
        self.channel_counts[message.channel.id] += 1

        for keyword in self.keywords:
            if keyword in normalized:
                self.keyword_counts[keyword] += 1
                self.keyword_mentions.append(
                    KeywordMention(
                        keyword=keyword,
                        author_id=message.author.id,
                        content=self.clean_content(content),
                    )
                )

        for match in WORD_PATTERN.finditer(normalized):
            word = match.group(0)
            if len(word) < 2 or word.startswith("http"):
                continue
            self.word_counts[word] += 1

    def clean_content(self, content: str) -> str:
        cleaned = " ".join(content.split())
        if len(cleaned) <= MAX_KEYWORD_CONTENT_LENGTH:
            return cleaned
        return cleaned[:MAX_KEYWORD_CONTENT_LENGTH].rstrip() + "..."

    def render_lines(self) -> list[str]:
        now = datetime.now(TAIPEI)
        active_minutes = max(1, round((now - self.started_at).total_seconds() / 60))
        top_users = " / ".join(
            f"<@{user_id}> {count}" for user_id, count in self.user_counts.most_common(5)
        )
        top_words = " / ".join(
            f"{word} {count}" for word, count in self.word_counts.most_common(self.top_word_limit)
        )
        keyword_hits = " / ".join(
            f"{keyword} {count}"
            for keyword, count in self.keyword_counts.most_common()
            if count > 0
        )

        lines = [
            "**頻道統計摘要**",
            f"期間：{self.started_at.strftime('%Y-%m-%d %H:%M:%S')} 起，約 {active_minutes} 分鐘",
            f"訊息數：{self.message_count}",
            f"發言人數：{len(self.user_counts)}",
            f"熱門發言者：{top_users or '無'}",
            f"關鍵字命中：{keyword_hits or '無'}",
            f"熱門字詞：{top_words or '無'}",
        ]

        if self.keyword_mentions:
            lines.extend(["", "**關鍵字留言明細**"])
            lines.extend(
                f"- {mention.keyword}｜<@{mention.author_id}>：{mention.content}"
                for mention in self.keyword_mentions
            )

        return lines

    def render(self) -> str:
        return "\n".join(self.render_lines())

    def render_chunks(self, max_length: int = 1900) -> list[str]:
        chunks: list[str] = []
        current_lines: list[str] = []
        current_length = 0

        for line in self.render_lines():
            line_length = len(line) + (1 if current_lines else 0)
            if current_lines and current_length + line_length > max_length:
                chunks.append("\n".join(current_lines))
                current_lines = []
                current_length = 0

            current_lines.append(line)
            current_length += len(line) + (1 if current_length else 0)

        if current_lines:
            chunks.append("\n".join(current_lines))

        return chunks
