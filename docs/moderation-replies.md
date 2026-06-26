# AI 版規回覆訊息

當 `MODERATION_ACTION` 設為 `reply` 或 `both` 時，bot 會直接回覆疑似違規的觀眾訊息。

回覆內容會先使用 `.env` 的 `DIRECT_REPLY_TEXT`。如果 AI 判斷結果有指出違反的版規，bot 也會在下一行補上：

```text
可能違反版規：禁止人身攻擊
```

建議 `DIRECT_REPLY_TEXT` 使用簡短、具體且不帶羞辱性的繁體中文，例如：

```dotenv
DIRECT_REPLY_TEXT=你的訊息可能違反版規，請調整語氣或內容。
```
