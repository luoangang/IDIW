# 西安三才中文期刊检索包

一个包、一张结果表；`journals.json` 当前包含 2 家：《合肥师范学院学报》（按词验证）和《安徽师范大学学报（社会科学版）》（2026-11-21 当期目次验证补入，按词模式仍未验收）。《机械与电子》旧站未能按词获取文章。三家的逐刊结论均保存在 `journal_catalog/supplier-journal-audit-2026-10-26.csv`。

参数：`journal_keys` 最多 3 家，`collect_mode` 可选 `keywords`（默认）或 `latest_issue`（读取 `api/api/Web/LastIssueList` 当期文章列表），`per_journal_limit` 控制每刊数量；整次运行还受平台 `request.limit` 总上限约束，达到总上限后不再查询后续期刊。`timeout_seconds` 控制单请求超时。查询词来自 `request.query`，`latest_issue` 模式忽略查询词。条目包含文章详情 URL、标题、作者、摘要、DOI、年份，按 `journal_key + external_id` 去重。不下载全文，不需要账户。
