# 勤云中文期刊检索包

一个包、一张结果表；`journals.json` 仅包含 2026-10-26 逐刊实测通过的 104 家期刊，其中包括《软件学报》（`jos`）。其余候选及每刊测试结论保存在 `journal_catalog/supplier-journal-audit-2026-10-26.csv`。同时支持新版 AJAX 与旧版 ASP.NET 检索；默认仅选择 `jos`。

参数：`journal_keys` 是目录中的期刊键数组（最多 30 个）；`per_journal_limit` 是每刊最多返回数，整次运行仍受平台 `request.limit` 总上限约束，达到总上限后不再查询后续期刊；`timeout_seconds` 是单请求超时。输入查询词由平台 `request.query` 提供。字段包括期刊名、标题、链接、作者、摘要、DOI、年份；详情与全文不自动下载。条目以 `journal_key + external_id` 去重。

本包使用标准库和站点公开搜索接口，不需要账户。站点证书照常验证，不绕过登录或防护；某刊网络不可达时，该刊记录为告警，已成功的其他期刊可保留。
