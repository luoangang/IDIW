# PaperOnce 期刊当期包

从 PaperOnce 期刊官网公开 API `api/api/Web/LastIssueList` 读取当期文章。69 本为 2026-11-21 从 2377 目录逐刊探测、当期返回至少 1 篇文章的期刊；其余 6 本因 HTTP 500/417/TLS/404 或当期空页未纳入。

## 来源标注

- 数据来自期刊官网的 PaperOnce 接口，不是 OpenAlex/Crossref；
- 选刊标签：`采集:官网API` + `当期核验` + `目录:2377`；
- `journals.json` 同时记录 `catalog_source=2377_catalog`、`data_source=official_api`、`source_group=paperonce`、`official_url`、`verification_mode=latest_issue`、`probe_items`、`probe_first_title`。

## 参数

- `journal_keys`：最多 100 本。
- `collect_mode`：`latest_issue`（默认，返回整期）或 `keywords`（仅对当期目次做本地关键词过滤；query 多词按 AND、aliases 按 OR，匹配标题/摘要/作者/DOI；**不是全刊检索**）。
- 平台请求的 `query` 仍需非空；`latest_issue` 模式不使用检索词。
- `per_journal_limit`：每刊上限，默认 50。
- `enrich_abstract`：默认 `true`，`latest_issue` 模式下对**摘要为空**的文章抓详情页摘要；优先 `span#LbZY`，兜底行内 `摘要：`/`Abstract:`（可能为英文，同样可用）。仅填空、不覆盖已有摘要。
- `abstract_enrich_limit`：每刊最多补抓条数，默认 5，范围 0–10（0 关闭）。
- 详情请求间隔 2 秒；单次 502 等待约 4 秒重试一次；单篇失败/无摘要只写非致命 warning，不影响整刊；仅保存文本，不下载 PDF，不登录、不绕验证码。旧版模板 URL 可能含双斜杠 `//oa/`，按原样访问。
- `timeout_seconds`：单请求超时，默认 20。
- 平台请求的 `query` 仍需非空；`latest_issue` 模式不使用检索词。

只读取公开当期列表，不下载全文、不绕过登录或验证码。历史探测不代表长期可用，正式运行前建议小批量复测。
