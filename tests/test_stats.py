from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from src.stats import MessageStats


class MessageStatsTest(unittest.TestCase):
    def test_reset_can_use_supplied_start_time(self) -> None:
        started_at = datetime(2026, 6, 22, 1, 0, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        stats = MessageStats()

        stats.reset(started_at=started_at)

        self.assertEqual(stats.started_at, started_at)

    def test_render_lists_keyword_mentions_with_author_and_content(self) -> None:
        stats = MessageStats(keywords=["早安", "晚安"])
        stats.record(
            SimpleNamespace(
                content="早安，今天也請多指教",
                author=SimpleNamespace(id=123),
                channel=SimpleNamespace(id=456),
            )
        )

        report = stats.render()

        self.assertIn("關鍵字命中：早安 1", report)
        self.assertIn("**關鍵字留言明細**", report)
        self.assertIn("- 早安｜<@123>：早安，今天也請多指教", report)

    def test_render_chunks_splits_long_reports(self) -> None:
        stats = MessageStats(keywords=["早安"])
        for index in range(8):
            stats.record(
                SimpleNamespace(
                    content=f"早安，這是第 {index} 則很長的留言內容" + "x" * 120,
                    author=SimpleNamespace(id=index + 1),
                    channel=SimpleNamespace(id=456),
                )
            )

        chunks = stats.render_chunks(max_length=500)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 500 for chunk in chunks))
        self.assertIn("**頻道統計摘要**", chunks[0])


if __name__ == "__main__":
    unittest.main()
