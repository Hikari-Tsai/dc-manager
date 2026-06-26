# Contributing

感謝你願意協助改善 dc-manager。這個專案目前以小範圍、可驗證的改動為主，方便快速檢查 Discord bot 的行為是否符合預期。

## 開發流程

1. 從 `main` 建立新的分支。
2. 針對一個明確問題或功能進行修改。
3. 若改動會影響程式行為，請同步新增或更新測試。
4. 送出 pull request 前，先執行完整測試：

```bash
python3 -m unittest discover -s tests
```

## Pull Request 建議

PR 描述建議包含：

- 修改摘要
- 測試方式
- 任何需要部署或設定調整的注意事項

請避免在同一個 PR 混入無關的重構、格式化或設定變更。
