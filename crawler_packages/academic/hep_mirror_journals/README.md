# HEP 公开镜像期刊包

读取中国高校科技期刊集群 `cjournal.hep.com.cn` 的公开当期目录。它**不是期刊官网**，是公开镜像；官网本身超时、412/WAF 时才使用。

2026-11-22 由 qinyun 剩余批探测，3 本 2377 目录期刊在 HEP 镜像有当期文章：郑州大学学报（工学版）、重庆医科大学学报、重庆邮电大学学报（社会科学版）。

## 来源标注

- 选刊标签：`采集:公开镜像` + `非官网` + `当期核验` + `目录:2377`；
- `journals.json` 记录 `data_source=public_mirror`、`official_url`、`current_url`、`probe_items`、`probe_first_title`；
- 文章标题和文章链接来自 HEP 当期目录，不下载全文，不绕过登录/验证码。

## 参数

- `journal_keys`：默认全部 3 本。
- `collect_mode`：`latest_issue`（默认，返回整期）或 `keywords`（仅对当期目次做本地关键词过滤；query 多词按 AND、aliases 按 OR，匹配标题/摘要/作者/DOI；**不是全刊检索**）。
- 平台请求的 `query` 仍需非空；`latest_issue` 模式不使用检索词。
- `per_journal_limit`：默认 50；`timeout_seconds`：默认 20。
- `enrich_abstract`：默认 `true`，`latest_issue` 模式下对**摘要为空**的文章抓详情页摘要；`meta[name=citation_abstract]` 优先，`description`/`og:description`/`twitter:description`/JSON-LD `abstract` 兜底，仅接受长度 >100 的文本。
- `abstract_enrich_limit`：每刊最多补抓条数，默认 4，范围 0–10（0 关闭）。
- 补采只填空、不覆盖列表已有摘要；详情请求间隔约 1.2 秒；单篇失败/无摘要只写非致命 warning，不影响整刊；仅保存文本，不下载 PDF，不登录、不绕验证码。
- 平台请求的 `query` 仍需非空；`latest_issue` 模式不使用检索词。
