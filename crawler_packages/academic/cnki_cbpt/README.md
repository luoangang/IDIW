# CBPT 期刊门户采集包

按关键词检索，或读取当期目次，逐刊获取目录内 `*.cbpt.cnki.net` 站点（部分期刊的 WKH3 当期页位于其 `*.chinajournal.net.cn` 公开别名）的标题、作者、摘要、期次和文章链接。使用网站公开搜索接口与当期目次页，不下载全文。

`journals.json` 仅列出逐刊实测取得文章且通过字段校验的 826 家期刊；原工作簿中的其他候选和失败记录保留在审计目录，不在平台选择器中显示。`journal_keys` 为需要采集的期刊键数组，默认选择三家已完成实测的站点。建议每批不超过 30 家，并分别监测失败告警。历史验收不保证站点长期可用。

参数：`journal_keys`、`collect_mode`、`per_journal_limit`、`max_pages_per_journal`、`timeout_seconds`。`collect_mode` 默认 `keywords`；设为 `latest_issue` 时读取 `portal/journal/portal/client/paper_list/type_benqi` 当期目次并跟随分页，忽略检索词，适合监测最新一期。平台请求的 `limit` 是整包上限，会尽量平均分给所选期刊；`per_journal_limit` 是每家期刊上限。运行结束时可查看 `warnings` 了解部分站点失败情况。2026-11-21 抽查中，哈尔滨体育学院学报可由当期目次取得 14 条；潮学研究仍返回 HTTP 500，属于站点故障，需跳过。

当期翻页（`latest_issue`）：

- 仅跟随首屏 HTML 中带 `href` 的 `paperPage_list?pageNum=N` 链接，按页码升序抓取；每页 10 条，按文章 URL 去重合并。
- `max_pages_per_journal`（整数，1–40，默认 20）是每刊总页数上限（含首页），实际页数取它与分页控件最大页码的较小者，不再有硬编码的 19 页魔法数。
- 第 2 页起校验分页 URL 中的 `yearId`、`issueId` 是否与首屏分页链接一致；不一致立即停止翻页并写入 warning，避免混入过刊。若分页链接本身不带这两个参数，则跳过该校验。
- 若首屏出现 `paperPage_list` 文本或按钮但没有 `href` 分页链接，写入 warning 提示可能为 JS 分页，只采首屏，不猜测接口。
- `WebPublication` 期刊仍按单页解析（含可选摘要补取）；页面若出现 `paperPage_list` 控件会写入单页告警，不做翻页。
- 部分 WKH3 站点的 `paperDigest.aspx` 摘要页可能 302 到 `showValidateCode.aspx` 验证码页（如兰州大学学报（社会科学版））。此时只保留题录与文章链接，摘要留空并写入 warning，不尝试绕过验证码。
