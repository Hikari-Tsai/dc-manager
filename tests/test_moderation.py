from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.moderation import ModerationAnalyzer


class ModerationAnalyzerTest(unittest.IsolatedAsyncioTestCase):
    async def test_analyze_requests_traditional_chinese_explanations(self) -> None:
        analyzer = ModerationAnalyzer(
            api_key="test-key",
            model="gpt-4.1-mini",
            rules_text="禁止人身攻擊",
        )
        analyzer.client = SimpleNamespace(
            responses=SimpleNamespace(
                create=AsyncMock(
                    return_value=SimpleNamespace(
                        output_text=(
                            '{"violates": false, "confidence": 0, "severity": "none", '
                            '"rule": "", "reason": ""}'
                        )
                    )
                )
            )
        )

        await analyzer.analyze(content="你好", author_tag="user#0001", channel_id=123)

        create_kwargs = analyzer.client.responses.create.await_args.kwargs
        system_content = create_kwargs["input"][0]["content"]
        self.assertIn("Traditional Chinese", system_content)
        self.assertIn("繁體中文", system_content)
        self.assertIn("rule", system_content)
        self.assertIn("reason", system_content)


if __name__ == "__main__":
    unittest.main()
