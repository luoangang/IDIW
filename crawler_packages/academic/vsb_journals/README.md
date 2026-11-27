# 高校 VSB 当期目次包

本包为协议 v1.0 的 `1.2.4` 版。

读取高校期刊 VSB sitebuilder 官网当期目录 HTML。2026-11-22 对 `vsb-sitebuilder` 集群 91 本逐站探测，11 本当期页可直接解析出文章标题和链接，纳入本包；其余多为目录图片、新闻页或动态菜单，暂未纳入。2026-11-22 追加社会科学家、贵州医科大学学报、职业技术教育、井冈山大学学报（社会科学版）、俄罗斯学刊 5 本。2026-11-24 追加东北石油大学学报。2026-11-26 追加管理科学（国内 P1 Top20 live 复核，当期 2026,39(3) 共 12 篇；ISSN 1672-0334，CN 23-1510/C）。当前 `journals.json` 共 13 条：2377 目录 12 条，另 1 条为东北石油大学学报。

## 来源标注

- 数据来自期刊官网当期目录页，不是 OpenAlex/Crossref；
- 选刊标签：`采集:官网当期目次` + `当期核验` + `目录:2377`；
- `journals.json` 记录 `catalog_source=2377_catalog`、`data_source=official_toc`、`source_group=vsb`、`official_url`、`current_url`、`verification_mode=current_issue_html`、`probe_items`、`probe_first_title`；
- 管理科学另记 `evidence=domestic_p1_top20_2026-11-26`、`source_file=domestic-p1-top20/agent4.csv`、`issn`、`cn`、`core_levels`、`categories`、`link_base`、`article_link_regex`；
- 同济大学学报（社会科学版）的当期文章链接指向超星阅读页，额外标注 `文章页:超星`，但标题和链接来自官网当期目录。

## 单刊链接规则

`journals.json` 可选的 `article_link_regex` 会覆盖包内默认文章链接正则；`section_start_regex` / `section_end_regex` 可先把解析范围收窄到当期正文区，避免把侧栏“下载中心/通知公告”等 `/info/` 链接误收为文章。管理科学即使用这两个区段字段：文章区从 `article-list article-list-table` 开始，到 `main-right` 侧栏前结束；`article_link_regex` 仍保留官网 `/info/\d+/\d+\.htm` 的通用链接形态。未配置这些字段的期刊保持原有行为。

## 参数

- `journal_keys`：最多 100 本，默认 12 本；东北石油大学学报需在 `journals.json` 中取键后显式选择。
- `collect_mode`：`latest_issue`（默认，返回整期）或 `keywords`（仅对当期目次做本地关键词过滤；query 多词按 AND、aliases 按 OR，匹配标题/摘要/作者/DOI；**不是全刊检索**）。
- 平台请求的 `query` 仍需非空；`latest_issue` 模式不使用检索词。
- `per_journal_limit`：每刊上限，默认 50。
- `enrich_abstract`：默认 `true`，`latest_issue` 模式下对**摘要为空**的文章选择性抓详情页摘要；可用结构为 `meta[name=description]`（长度 >100）、`div.article-abstract`、`【摘要】`、行内 `摘要：`，`meta` 过短时改用行内。仅填空、不覆盖已有摘要。
- `abstract_enrich_limit`：每刊最多补抓条数，默认 5，范围 0–10（0 关闭）。
- 自动跳过 `kns.cnki.net`（安全验证）与明显仅 PDF 的页面；详情请求间隔 2 秒；单篇失败只记录非致命 warning，不影响整刊；仅保存文本，不下载 PDF，不登录、不绕验证码。
- `timeout_seconds`：单请求超时，默认 20。
- 平台请求的 `query` 仍需非空；`latest_issue` 模式不使用检索词。

只解析当期目录中的文章链接，不下载全文、不绕过登录或验证码。目录/封面/封底/征稿/启事等导航项会被过滤。历史探测不代表长期可用，正式运行前建议小批量复测。

管理科学站点 2026-11-26 实测当期页为 2026 年 39 卷 3 期，过刊页 `gkll.htm` 仅列到 2023 年，无法确认是否存在更晚未上网期；任务运行前建议复核当期是否更新。
