# 国外 Q1 期刊包

基于 JCR 2025 Q1 全学科 watchlist，通过 OpenAlex / Crossref 公开 API 采集**文章元数据与链接**的研究用采集包。只保存题录、摘要文本和 DOI/URL，**不下载 PDF**。

## 数据范围

- 来源：`journal_catalog/foreign/foreign_journals_q1_2026-11-25.csv`
- 只取 `include_daily=yes` 的 **5,238 本**；排除 `include_daily=no` 的 41 本 Inactive 期刊。
- 按 `journal_id` 去重，作为本包的 `journal_key`。
- 覆盖 SCIE、SSCI、ESCI、AHCI 与少量 edition 缺失（`?`）的 Q1 期刊，学科为全学科。
- watchlist 未提供 `official_url`，因此 `journals.json` 的 `url` 统一为空字符串；文章链接使用 DOI 解析地址。
- 出版周期取自 `journal_catalog/source/periodicals_2026-11-25/JCR爬虫/JCR_最终版/*.json` 中 `quartile=Q1` 的记录（按 ISSN/eISSN 规范化匹配，必要时回退刊名），5,279 行全部匹配成功。

## 数据源与身份

- 主源：OpenAlex Works API（`https://api.openalex.org/works`）。
- 兜底：OpenAlex 请求失败（429/5xx/超时/网络错误/响应过大）时，改用 Crossref Works API（`https://api.crossref.org/works`）。同一轮任务内一旦触发兜底，后续期刊也优先走 Crossref。此外，某刊 OpenAlex 在所有候选 ISSN 上均返回空列表（HTTP 200、0 条），或返回的记录全被过滤（无 DOI、无标题、编辑类/更正标题）时，也会用 Crossref 重新查该刊（按 ISSN 依次尝试），交叉记录以 `source_api=crossref` 返回；OpenAlex 有可用记录时不重复请求 Crossref。成功的空结果回退不产生额外 warning。以上兜底仅适用于 `keywords` / `latest_issue` 逐刊模式；`bulk_window`（v1）只查 OpenAlex，不返回 Crossref。
- 身份字段：`identity_fields=["doi"]`。DOI 统一小写并去掉 `https://doi.org/` 前缀；同一 DOI 在单次结果内只保留一条。
- 摘要：OpenAlex 使用 `abstract_inverted_index` 倒排索引还原；Crossref 使用 `abstract` 字段并清理 JATS 标签。
- 只采公开元数据，不登录、不绕 WAF、不设置全局代理/TUN；`url` 指向 DOI 或 Crossref 给出的落地页，不抓取出版商 PDF。

## 出版周期字段

watchlist 与 `journals.json` 均新增三列/字段（插在 `edition` 之后）：

| 字段 | 说明 |
| --- | --- |
| `publication_frequency` | JCR 原始值，如 `4 issues/year`；JCR 未提供时为空 |
| `issues_per_year` | 每年期数（整数）；无法解析 `N issues/year` 时为空 |
| `frequency_class` | 频次等级，见下表 |

| 等级 | 每年期数 |
| --- | --- |
| `weekly` | ≥ 40 |
| `semimonthly` | 18–36 |
| `monthly` | 12 |
| `10ish` | 7–11 |
| `bimonthly` | 6 |
| `5/year` | 5 |
| `quarterly` | 4 |
| `triannual` | 3 |
| `semiannual` | 2 |
| `annual` | 1 |
| `unknown` | JCR 缺失，或 13–17 期/年等无对应区间 |

13–17 期/年、以及 JCR 未给值的记录记为 `unknown`；前者仍保留 `issues_per_year`，标签显示“每年 N 期”。

watchlist 5,279 行（含 41 本 Inactive）：`annual` 758、`semiannual` 160、`triannual` 148、`quarterly` 1,371、`5/year` 85、`bimonthly` 920、`10ish` 332、`monthly` 1,161、`semimonthly` 200、`weekly` 43、`unknown` 101（其中 33 本 JCR 缺失原始值，68 本为 13–17 期/年）。
包内 5,238 本（`include_daily=yes`）：`annual` 751、`semiannual` 159、`triannual` 146、`quarterly` 1,358、`5/year` 85、`bimonthly` 910、`10ish` 332、`monthly` 1,154、`semimonthly` 200、`weekly` 43、`unknown` 100。

## 目录文件

- `journals.json`：5,238 本 Q1 期刊，一行一本。字段包括
  `journal_key`、`name`、`name_en`、`issn`、`issns`（issn/eissn 去重）、`publisher`、`url`、`tags`，
  以及 `edition`、`publication_frequency`、`issues_per_year`、`frequency_class`、`jcr_year`、
  `jcr_quartile`、`primary_category`、`categories`、`scopus_active`、`scopus_top_levels`、
  `scopus_source_id`、`openalex_source_id`、`crossref_journal_id` 等审计字段。
- `tags` 固定 4 个，按顺序为：`JCR:Q1`、`EDITION:<SCIE|SSCI|ESCI|AHCI|?>`、
  `频次:<年刊|半年刊|季刊|双月刊|月刊|半月刊|周刊|每年N期|未知>`、`primary_category`（截断到 24 字）。
  `scopus_active`、`scopus_top_levels` 等仍保留为独立字段，不再占用 tags。
- `manifest.json`：参数与输出协议；`package_key=foreign_q1_journals`，版本 `1.1.1`。
- `crawler.py`：OpenAlex → Crossref 适配器，无逐刊硬编码。
- `requirements.lock`：仅标准库。

## 参数

| 参数 | 默认值 | 范围/取值 | 说明 |
| --- | ---: | --- | --- |
| `journal_keys` | 前 20 个 key | 1–5,238，去重 | 选择期刊；key 必须存在于 `journals.json` |
| `collect_mode` | `keywords` | `keywords` / `latest_issue` / `bulk_window` | `latest_issue` 按日期窗口逐刊取最新文章；`keywords` 额外带检索词；`bulk_window` 按 ISSN 分组批量查询 OpenAlex（见下） |
| `bulk_size` | `100` | 1–100 | `bulk_window` 每组 OR 查询的 ISSN 数；超出范围时按 1/100 截断 |
| `search_terms` | `[]` | 最多 10 条 | 关键词模式使用；与 request 的 `query`/`aliases` 合并，最多取 5 个 |
| `lookback_days` | `30` | 1–90 | 向前回溯天数；request 的 `time_range` 优先 |
| `per_journal_limit` | `20` | 1–100 | 每本刊最多返回条数；最终还受 request `limit` 约束 |
| `timeout_seconds` | `25` | 5–120 | 单次 HTTP 请求超时 |
| `require_abstract` | `false` | 布尔 | 为 `true` 时丢弃无摘要记录（两种模式均生效） |

`latest_issue` 以 `from_publication_date` / `to_publication_date`（OpenAlex）或
`from-pub-date` / `until-pub-date`（Crossref）限定窗口，按出版日期倒序取数。

### `bulk_window` 批量模式

用于全量 Q1 快速采集，避免逐刊请求的固定开销：

1. 读取 `journal_keys`（单批可达 500 本），按每本 `issns` 收集 ISSN，建立 `ISSN -> (journal_key, 目录 ISSN)` 映射；一个刊可对应多个 ISSN，一个 ISSN 只映射到先出现的刊。
2. 将所有 ISSN 按 `bulk_size`（默认 100）分组，每组发一次 OpenAlex works 请求：
   `filter=primary_location.source.issn:<issn1>|<issn2>|...,from_publication_date:<start>,to_publication_date:<end>`，
   并带 `per-page=100`、`cursor=*`、`sort=publication_date:desc`、`select`（id/doi/title/日期/type/authorships/biblio/摘要倒排/primary_location/OA/被引/language）与 `api_key`（环境变量）。
3. 用 `next_cursor` 逐页取数，直到游标为空、无结果、达到 request `limit` 或任务 `deadline_at`；若组内所有刊都已达到 `per_journal_limit` 则提前结束该组。
4. 对每条 work，用 `primary_location.source.issn`（缺失时用 `issn_l`）匹配回刊；匹配不到则跳过并累计为 `BULK_UNMATCHED_WORK` warning。记录仍由 `openalex_record()` 生成（字段、DOI 身份、标题过滤与逐刊模式一致），DOI 去重，每刊最多 `per_journal_limit` 条，总数不超过 request `limit`。
5. 单组请求失败会按 1s/2s 退避重试 3 次，仍失败则记 `BULK_GROUP_FAILED` warning 并继续下一组，不影响整包；全部组失败时任务才为 `failed`。
6. bulk 模式记录 `source_api="openalex"`，不做 Crossref 回退；窗口内 0 条的刊不会出现在 `items` 中，需由平台报告按选中刊清单标注。

`latest_issue` 仍是逐刊模式，选刊与取数流程与 1.0.x 一致；1.1.1 起“源返回记录但全被过滤”会触发 Crossref 回退，且不再静默计为成功。`bulk_window` 仅用于全量快速采集。

## 输出

输出 schema 与 `supplement_journals` 一致，共 20 个字段：
`doi`、`journal_key`、`journal_name`、`issn`、`title`、`url`、`authors`、`affiliations`、`abstract`、
`published_at`、`year`、`volume`、`issue`、`pages`、`language`、`open_access`、`cited_by_count`、
`source_api`、`openalex_id`、`matched_terms`。

`source_api` 为 `openalex` 或 `crossref`，可用于区分实际数据源。不返回全文、PDF 地址或附件。

## 限速与稳定性

- OpenAlex 每页最多 100 条，Crossref 每页最多 100 条。
- 逐刊模式每本期刊处理完后休眠 0.15 秒；`bulk_window` 翻页之间休眠 0.15 秒。单次响应上限 8 MB。
- OpenAlex 可选密钥来自环境变量 `CRAWLER_SECRET_OPENALEX_API_KEY`（manifest 中声明为 `OPENALEX_API_KEY`），未设置时走匿名配额。
- 未知 `journal_key` 返回 `UNKNOWN_JOURNAL` 警告；单刊请求失败返回 `JOURNAL_REQUEST_FAILED` 警告；源返回的记录全被 DOI/标题过滤时返回 `JOURNAL_ITEMS_FILTERED`，该刊不计入成功；bulk 单组失败返回 `BULK_GROUP_FAILED`，无法匹配 ISSN 的记录计入 `BULK_UNMATCHED_WORK`；全部期刊/分组失败时任务状态为 `failed`。

## 已知限制

- 平台 `load_journal_catalog()` 对 `journals.json` 有 **5,000 行 / 4 MB** 上限。本包为 5,238 行（约 3.8 MB），因此网页端“选刊”接口 `/api/v1/packages/foreign_q1_journals/journals` 会因行数超限报错；Worker 直接读取目录，按 `journal_keys` 分批建任务不受影响。若要在网页端选刊，需要平台侧放宽上限或把目录拆成多个 ≤5,000 行的分片。
- `journals.json` 的 `tags` 已固定为 4 个（`JCR:Q1`、`EDITION:*`、`频次:*`、`primary_category` 前 24 字），`scopus_active` / `scopus_top_levels` 等仍保留为独立字段。
- 部分期刊在 OpenAlex 的 ISSN 映射不完整；逐刊模式会依次尝试 `issns` 中最多 3 个 ISSN，bulk 模式则把所有候选 ISSN 一起放进 OR 过滤。
- 逐刊模式下 OpenAlex 对某刊返回 0 条时会再用同一 ISSN 列表查 Crossref；若 Crossref 在窗口内同样无记录，则该刊本次仍返回 0 条（源已响应，不算失败，不产生 warning）。若两个源都返回了记录但全部被 DOI/标题过滤，则记 `JOURNAL_ITEMS_FILTERED` warning 且不计入成功，避免静默 0 条。
- `bulk_window` 依赖 OpenAlex 的 ISSN 反查：若某条 work 的 `primary_location.source.issn`/`issn_l` 不在本批映射中会被跳过；若某组请求持续失败，该组覆盖的期刊本轮为 0 条，但其他组继续。bulk 模式不做 Crossref 兜底。
- `bulk_window` 的每组 ISSN 数受 OpenAlex 查询串长度与稳定性限制，建议保持默认 100；单页仍为 100 条、8 MB 上限，摘要倒排索引较长时可能需要更多翻页。
- 仅覆盖 OpenAlex/Crossref 有元数据的文章；无 DOI 的记录会被跳过（DOI 为身份字段）。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest crawler_packages/academic/foreign_q1_journals/tests -q -p no:cacheprovider
```

测试全部使用 mock，不访问网络；其中 watchlist 交叉校验在 CSV 不存在时自动跳过。共 31 项，覆盖逐刊 `keywords`/`latest_issue` 与 bulk 的 ISSN 分组、cursor 翻页、DOI 去重、每刊/总量上限、ISSN 不匹配、分组失败与重试；另含频次三字段一致性、tags 顺序与 0 条误判回退（OpenAlex 记录被过滤 → Crossref；两源均空时 warning/不静默成功）。
