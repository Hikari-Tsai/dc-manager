from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI


RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "violates": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "severity": {"type": "string", "enum": ["none", "low", "medium", "high"]},
        "rule": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["violates", "confidence", "severity", "rule", "reason"],
}


class ModerationAnalyzer:
    def __init__(self, api_key: str, model: str, rules_text: str) -> None:
        self.enabled = bool(api_key)
        self.model = model
        self.rules_text = rules_text
        self.client = AsyncOpenAI(api_key=api_key) if self.enabled else None

    async def analyze(self, content: str, author_tag: str, channel_id: int) -> dict[str, Any] | None:
        if self.client is None:
            return None

        response = await self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are a Discord community moderation assistant. "
                        "Judge only the supplied message against the supplied server rules. "
                        "Write the rule and reason fields in Traditional Chinese (繁體中文). "
                        "Return JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": "\n\n".join(
                        [
                            f"Server rules:\n{self.rules_text}",
                            f"Author: {author_tag}",
                            f"Channel ID: {channel_id}",
                            f"Message:\n{content}",
                        ]
                    ),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "discord_moderation_result",
                    "schema": RESULT_SCHEMA,
                    "strict": True,
                }
            },
        )

        output = response.output_text
        if not output:
            return None
        return json.loads(output)
