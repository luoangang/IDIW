# 北大方正期刊当期包

从北大方正 `rc-pub` 官网公开接口读取当期文章：`site/findBySld → 详情 → getFirstTwoPeriods → getArticlesByPeriodicalId`。

2026-11-21 对 2377 目录中真正落在 `*.publish.founderss.cn`/`*.portal.founderss.cn`/`*.hssonline.cn` 的 25 本做了探测，20 本成功、5 本失败；其余 132 本北大方正候选是各校独立 CMS，不适用本包，继续留在补充包 pending。

## 来源标注

- 数据来自期刊官网的方正 rc-pub 接口，不是 OpenAlex/Crossref；
- 选刊标签：`采集:官网API` + `当期核验` + `目录:2377`；
- `journals.json` 保留 `base_url`、`site_id`、`publication_index_id`、`source_group`、`official_url`、`data_source=official_api`、`verification_mode=latest_issue`、`probe_items` 等来源字段。

## 参数

- `journal_keys`：最多 100 本。
- `collect_mode`：`latest_issue`（默认，返回整期）或 `keywords`（仅对当期目次做本地关键词过滤；query 多词按 AND、aliases 按 OR，匹配标题/摘要/作者/DOI；**不是全刊检索**）。
- 平台请求的 `query` 仍需非空；`latest_issue` 模式不使用检索词。
- `per_journal_limit`：每刊上限，默认 50。
- `timeout_seconds`：单请求超时，默认 20。
- 平台 `query` 仍需非空；`latest_issue` 模式不使用检索词。

只读取公开当期列表，不下载全文、不绕过登录或验证码。历史探测不代表长期可用，正式运行前建议小批量复测。
