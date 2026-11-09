# 仁和汇智中文期刊检索包

一个包、一张结果表；`journals.json` 仅包含 2026-10-26 逐刊实测可返回记录且按词过滤的 122 家期刊。支持 JSON `searchResult`、HTML 检索页和 `search-data` 变体。默认《工程科学学报》（`b11e9e7fdb08aa16`）；该站首轮与无关词测试通过，三条记录复测曾有一次超时。其余候选及每刊结论保存在 `journal_catalog/supplier-journal-audit-2026-10-26.csv`。

参数：`journal_keys` 最多 30 家，`per_journal_limit` 控制每刊数量；整次运行还受平台 `request.limit` 总上限约束，达到总上限后不再查询后续期刊。`timeout_seconds` 控制单请求超时。查询词来自 `request.query`。结果表存标题、详情 URL、作者、摘要、DOI、年份及期刊身份，按 `journal_key + external_id` 去重。不下载全文，不关闭 TLS 校验。
