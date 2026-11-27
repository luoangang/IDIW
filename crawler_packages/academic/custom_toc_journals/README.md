# 自定义当期目次期刊包

读取期刊官网公开当期目次，支持自定义/静态 HTML、公开 JSON 列表 API、onclick 构造的文章页、“过刊索引取最新一期”、按刊链接正则、表格“标题+摘要链接”配对、页面切段与分页等多类入口，文章标题和链接来自官网。当前 **829** 本（3.10.3），包含五批中文、英文、A3/A4/A5G6 等核心刊补录，2026-11-22 blocked 复测与 pending_adapter 回迁期刊，以及 2026-11-26 国内 P1 期刊补录。

## 来源标注

- 选刊标签：`采集:官网当期目次` + `当期核验` + `目录:2377`；
- `journals.json` 记录 `data_source=official_site`、`official_url`、`current_url`、`probe_items`；个别官网对采集器 UA 返回 502 时可按刊配置 `user_agent`（仍为公开页面，无登录/Cookie/WAF 绕过）；
- 入口能力：普通 HTML 走 `current_url`；公开 JSON 列表配置 `json_api`（含字段映射、URL 模板、页面参数提取）；onclick 文章页配置 `onclick_link`（正则 + URL 模板）；期次静态页配置 `issue_link`（从过刊索引解析最新一期，可跳过空期）+ `link_base`（修正相对链接）；`issue_link.select=latest` 时按 URL 中的年/期数字取最新一期（适用于索引按年/期升序排列的站点），默认仍取索引首条；特殊模板可用 `article_link_regex`（按刊链接正则）、`pair_link`（表格标题+摘要链接配对）、`section_start_regex`/`section_end_regex`/`last_section_regex`（按锚点切段）和 `pagination`（按模板翻页）；请求自动携带 CookieJar，可用 `max_response_bytes` 放宽单刊响应上限；
- 只解析文章链接和标题，不下载全文，不绕过登录/验证码；目录/封面/摘要重复链接会被过滤。

## 最新一期翻页

`latest_issue` 的 plain/json/onclick/pair/issue 五种模式统一走同一个分页层：先取首页并解析，再按配置或自动发现决定是否抓第 2..N 页，合并去重后仍受 `per_journal_limit` 与任务 `limit` 约束。

- 显式配置优先：`pagination.url_template`（必须含 `{page}`）、`start`（默认 2）、`max_pages`（末页页码，硬上限 20）。相对模板会用 `urljoin(journal.current_url, ...)` 解析，例如 `"url_template": "?apage4={page}"`；可选 `base` 覆盖基准 URL，`allow_external_host` 允许跨域分页（默认只允许同 host）。
- 自动发现：仅 plain / pair / issue（HTML 且复用现有解析器）启用，JSON API 与 onclick **不自动翻页**。规则为同 host、同 path、仅页码参数不同（如 `page`/`p`/`pageNo`/`apage4`），排除 `year_id`/`quarter_id`/`issue`/`volume`/`vol`/`issueId` 等期次或年份参数；至少发现 2 个页码才生效，最多 10 页。首页能提取期次标记（如 `2026年第11期`、`2026年 第11期`）时，后续页必须仍是同一期。
- 停止条件：0 新增、整页 URL 指纹与已抓页重复、连续 2 页请求/解析异常、HTTP 错误、期次标记变化、达到页数上限（20/10）。非正常停止会在 `warnings` 追加可解释字符串（`journal_key (刊名): PAGINATION_STOPPED 原因`），单刊翻页失败不影响其他刊；0 新增属正常收尾，不写 warning。
- JSON/onclick 只接受显式 `pagination` 配置。机电工程 API 的 `pageNum` 被服务端忽略、`pageNo=2` 会串到上一期，因此不配置自动翻页。

## 摘要补采

`latest_issue` 模式下对缺摘要文章抓详情页补摘要，只填空、不覆盖已有摘要；每刊最多尝试 `abstract_enrich_limit` 篇（默认 3，最大 10），相邻请求间隔约 1.6 秒，单篇失败静默跳过，不下载 PDF。

详情页提取顺序：`meta[name=citation_abstract]` → 常见摘要容器（`CnAbstractValue`/`EnAbstractValue`、`in_abst`、`article-abstract` 等）→ `div.zhaiyaojs`（跳过作者块，截断到 `Abstract`）→ `【摘要】`（截断到 `【关键词】` 等标签）→ 行内 `摘要：`/`Abstract：` → `meta[name=description]`（仅当长度大于 100 字，避免 SEO 短描述）；正文统一在关键词、参考文献、基金项目等位置截断。JSON 模式仍优先使用配置/常见摘要字段。

## 参数

- `journal_keys`：默认全部 829 本。
- `collect_mode`：`latest_issue`（默认，返回整期）或 `keywords`（仅对当期目次做本地关键词过滤；query 多词按 AND、aliases 按 OR，匹配标题/摘要/作者/DOI；**不是全刊检索**）。
- 平台请求的 `query` 仍需非空；`latest_issue` 模式不使用检索词。
- `per_journal_limit`：默认 50；`timeout_seconds`：默认 20。
- `enrich_abstract`：默认 true，为缺摘要文章补抓详情页摘要。
- `abstract_enrich_limit`：默认 3，每刊最多尝试补抓的文章数，0 表示关闭。
