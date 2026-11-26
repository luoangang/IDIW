# 玛格泰克中文期刊检索包

这是协议 v1.0 的 `1.16.5` 版源码包，不会随平台启动自动注册。平台中已安装的旧版不会自动升级，需要重新导入此目录或其 ZIP。

## 内含期刊

`journals.json` 当前 409 家：原逐刊实测刊与此前当期目次验证补入的期刊。2026-11-22 补《管理学报》（显式 `current_url`）、仿生工程学报（旧版 `txt_biaoti` 模板）和《化学进展》（`api_mode=stae`，读取 magetech 3.0 JSON API）；2026-11-26 依据国内 P1 Top20 live 探测补《电工技术学报》（`eb848c086da3fb6d`，当期 23 篇）。原有三家包内标识保持不变：

- 数据分析与知识发现（`data_analysis`）
- 图书情报工作（`lis`）
- 情报资料工作（`qbzl`）

默认仅选上述三家。原 98 家中，96 家在“研究”词容量测试中取得至少 70 条；《福建电脑》和《当代亚太》对换词及反向词有响应，但未证实可取 70 条。《当代亚太》仍有解析条数低于页面自报总数的问题。其他候选，包括 70 家分页停滞的期刊，已从可选目录移除；原始审计仍在 `journal_catalog/`。历史测试不保证站点长期可用，也不保证其余 96 家都通过了反向词过滤复核。

## 可配置参数

- `journal_keys`：本次启用的期刊，默认上述三刊；每次最多选择 30 家。目录内其他期刊使用 `journals.json` 中的 `journal_key`。
- “情报资料工作”继续使用旧包的 `qbzl` 键，结果身份保持不变。
- `collect_mode`：`keywords`（默认，按检索词查全站）或 `latest_issue`（读取期刊 `current_url` 或默认 `/CN/current` 当期目次，忽略检索词，适合持续监测最新发表）。
- `max_pages_per_journal`：关键词模式下每个期刊、每个检索词最多读取的页数，默认 20；`latest_issue` 模式复用同一参数限制当期翻页页数（内部上限 20 页）。
- `request_delay_ms`：请求间隔，默认 300 毫秒。
- `enrich_abstract`：`latest_issue` 模式下是否对摘要为空的文章补采详情页摘要，默认 `true`。只填空，不覆盖列表已给出的摘要。
- `abstract_enrich_limit`：每刊本次最多补采摘要的文章数，默认 5，允许 0–10；`0` 等同于关闭补采。补采只抓 HTML 文本，不下载 PDF，单条间隔 1.5–2 秒，失败写 `warnings` 且不影响整刊结果。

### 当期翻页

`latest_issue` 先解析当期入口页，再只跟随**同 host、同 path** 的数字分页/下一页控件（如 `?page=2`、`paperPage_list?pageNum=2`）抓取第 2..N 页，用同一解析器合并去重：

- 不会跟随年份/期次下拉框、过刊目录或跨期链接（URL 中的 `year_id`/`issue_id` 等期次参数必须与入口页一致，多出的非翻页参数也会被拒绝）。
- 首页与翻页页能提取到“2026年第10期”式期次标记时，标记必须一致，否则停止翻页并写 `ISSUE_MARKER_MISMATCH`。
- 无分页控件时保持单次请求；某页 0 新增（重复页）即停并写 `PAGINATION_STALLED`；最多 20 页。
- 页面本身没有分页控件时行为与旧版完全一致。

《电工技术学报》等站点使用旧版 Magtech 目次表（`TD.J_VM` 行 + `CN/abstract/abstractN.shtml`）：解析器按文章表格块配对标题、作者、年卷期页码与 DOI，并跳过页码为 0-0 的“目录”条目。

STAE（`api_mode=stae`，如《化学进展》）改为 `pageSize=200` 并按 `pageNum` 循环到 `total`，同时读取接口 `total`；若大 pageSize 被拒绝会回退到 50 并写 `STAE_PAGE_SIZE_FALLBACK`，返回条数等于 pageSize 且无 total 时写 `STAE_PAGE_TRUNCATED` 提示可能截断。

### 摘要补采

仅处理 `latest_issue` 结果中摘要为空的文章（每刊最多 `abstract_enrich_limit` 条），按顺序尝试：

1. `#zhaiyao .zhaiyao` 或 `div#zhaiyao`（CMA 系，含“目的/方法/结果/结论”分段）；
2. `#collapseOne .panel-body`（农学、耐火材料等 panel 模板）；
3. `TD.J_zhaiyao` 且以 `<b>摘要</b>` 开头（《电工技术学报》等旧版目次站点）。

文本在 `Abstract`、`关键词`、`参考文献`、`References` 处截断并做标签清洗；不使用只有 33 字截断的 `meta[name=description]`。详情页请求失败或找不到容器时写 `ABSTRACT_ENRICH_FAILED` / `ABSTRACT_ENRICH_EMPTY`，不致命。

`latest_issue` 模式对部分检索接口返回 403 或分页停滞、但当期目次页仍公开的站点更友好。2026-11-21 抽查中，中央音乐学院学报、中国临床护理、中国消毒学杂志可通过当期目次取得文章；华南理工大学学报（自然科学版）页面可访问但当期暂无可解析文章，中国农业气象当期页无文章。历史抽查不代表长期可用，仍需按刊观察 `warnings`。

平台任务的 `limit` 是整个插件包的总返回上限，并会在本次启用的期刊之间尽量平均分配，避免单个期刊独占额度。任务的时间范围会按论文年份做二次过滤。

## 导入体验

1. 若尚未安装，执行 `python platform_main.py import crawler_packages/academic/magetech_journals`，或压缩该目录后在平台导入页上传。
2. 创建学术文献监控任务，输入检索词并选择本插件。
3. 运行后在记录及插件数据表中查看结果。

`journal_catalog/groups/` 保留供应商分类的原始依据。导入 `1.16.5` 后建议先按期刊筛选并做小批量验证；新补入的期刊只验证了当期目次模式，不要一次设置全部期刊。

插件只使用 Python 标准库，不需要联网安装依赖。期刊站点结构变化或临时限流时，插件会把具体期刊错误写入 `warnings`，其他期刊仍可继续返回数据。
