# 高校期刊 OA RSS 当期包

从期刊官网公开的 `/oa/rss.aspx` 读取当期（最新一期）文章。2026-11-22 对 Agent 2 聚类出的 39 本高校 CMS 期刊逐站探测，18 本返回可解析 RSS；其中《中医眼耳鼻喉杂志》RSS 停在 2012 年，作为源站停更未纳入，最终 17 本进入本包。随后对 1290 本 pending 广扫 `/oa/rss.aspx`，新增《机械与电子》1 本，最终 18 本。

## 来源标注

- 数据来自期刊官网公开 RSS，不是 OpenAlex/Crossref；
- 选刊标签：`采集:官网RSS` + `当期核验` + `目录:2377`；
- `journals.json` 记录 `catalog_source=2377_catalog`、`data_source=official_rss`、`source_group=oa_rss`、`official_url`、`rss_url`、`verification_mode=latest_issue_rss`、`rss_year`、`rss_month`、`probe_items`、`probe_first_title`；
- RSS 的 `channel/year`、`channel/month` 与每篇文章的 `issue`、`pubDate` 保留在探测记录中，正式运行时按 RSS 当期内容读取。

## 参数

- `journal_keys`：最多 100 本。
- `collect_mode`：`latest_issue`（默认，返回整期）或 `keywords`（仅对当期目次做本地关键词过滤；query 多词按 AND、aliases 按 OR，匹配标题/摘要/作者/DOI；**不是全刊检索**）。
- 平台请求的 `query` 仍需非空；`latest_issue` 模式不使用检索词。
- `per_journal_limit`：每刊上限，默认 50。
- `timeout_seconds`：单请求超时，默认 20。
- 平台请求的 `query` 仍需非空；`latest_issue` 模式不使用检索词。

RSS 中标题以“目录/封面/封底/征稿/启事/稿约”结尾的条目会被过滤，避免把整期目录当成文章。只读取公开 RSS，不下载全文、不绕过登录或验证码。历史探测不代表长期可用，正式运行前建议小批量复测。
