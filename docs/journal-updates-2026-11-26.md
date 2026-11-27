# 期刊监测增量说明（2026-11）

本仓库基于组内 IDIW 爬虫平台（底座）；本轮主要更新集中在**期刊监测**部分，平台底座、代理池、周报、DeepSeek 助手等沿用原有实现。完整项目历程见 [project-history.md](project-history.md)，逐次运行明细见 [current-progress.md](current-progress.md)。

## 1. 国内期刊

- 13 个国内期刊包已导入平台，共 **3,185** 个可选刊；核心名单（北大核心 2023、CSSCI 2023–2024、CSTPCD 2024、CSCD 2023–2024 四并集 3,461）覆盖 **2,225/3,461（64.3%）**。
- 包版本：`cnki_cbpt` 1.12.7（846）、`custom_toc_journals` 3.10.7（849）、`magetech_journals` 1.16.9（417）、`qinyun_journals` 1.9.5（173）、`rhzh_journals` 1.3.7（328）、`vsb_journals` 1.2.5（14）、`sancai_journals` 1.0.4（3）、`founder_journals` 1.2.2（101）、`paperonce_journals` 1.1.3（78）、`sciengine_journals` 1.0.1（14）、`oa_rss_journals` 1.1.1（18）、`hep_mirror_journals` 1.1.1（6）、`supplement_journals` 1.1.2（338）。
- P1 1–196 已全部探测，累计写回 **64 本**；另对核心 backlog A/B 类做直连重试，补写回 **8 本**（心理学报、南京审计大学学报、棉纺织技术、植物遗传资源学报、海军航空大学学报、现代制造工程、数学进展、遥测遥控）。
- 覆盖匹配只认 ISSN/CN/完全同名；基础名/模糊匹配只标歧义，不冒充覆盖。公开源剩余以登录/验证码/WAF、SPA、仅 PDF、停更为主，backlog 1,123 本留档。

## 2. 国外 Q1

- 基于 JCR 2025 全学科 Q1 **5,279** 本（日更排除已知 Inactive 后 **5,238** 本）建 `foreign_q1_journals` **1.1.1**。
- `bulk_window`：100 ISSN/次 OR 查 OpenAlex、cursor 分页、DOI 去重、映射回期刊；OpenAlex 主源，空结果回退 Crossref；30 天回看、每刊最多 20 篇；JCR 出版频次写入 `publication_frequency/issues_per_year/frequency_class`。
- 全量 11 批已完成：**5,238 本、53,138 条**（唯一 DOI 53,136）、4,549 本有结果、689 本 0 条、DOI 覆盖率 100%、摘要 35,685（67.2%）。
- 500 本试点与全量报告分开发布；500 本是 watchlist 前 500，主要 ESCI/AHCI，不代表全 Q1。

## 3. 去重、翻页与摘要

- 所有包数据表增加 `sys_first_seen_at` / `sys_last_seen_at` / `sys_last_changed_at` / `sys_change_count`；只有内容哈希变化才更新“最近变更”，重复抓取只推进 `last_seen`。
- 国内 `latest_issue` 统一分页层：custom_toc 自动发现同 host/path 的页码参数并排除年份/期次；CNKI 支持 `max_pages_per_journal`；magetech/qinyun/rhzh 增加期次分页与跨期过滤。
- 详情页摘要补采：hep、magetech、paperonce、vsb、custom、rhzh、qinyun；同批 48 本摘要 59.8%→95.8%。
- parser 扩展：custom_toc 的 yiigle 目录区块、pair_link JS 链接模板、CCJ JSON API、目次/封面噪声；magetech 的 abstract 路由与封面过滤；rhzh 的 gzip/resName/相对链接；CNKI 的 `稿约/编后/召开/典型案例` 过滤；sancai 的郑大医学版 API。

## 4. 工程与验证

- 平台：选刊目录上限 10,000 行/8MB；数据页支持“全部 / 今天有变动”；monitor 可跨包选刊；Worker/Scheduler 继续按研究模式手动运行，不常驻。
- 测试：平台 **181 passed + 81 subtests**；包单测覆盖 custom_toc 47、qinyun 36、magetech 35、rhzh 35、cnki 32、vsb 19、paperonce 15、sancai 3。
- 冒烟：run48（9 本/44 条）、run49（9 本/34 条）、run50（14 本抽检/52 条）、run52（4 本/14 条）、run53（8 本/28 条）；均 0 rejected，monitor 已归档。

## 5. 数据边界

- 只采集**文章元数据 + 文章/PDF 链接**，不下载、不存储 PDF。
- 不登录、不绕过验证码/WAF/Cloudflare；blocked 留 backlog。
- 核心名单、JCR/Scopus/知网/万方原始数据、全量文章明细与大型 HTML/CSV 报告保留在本地，不随仓库公开；仓库只带代码、包目录、测试、文档和小型 applied/evidence CSV。
- 本仓库是组内平台的期刊监测增量，不是新的平台底座；专利与低空相关性 Agent 仍属后续工作。
