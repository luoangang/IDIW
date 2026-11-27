# 勤云中文期刊检索包

一个包、一张结果表；`journals.json` 当前 **171** 家期刊（包版本 1.9.3），包含 2026-10-26 逐刊实测批次及后续核心刊补录（如《地质与勘探》《体育学研究》）。其余候选及每刊测试结论保存在 `journal_catalog/supplier-journal-audit-2026-10-26.csv`。同时支持新版 AJAX 与旧版 ASP.NET 检索；默认包含 `jos`、2026-11-24 新增的地质与勘探及后续核心刊补录。

参数：`journal_keys` 是目录中的期刊键数组（最多 174 个）；`collect_mode` 可选 `keywords`（默认）或 `latest_issue`（读取当期目次；`current_url` 为 JS 跳转页或勤云 `issue/browser` 过刊浏览页时都会自动解析并跟随最新期，并过滤封面/目录条目）；`per_journal_limit` 是每刊最多返回数，整次运行仍受平台 `request.limit` 总上限约束，达到总上限后不再查询后续期刊；`timeout_seconds` 是单请求超时。输入查询词由平台 `request.query` 提供。字段包括期刊名、标题、链接、作者、摘要、DOI、年份；详情与全文不自动下载。条目以 `journal_key + external_id` 去重。

`latest_issue` 的 `current_url` 优先使用期刊的稳定入口：勤云 `issue/browser` 页内嵌的 `strAllIssueJson` 会自动解析出最新年/期并转到 `/article/issue/{年}_{期}`，因此新期上线后通常无需改目录；只有站点未提供稳定入口时才写当前期直链，并需要按新期更新 `current_url`。

`latest_issue` 默认只请求一页。仅当当期页出现指向**同一期**的分页链接（`?page=N`、`.../article/issue/{年}_{期}/N`，或旧版 ASP 的 `PageCount` 加页码链接）时才顺序补页：最多 20 页，0 新增、期次标记变化、重复页或请求失败即停止，链接跨期/跨路径一律忽略。解析后会核对页面 `FileNO` 数量，只有真实文章未解析才写入告警；封面/封底/目录等噪声过滤不计为丢条。摘要补采（`enrich_abstract`/`abstract_enrich_limit`）行为保持不变，只填空、不覆盖已有摘要。

本包使用标准库和站点公开搜索接口，不需要账户。站点证书照常验证，不绕过登录或防护；某刊网络不可达时，该刊记录为告警，已成功的其他期刊可保留。
