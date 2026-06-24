# Discord 頻道統計與 AI 版規偵測 Bot

這是一個 Python Discord bot，可以：

- 監聽指定頻道的聊天訊息
- 統計訊息數、發言人數、關鍵字命中、熱門字詞
- 定時把統計摘要發到另一個頻道
- 使用 OpenAI 做語意版規判斷
- 依 `.env` 設定，將違規結果回覆給觀眾、送到私密頻道、兩者都做或都不做

## 安裝

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 設定

直接編輯目前資料夾的 `.env`：

```dotenv
DISCORD_TOKEN=你的 Discord bot token
SOURCE_CHANNEL_IDS=來源頻道ID
STATS_CHANNEL_ID=統計要發送的頻道ID
MOD_LOG_CHANNEL_ID=私密審核頻道ID
OPENAI_API_KEY=你的 OpenAI API key
RULES_FILE=rules.txt
STATS_BACKFILL_HOURS=6
MODERATION_MIN_CONFIDENCE=0.75
MODERATION_BYPASS_USER_IDS=管理員使用者ID
MODERATION_BYPASS_ROLE_IDS=管理員角色ID
MODERATION_BYPASS_ADMINISTRATORS=true
```

多個來源頻道用逗號分隔：

```dotenv
SOURCE_CHANNEL_IDS=111111111111111111,222222222222222222
```

`MODERATION_ACTION` 可用：

- `log`：只送到私密頻道
- `reply`：直接回覆觀眾
- `both`：私密頻道與直接回覆都做
- `none`：只分析但不通知

## 統計回抓設定

bot 啟動時會先往回抓 `SOURCE_CHANNEL_IDS` 裡每個頻道最近一段時間的歷史訊息，建立初始統計：

```dotenv
STATS_BACKFILL_HOURS=6
```

預設是回抓 6 小時。設為 `0` 可以停用啟動回抓，只統計 bot 啟動後的新訊息。歷史回抓只會更新統計，不會對舊訊息執行 AI 審核或發違規通知。

定期統計報告預設每日 00:00 發送一次，可用 cron 格式調整：

```dotenv
STATS_INTERVAL_CRON="0 0 * * *"
```

## 統計報告說明

統計報告會顯示以下欄位：

- `期間`：這份報告涵蓋的統計開始時間與累積分鐘數。啟動回抓有開啟時，開始時間會是回抓起點；定期報告送出後若 `STATS_RESET_AFTER_REPORT=true`，下一期會重新計算。
- `訊息數`：統計期間內，來源頻道收到的使用者訊息總數。bot 自己的訊息不會計入。
- `發言人數`：統計期間內有發言的不重複使用者數。
- `熱門發言者`：發言數最多的前 5 位使用者與各自訊息數。
- `關鍵字命中`：`.env` 的 `KEYWORDS` 中，每個有被命中的關鍵字與命中次數。
- `熱門字詞`：從訊息內容切出的常見字詞，最多顯示 `TOP_WORD_LIMIT` 個。
- `關鍵字留言明細`：每一則命中關鍵字的留言都會列出 `關鍵字｜發言者：留言內容`。

範例：

```text
**頻道統計摘要**
期間：2026-06-22 00:00:00 起，約 360 分鐘
訊息數：12
發言人數：3
熱門發言者：<@123> 5 / <@456> 4
關鍵字命中：早安 2 / 晚安 1
熱門字詞：早安 2 / 大家 2

**關鍵字留言明細**
- 早安｜<@123>：早安，今天也請多指教
- 晚安｜<@456>：大家晚安
```

如果關鍵字明細太長，bot 會自動拆成多則 Discord 訊息送出。單則留言內容會整理換行，並保留前 500 字避免超過 Discord 訊息長度限制。

## AI 版規設定

AI 審核會優先讀取 `.env` 的 `RULES_FILE`：

```dotenv
RULES_FILE=rules.txt
```

把完整版規寫在 `rules.txt`，啟動時會送給 AI 作為判斷依據。這是嚴格模式：只要設定了 `RULES_FILE`，但檔案不存在、讀不到或內容是空的，bot 會啟動失敗並顯示設定錯誤。

AI 審核只有在 AI 回傳 `violates=true`，而且 `confidence` 達到 `MODERATION_MIN_CONFIDENCE` 時才會觸發通知、回覆或刪除。預設值是 `0.75`，如果覺得太敏感可以調高，例如 `0.85`；如果漏判太多可以調低，例如 `0.65`。

```dotenv
MODERATION_MIN_CONFIDENCE=0.75
```

AI 審核會在送出 OpenAI 前檢查 bypass 名單；命中的訊息仍會被統計，但不會進行 AI 版規判斷，也不會回覆、記錄或刪除。

```dotenv
MODERATION_BYPASS_USER_IDS=111111111111111111,222222222222222222
MODERATION_BYPASS_ROLE_IDS=333333333333333333
MODERATION_BYPASS_ADMINISTRATORS=true
```

- `MODERATION_BYPASS_USER_IDS`：指定使用者 ID 名單。
- `MODERATION_BYPASS_ROLE_IDS`：指定角色 ID 名單，例如管理員角色。
- `MODERATION_BYPASS_ADMINISTRATORS`：預設 `true`，自動 bypass 具備 Discord Administrator 權限的使用者；設為 `false` 可關閉。

如果不想使用 txt 檔，移除或留空 `RULES_FILE`，程式才會改用 `.env` 的 `RULES_TEXT`：

```dotenv
RULES_TEXT=禁止人身攻擊、歧視、騷擾、洗頻、惡意連結、NSFW 內容與洩漏個資。
```

## Discord 權限

Discord Developer Portal 的 Bot 設定需要開啟 `Message Content Intent`，否則 bot 收不到一般訊息內容。Bot 邀請到伺服器時至少需要：

- View Channels
- Send Messages
- Read Message History
- Manage Messages：只有在 `DELETE_VIOLATING_MESSAGES=true` 時需要

## 啟動

```bash
source .venv/bin/activate
python3 -m src.main
```

## 手動查看統計

在被監聽頻道或 `MOD_LOG_CHANNEL_ID` 管理頻道輸入：

```text
!dcstats
```

查看目前已累積的統計。

也可以附帶小時數，讓 bot 即時往回抓指定時間範圍並產生一份臨時報告：

```text
!dcstats 6
```

這會統計最近 6 小時的來源頻道訊息。這份臨時報告不會覆蓋目前定期統計累積資料，也不會對歷史訊息執行 AI 審核或發違規通知。

需要使用者有 `Manage Server` 權限。
