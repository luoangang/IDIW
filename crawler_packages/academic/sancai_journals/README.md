# 西安三才中文期刊检索包

一个包、一张结果表；`journals.json` 当前只包含逐刊实测通过正向与无关词检索的《合肥师范学院学报》。另一家《安徽师范大学学报（社会科学版）》正向检索与三条记录复测通过，但无关词复测遇到 HTTP 502，暂不列入可用目录；《机械与电子》旧站未能按词获取文章。三家的逐刊结论均保存在 `journal_catalog/supplier-journal-audit-2026-10-26.csv`。

参数：`journal_keys` 最多 3 家，`per_journal_limit` 控制每刊数量；整次运行还受平台 `request.limit` 总上限约束，达到总上限后不再查询后续期刊。`timeout_seconds` 控制单请求超时。查询词来自 `request.query`，目前按标题检索。条目包含文章详情 URL、标题、作者、摘要、DOI、年份，按 `journal_key + external_id` 去重。不下载全文，不需要账户。
