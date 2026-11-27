# 国内期刊处理思路（2026-11-24）

- 定位：把 2026-11-24 国内核心期刊补录、当期目次适配、摘要补采和日更实验整理成一套可复用的处理思路；国内部分作为方法基线，最后一节给出国外期刊的复用方式。
- 数据口径：本文数字均来自 2026-11-24 的报告、CSV 和包目录，不代表实时复核结果；引用的证据文件见第 10 节。
- 一句话结论：**只采文章元数据与链接，不下载 PDF；国内是“当前期轮询 + 去重”，不是按发布日期日更；摘要必须分层补采，不能假设所有包都有；国外应复用“维表/分包/质检/覆盖统计”的骨架，但把时间语义换成发布日期窗口、把去重键换成 DOI。**

---

## 1. 目标与边界

### 1.1 目标

对核心名单中的每一种期刊，从公开页面或公开接口取得**文章级元数据**，写入平台结果表，支持日更、周更和回补。

标准字段：

| 字段 | 含义 | 说明 |
|---|---|---|
| `journal_key` | 包内期刊稳定键 | 16 位十六进制；同一刊跨批次不重建 |
| `journal_name` / `journal_url` | 刊名 / 官网或入口 URL | 刊名按目录；URL 保留官网或当前入口 |
| `external_id` | 文章在来源站内的 ID | 用于国内包去重 |
| `title` | 文章标题 | 必填，非空 |
| `url` | 文章页 / 摘要页 / DOI 落地页 | 必填，非空；不保证全文可访问 |
| `authors` | 作者 | 可为空；格式随包不同 |
| `abstract` | 摘要 | 可为空；后加需求，按第 5 节补采 |
| `doi` | DOI | 可为空；CNKI 当前无 DOI 字段 |
| `year` / `issue` / `pages` | 年 / 期 / 页码 | 视来源；国内普遍没有发布日期 |
| `pdf_url` | PDF **链接字符串** | 只有 magetech 部分模板提取；从不下载文件 |
| `source_api` | 来源标识 | 如 `custom_toc`、`founder`、`oa_rss` |
| 平台系统字段 | `sys_identity_hash` / `sys_content_hash` 等 | 平台按身份字段去重、按内容哈希判更新 |

### 1.2 不做什么

- **不下载 PDF、不抓全文**：`pdf_url` 只保存链接，不发起文件请求；文章页里的 PDF 按钮不点。
- **不登录、不验证码、不绕 WAF、不关闭 TLS 校验、不做对抗式代理**：遇到 401/403/412、登录墙、验证码、WAF，记录 `blocked` 或 `E-登录/验证码/WAF`，不硬加。
- **不做全历史枚举**：当前只有“当期目次”和“当期关键词过滤/检索”；历史全量期次枚举尚未实现。
- **不把“当期”说成“今天发布”**：国内包的 `latest_issue` 是当前可见期，不是发布日期增量。
- **不伪造字段**：没有摘要、DOI、发布日期就留空；不用第三方全文或模型生成内容冒充元数据。
- **不把入口当官网**：CBPT 门户、PaperOnce/三才页面、HEP 镜像、OpenAlex/Crossref 都必须打来源标签，不能标成“官网”。
- **不重分发核心名单**：CSSCI/CSTPCD/CSCD/北大核心名单只在本地研究使用，报告标注 `official` / `reference`；正式采信前需官方或授权版本复核。

### 1.3 来源标签

新写入的每一条期刊目录必须同时有 `data_source` 和 `tags`，不能只靠 `supplier` 推断。

`data_source` 规范值：

| `data_source` | 含义 | 典型包 |
|---|---|---|
| `official_site` | 期刊官网公开页面 | custom_toc 的普通 HTML |
| `official_api` | 期刊官网公开 JSON/API | founder、paperonce、magetech 的 JSON、qinyun/rhzh 的接口 |
| `official_rss` | 期刊官网 RSS | oa_rss |
| `official_toc` | 期刊官网当期目录页 | vsb |
| `public_mirror` | 公开镜像，不是官网 | hep_mirror |
| `public_platform` | 公开聚合/门户页面 | CBPT 门户、PaperOnce/三才页面等 |
| `openalex_crossref` | OpenAlex/Crossref 元数据 | supplement |
| `pending` | 仅登记、尚未适配 | supplement 的 `pending_journals.json` |

`tags` 规范前缀：

- 采集方式：`采集:官网当期目次`、`采集:官网API`、`采集:官网RSS`、`采集:公开镜像`、`采集:OpenAlex/Crossref`、`采集:待适配`。
- 质检/目录：`当期核验`、`目录:2377`、`目录:核心`、`官网HTML`。
- 来源限定：`非官网`、`公开平台`、`文章页:超星`、`文章页:知网`。
- 平台选刊标签最多保留 4 个、每个最多 24 字；更细的来源写在 `data_source_detail`、`official_url`、`current_url` 等 JSON 字段。

规则：

1. 文章元数据来自 CBPT/PaperOnce/三才/HEP/OpenAlex 等第三方入口时，必须标 `公开平台` / `非官网` / `采集:公开镜像` / `采集:OpenAlex/Crossref`，不能标官网。
2. 文章链接指向超星、知网等第三方阅读页时，标题和链接仍来自官网当期目录，但要加 `文章页:超星` / `文章页:知网`。
3. 历史目录有标签债务：当前有 **853** 条包内期刊没有 `data_source`（cnki_cbpt 524、rhzh 122、qinyun 104、magetech 102、sancai 1），且存在 `采集:官网当期`、`采集:核心补录`、`目录:核心` 等历史变体。非空分布为 `official_site` 1623、`openalex_crossref` 338、`official_api` 165、`official_rss` 18、`official_toc` 12、`public_platform` 13、`public_mirror` 6。新批次必须补齐；旧批次按“不追溯改写、只在下一版新增字段”处理。

---

## 2. 分层架构

```
核心名单(.local/core/*.csv)
        ↓ 合并/去重/严格匹配
期刊维表(journal_catalog/journals.json, 2377)
        ↓ 按平台/模板选包
包目录(crawler_packages/academic/<package>/journals.json)
        ↓ latest_issue / keywords
当期目次或检索结果
        ↓ 解析
文章元数据(title/url/authors/abstract/doi/year/issue/pages/pdf_url)
        ↓ 可选
摘要补采(详情页/JSON enrichment，限量、可关、失败不致命)
        ↓ 平台 identity + content hash
结果表(pkg_data_<id>)
        ↓
日更/周更/回补 → QA/覆盖统计 → adapter backlog
```

| 层 | 职责 | 主要文件/脚本 | 产出/证据 |
|---|---|---|---|
| L0 核心名单 | CSSCI、CSTPCD、CSCD、北大核心等并集 | `.local/core/*.csv`；`scripts/build_core_coverage.py` | 3461 本并集、核心级别/学科/来源质量 |
| L1 期刊维表 | 统一的刊名、URL、供应商、模板组 | `journal_catalog/journals.json`（2377 本） | `journal_key`、`name`、`url`、`supplier`、`template_group`、`evidence` |
| L2 平台/模板分包 | 一个平台或一类模板一个包；不按单刊建包 | `crawler_packages/academic/<package>/` 的 `journals.json`、`manifest.json` | 可安装包、选刊目录、参数字段 |
| L3 采集模式 | 当期目次或关键词过滤/检索 | 各包 `crawler.py`；`collect_mode` | `latest_issue` / `keywords` |
| L4 文章元数据 | 解析标题、链接、作者、摘要、DOI、年/期/页 | 各包 `normalize` / `build_item` | 统一字段的结果行 |
| L5 摘要补采 | 列表页没有摘要时按刊补采 | qinyun/rhzh/custom/cnki 的 `enrich_abstract` | `abstract`、补采统计 |
| L6 去重入库 | 国内按 `journal_key + external_id`；国外按 DOI | `crawler_platform/storage.py`、`protocol.py` | `inserted` / `updated` / `unchanged` / `batch_duplicates` |
| L7 调度/回补 | 每日当前期轮询、失败重试、周/月回补 | 平台 Scheduler/Worker；包内 warnings | 运行记录、失败台账 |
| L8 QA/统计 | 冒烟、单测、覆盖、backlog、来源统计 | `scripts/smoke_core_additions.py`、`build_core_coverage.py`、`build_adapter_backlog.py`、`summarize_core_sources.py` | coverage CSV/MD、backlog、source summary |
| L9 adapter backlog | 已探测未入包、失败原因分类 | `scripts/build_adapter_backlog.py` | A–H 分类、P1–P5 优先级 |

三条不变量：

1. **按平台/模板分包**：同一供应商/同一 CMS 模板的刊放在一个包里；单刊特例用按刊配置（`current_url`、`article_link_regex`、`link_base`、`section_*_regex`、`pagination`），不新建单刊包。
2. **安装后的包不可直接改**：源码在 `crawler_packages/`，平台安装副本在 `crawler_platform_runtime/packages/`；升级必须升 `package_version` 后重新导入，不能改旧版本文件。
3. **身份字段不能中途改**：国内包统一 `journal_key + external_id`；国外 `doi`。升级时平台禁止修改 `identity_fields`，需要换身份键就新建包。

最小闭环：

```
核心名单 → 维表 → 包目录 → live verify → apply → smoke → import → coverage/backlog/source → docs
```

---

## 3. 国内包分类与字段能力矩阵

### 3.1 分类

按主入口分四类（一个包可能跨类，以主入口归类）：

1. **结构化 API/JSON 类**：`founder_journals`（方正 rc-pub）、`paperonce_journals`（LastIssueList）、`sancai_journals`（三才 ArticleSearch）、`oa_rss_journals`（官网 RSS）、`magetech_journals` 的新版 JSON、`qinyun_journals` 的新版 AJAX、`rhzh_journals` 的 `searchResult`/`current-data`。
2. **HTML 当期目次类**：`cnki_cbpt`（CBPT/腾云门户）、`magetech_journals`（`/CN/current`）、`qinyun_journals`（新旧 ASP.NET 页面）、`rhzh_journals`（`article-list`）、`vsb_journals`（VSB sitebuilder）、`hep_mirror_journals`（HEP 公开镜像）。
3. **自定义 CMS 兜底类**：`custom_toc_journals`，用 `current_url`、`json_api`、`onclick_link`、`issue_link`、`pair_link`、`article_link_regex`、`section_start/end_regex`、`pagination` 等按刊配置覆盖独立站点。
4. **元数据兜底类（非国内官网）**：`supplement_journals`（OpenAlex/Crossref，338 本）、`flagship_journals`（Nature/Science/PNAS/Cell，4 本）。它们不是国内包，但放在矩阵里作为“字段最全”的参照。

### 3.2 包清单与字段能力矩阵

下表版本/目录数为 2026-11-25 当前源码状态；字段列的 `x/y` 是 2026-11-24 每日实验中“有结果期刊的首条文章”口径（见 `daily-sample-summary-2026-11-24.md`），不是全量保证。

| 包（版本/目录数） | 主入口/模板 | 标题+URL | 作者 | 摘要 | DOI | PDF 链接 |
|---|---|---|---|---|---|---|
| `cnki_cbpt` 1.12.2 / 825 | CBPT `paper_list/type_benqi`、WKD `paperDigest`、公开搜索 API | 保证 | 常见（4/5） | portal `paperBox` 摘要 + WK 同会话 `paperDigest`；agent 49/50、主线程 15/15 | **无字段**（0/5） | 无 |
| `magetech_journals` 1.16.2 / 408 | `/CN/current` HTML、STAE JSON、旧版模板 | 保证 | 4/4 | 3/4 | 2/4 | **2/4（全部条目 8/12）** |
| `custom_toc_journals` 3.10.1 / 825 | 自定义 HTML、JSON API、onclick、过刊索引、切段、分页 | 保证 | JSON 类有；样本 0/5 | JSON 字段 + 详情 enrichment；样本补后 12/15 | JSON 类有；样本 2/5 | 无 |
| `qinyun_journals` 1.9.1 / 170 | 新版 AJAX、旧版 ASP.NET、当期 HTML/内嵌 JSON | 保证 | 字段有；样本 0/3 | 详情 enrichment（`Abstract`/`CnAbstractValue`/标签段）；85 条 41→75（88.2%）；主线程 9/9 | 字段有；样本 0/3 | 无 |
| `rhzh_journals` 1.3.2 / 317 | JSON `searchResult`、HTML `article-list`、`search-data`、`current-data` | 保证 | 字段有；样本 0/4 | `current-data.abstractinfoCn` + 详情；65 条 60 有（92.3%）；主线程 13/15 | 2/4 | 无 |
| `founder_journals` 1.2.2 / 101 | 方正 rc-pub JSON API | 保证 | 5/5 | 4/5 | 4/5 | 无 |
| `paperonce_journals` 1.1.1 / 77 | PaperOnce `api/api/Web/LastIssueList` + 旧版 paperopen HTML | 保证 | 3/3 | 3/3 | 2/3 | 无 |
| `sciengine_journals` 1.0.1 / 14 | SciEngine 公开 JSON；最新卷期发现 + 固定期回退 | 保证 | API `pAuthorList` | API `intro`，部分刊为空 | 有 | 链接 |
| `oa_rss_journals` 1.1.1 / 18 | 官网 `/oa/rss.aspx` | 保证 | 3/3 | 2/3 | 0/3 | 无 |
| `vsb_journals` 1.2.2 / 12 | VSB sitebuilder 当期目录 HTML | 保证 | 0/5 | 0/5 | 0/5 | 无 |
| `hep_mirror_journals` 1.1.0 / 6 | HEP 公开镜像当期目录 | 保证 | 0/5 | 0/5 | 0/5 | 无 |
| `sancai_journals` 1.0.3 / 2 | 三才 HTML/JSON | 保证 | 2/2 | 2/2 | 0/2 | 无 |
| `supplement_journals` 1.1.2 / 338 | OpenAlex/Crossref 日期窗口 | 保证 | 3/3 | 2/3 | 3/3 | 无 |
| `flagship_journals` 1.0.1 / 4 | OpenAlex 检索 + Nature 页面/Crossref 补摘要 | 保证 | 1/1 | 1/1 | 1/1 | 无 |

读表结论：

- **founder、paperonce、sancai 的摘要+DOI 最稳定**；magetech、oa_rss、supplement 次之。
- **qinyun/rhzh 已补详情 enrichment**：勤云抽样 85 条摘要 41→75（88.2%），仁和 65 条 60 有（92.3%）；主线程复测 9/9、13/15。
- **custom 只能按来源补**：JSON 字段/详情页通用容器能补一部分，抽样 255 条 23→49；HTML 无摘要/PDF-only 的站补不到。
- **CNKI 已实现 1.12.1**：portal 列表 `div.paperBox` 有完整摘要；WK 详情页用列表页同会话 Cookie 可取 `<p id="digest">`，不是验证码；agent 49/50、主线程 15/15 有摘要（含 2 条格式指南，后续按标题过滤）。
- **PDF 链接只有 magetech 部分模板提取**；其他包即使文章页有 PDF，也没有提取或下载。
- **国内包普遍没有 `published_at`**：`year`/`issue` 有，但不是发布日期；只有 supplement/flagship 有 `published_at`。
- `cnki_cbpt` 的结果字段没有 DOI；`custom_toc` 的 `source_api` 固定为 `custom_toc`，JSON 类才有作者/DOI。

### 3.2.1 摘要补采第一阶段结果（2026-11-24）

| 包 | 版本 | 补采方式 | 抽样结果 |
|---|---|---|---|
| qinyun | 1.8.0 | 列表页 `Abstract`/`CnAbstractValue`/标签段 + 详情页 | 85 条 41→75（88.2%）；主线程 9/9 |
| rhzh | 1.2.0 | `current-data.abstractinfoCn` + 详情 `article-abstract` | 65 条 60 有（92.3%）；主线程 13/15 |
| custom | 3.9.0 | JSON `fields.abstract`/常见字段 + 详情常见容器 | 255 条 23→49；主线程 12/15 |
| cnki | 1.11.1 | portal 列表 `paperBox` 摘要；WK 同会话 `paperDigest` | agent 49/50（98%）；主线程 15/15；WK 54 次详情 0 验证码 |

- 主线程独立复测三包：39 条中 34 条有摘要（87%），改造前 6/39。
- 摘要 enrichment 统一原则：默认每刊最多 5 条、可 `enrich_abstract=false` 关闭、占位/空/与标题相同拒绝、失败不致命、只存文本不下载 PDF。
- 详见 `.local/abstract-reports/` 下各包报告。

### 3.3 `keywords` 的真实含义

这是最容易被误用的地方：

| 包 | `keywords` 模式 | 说明 |
|---|---|---|
| `cnki_cbpt`、`magetech_journals`、`qinyun_journals`、`rhzh_journals`、`sancai_journals` | 站内检索 | 向站点公开检索接口提交 query，能查过刊/多期 |
| `custom_toc_journals`、`founder_journals`、`paperonce_journals`、`oa_rss_journals`、`vsb_journals`、`hep_mirror_journals` | **只对当前期做本地关键词过滤** | 不是全刊检索；query 多词按 AND、aliases 按 OR，匹配标题/摘要/作者/DOI |
| `supplement_journals`、`flagship_journals` | API 检索 + 日期窗口 | OpenAlex/Crossref 的检索语义，不是官网检索 |

因此：

- 要“某刊近十年某主题”，国内只有前五个包能真正检索；后六个包只能筛当前期。
- 要“当期全量”，统一用 `latest_issue`，不要传关键词。
- 平台请求的 `query` 仍必须非空；`latest_issue` 模式忽略它。

---

## 4. 标准工作流

### 4.1 角色与批次

- **只读探测 agent**：只访问公开页面/接口，只输出证据 CSV/JSON；不写包、不写 DB、不建任务。
- **主线程**：合并证据、用生产 parser 逐本 live verify、决定写回、执行 apply/smoke/import、重算统计、更新文档。
- **WorkBuddy/外部代理**：可以批量做耗时探测，但交付只是“候选证据”；主线程必须逐本 live 验收，**不直接采信自检结论**。
- 批次大小：25–50 本/批；6–10 个只读 agent；避免单 agent 150 轮上限；失败批次拆小批补跑。

探测输出至少包含：

| 字段 | 用途 |
|---|---|
| `journal_name`、`core_levels`、`categories` | 身份与核心级别 |
| `official_url`、`current_url` | 官网与当期入口 |
| `items`、`first_title` | 证据强度和标题匹配 |
| `target_package`、`template_group` | 目标包/模板 |
| `data_source`、`data_source_detail`、`tags` | 来源标签 |
| `article_link_regex`、`link_base`、`relaxed_title_filter` | 按刊适配参数 |
| `notes` | 失败原因、噪声、特殊路径 |

### 4.2 七步闭环

#### 第 1 步：只读探测

- 每本刊只请求一次公开当期页/API，12–25 秒超时；记录 HTTP 状态、首条标题、条数、入口 URL。
- 判断“可读但 parser 没吃下”和“站点本身不可读”是两件事：前者进 `A-优先适配`，后者进 `B–F`。
- 产出：`probe-results-*`、`probe-verify-*.csv`、批次 JSON；不写包。

#### 第 2 步：主线程 live verify

- 用目标包的**生产 parser**逐本抓取；按包选择 custom/magetech/qinyun/rhzh/cnki_cbpt/hep/paperonce/sancai，失败回退 custom。
- 每本 1–2 次重试；12–25 秒；记录 `pass` / `warn` / `fail`。
- 通过门槛：`items > 0`，首条标题与证据一致（或能解释“页面已换期”），不是只有封面/目录/征稿。
- WorkBuddy 交付另要求 `current_items >= 2`、15 个字段齐全、证据 JSON 与 CSV 一致；PDF-only 不接受。
- 反例：B151 中 WorkBuddy 建议采信 94 本，live 实际只有 76 本可写回；差异集中在 host 白名单、SSL、SPA/JS/0 条、PDF/过采集。

#### 第 3 步：apply 写回

以 `scripts/apply_workbuddy_b151.py` 为模板：

1. 读计划 CSV；备份目标包的 `journals.json`、`manifest.json` 到 `.local/backups/`。
2. 按规范化刊名去重；用 `sha1(规范名|url|salt)[:16]` 生成稳定 `journal_key`。
3. 写入证据字段：`official_url`、`current_url`、`data_source`、`data_source_detail`、`source_group`、`status=verified_current_issue`、`verification_mode`、`verified_at`、`probe_items`、`probe_first_title`、`core_levels`、`categories`、`tags`。
4. 按需写入 `article_link_regex`、`link_base`、`relaxed_title_filter`；cnki 写 `url_signature=cbpt.cnki.net`；qinyun/rhzh 写 `url_signature=null`。
5. 升 `package_version`；把新 key 追加到 `parameters_schema.properties.journal_keys.default`；custom/qinyun 放宽 `maxItems`。
6. 输出 `*-applied-*.csv`，记录实际写入的刊、key、条数、首条标题、来源。

原则：**只加目录，不改 parser 逻辑**；parser 变更另开版本、另跑单测。

#### 第 4 步：smoke

- 用 `scripts/smoke_core_additions.py --applied <applied.csv> --per-package 4 --limit 5 --date YYYY-MM-DD` 真实抓取。
- 每包抽 3–5 本；`pass` = 有结果，`warn` = 有结果但有告警，`fail` = 0 条/异常；失败先重试一次，仍失败则保留 backlog。
- 同时跑包内单测和平台回归：
  - 包内：`python -m unittest discover -s crawler_packages/academic/<package>/tests -v`
  - 平台：`python -m unittest discover -s tests_platform -v`（或 `python -m pytest tests_platform -q -p no:cacheprovider`）
- 当前基线：B151 冒烟 18/18；C 组冒烟 9/9；平台 `151 passed + 72 subtests`（2026-11-24 记录）。

#### 第 5 步：import

- `python platform_main.py import crawler_packages/academic/<package>`
- 安装后的旧版本不直接改；导入前确认 `manifest.json` 的 `package_version` 已升。
- 多个包都改了，就逐个导入；导入后确认平台包的版本和结果表，不重建已有任务。
- 不在导入前跳过 smoke；不在导入后手工改结果表。

#### 第 6 步：coverage / backlog / source 重算

```bash
python scripts/build_core_coverage.py --date 2026-11-24
python scripts/build_adapter_backlog.py --date 2026-11-24
python scripts/summarize_core_sources.py   # 当前 DATE 常量写死，跑前确认日期
```

检查：

- `package_covered` / `catalog_only` / `ambiguous` / `new_candidate` 是否按预期变化；
- backlog 的 A–H 分类是否新增/减少；P1/P2 是否优先；
- `core-source-summary` 的包分布、学科分布、名单质量；
- `out-of-2377` 清单和学科分布是否需要同步重算；
- 新增的 `catalog_only` 是否有明确 blocked 原因，不能静默消失。

#### 第 7 步：docs / memory

- 在 `docs/current-progress.md` 顶部追加当日批次：包版本、新增数、冒烟/测试、覆盖/backlog、失败清单、证据路径。
- 更新 memory 的“当前状态”“日更实验”“国外方向”等条目；不写凭据、不写聊天内容。
- 失败和 held 要落 CSV/backlog，不只写在文档叙述里。

### 4.3 质量门槛

| 门槛 | 通过标准 | 不通过动作 |
|---|---|---|
| 有结果 | `items > 0`，且不是只有封面/目录/征稿 | 进 backlog，不硬加 |
| 标题匹配 | 首条标题与证据一致；换期导致差异要能解释 | warn 或重抓；不能解释则 fail |
| 批量交付 | WorkBuddy `current_items >= 2`、15 字段齐全、证据 JSON 一致 | held，补证据或重做 |
| 噪声 | 无“目录/封面/封底/征稿/启事/稿约/新闻/通知”等 | 加标题过滤或按刊 regex |
| 来源标签 | `data_source` + `tags` 正确，门户/镜像不标官网 | 打回重标 |
| 去重 | 包内无重复刊名/key；身份键稳定 | 不写回，先合并 |
| 版本 | `package_version` 升、`journal_keys.default` 含新 key | 不导入 |
| 测试 | 包内单测 + 平台回归通过；冒烟无 fail | 修复后重跑 |
| 边界 | 无登录/验证码/WAF/TLS 绕过；无 PDF 下载 | 停止，记 blocked |

补充：

- “items>0 但首条是封面”按拒绝处理；B151 的《高等学校化学学报》仅 1 条“封面和目次”，就是 rejected。
- “页面已换期”可接受为 `accepted_warn`（如江苏农业科学），但要在报告里写清。
- “0 条”不等于永久不可采；502/超时/维护要重试，连续多轮失败再降级。

### 4.4 失败处理与 backlog

`build_adapter_backlog.py` 的分类语义：

| 分类 | 含义 | 默认动作 | 优先级 |
|---|---|---|---|
| `G-已验证需扩包` | 已验证 items>0，只差加入现有包 | 直接扩包 | P1 |
| `A-优先适配` | agent 能读、现有 parser 未吃下 | custom 加 adapter 或专用 parser | P2 |
| `B-可重试` | 网络/代理临时故障 | 过几天重抓，不写代码 | P3 |
| `H-未复核` | agent 标记可读但缺 live verify | 补一次复核 | P3 |
| `C-需SPA适配` | 前端渲染/接口不明 | 有公开 API 再适配，否则暂缓 | P4 |
| `D-仅PDF/图片` | 只有整期 PDF/图片目录 | 跳过 | P5 |
| `E-登录/验证码/WAF` | 需要登录/验证码/WAF | 跳过 | P5 |
| `F-无官网/仅代理`、`F-其他失败` | 没有独立官网/只有聚合站；探测未找到公开当期 | 跳过 | P5 |

原则：

- **能读但 parser 没吃下** → A，不直接判死；**站点本身要登录/验证码/WAF** → E，不绕过。
- 失败记录必须带 URL、状态码、异常类型、探测时间；下次探测可复现。
- 不把“单次 0 条”写进永久 blocked；B151 的 31 held 就是待适配/待重试，不是已拒绝。

---

## 4.4 2026-11-25 适配补充（WorkBuddy accepted 写回）

- **SciEngine 新包**：`sciengine_journals` 1.0.1（14 本），读取 `selectArticlesInJournalOfVolumeAndIssue`；每次先调 `getJournalLatestVolumeAndIssue` 发现最新卷期，变了就动态拼文章 API，接口失败或最新期无有效文章回退固定快照；`follow_latest=false` 可关闭。DOI 作为身份，文章 URL `https://www.sciengine.com/doi/<doi>`，只存 PDF 链接。
- **founder 1.2.1**：`get_json` 支持 gzip（按 `Content-Encoding` 和 `1f 8b` 魔数）；标题/摘要去 HTML/JATS 标签；过滤封面、目录、专栏、投稿须知等噪声。解锁四川大学学报、新疆石油地质、测试技术学报、电焊机。
- **qinyun 1.9.1**：当期目录同时支持 `article_line` 与 `article_list`、连字符/下划线类名，`article_list` 外层 div（带 id）不再被内层 div 截断；标题过滤补编委会/投稿须知。解锁军事护理、南京信息工程大学学报等。
- **paperonce 1.1.1**：API 404/非 JSON 时回退旧版 paperopen HTML（GB2312、`div.item`、`oa/darticle.aspx?id=`），并过滤封面/目录。解锁现代检验医学杂志；断块油气田纠正 `url` 为 `dkyqt.paperonce.org`。
- **magetech 1.16.1**：支持 gzip 页面；`parse_generic_toc` 识别 `/CN/10.xxxx/` DOI 文章链接；当期页 `parse_search_result` 抛 `UNSUPPORTED_TEMPLATE` 时回退 generic，且 generic 条数明显更多时优先。解锁耐火材料、农学学报（改 http 绕开 hostname mismatch）。
- **rhzh 1.3.1**：HTML 目录过滤补投稿须知/编委会等。解锁现代应用物理（首条投稿须知被过滤）。
- **custom 3.10.1**：`read_page`/`fetch_text` 按 `meta charset` 兜底（GB2312 站点不再乱码）；标题过滤补团队介绍；JSON/pair 配置支持 8 本 NoteFirst `IssueId=0` 自动当期；新增 37 本，其中 16 本 JSON、5 本 pair、16 本 regex。
- **未完成**：custom 3 本嵌套 JSON/onclick URL 模板（哈工大社科版、矿山机械、浙大理工）、magetech 数据与计算（502）/石河子（TLS SECLEVEL=1）、rhzh 旧 ijournals/首页 article/id 模板（海军航空、现代大学教育、科普研究）；97 本 held 与 4 本仅放宽证书的期刊不写回。

## 5. 摘要补充策略

### 5.1 原则

1. **列表页有摘要优先**：能不 extra request 就不 extra request；founder、paperonce、sancai、magetech、oa_rss、qinyun 新版列表、rhzh JSON 都优先取列表字段。
2. **没有再做详情页/JSON enrichment**：只对缺摘要的条目补，已有摘要不重复抓。
3. **每刊上限**：默认每刊最多补 5 条（`abstract_enrich_limit=5`）；可按刊调低/调高；全局受平台 `limit` 约束。
4. **可关闭**：代码层已有 `enrich_abstract` 开关（默认 true）；任务层要能关。
5. **失败不致命**：详情页超时/解析失败只保留空摘要，不影响该刊其他条目，也不让整次运行失败。
6. **占位文本拒绝**：`摘要`、`Abstract`、`暂无`、`暂无摘要`、`点击查看`、`查看摘要`、`N/A`、`—`、纯 PDF/全文标签等不能当摘要；配合最小长度阈值，避免把导航文本写进 `abstract`。
7. **可计量**：按包/按刊统计 `abstract_len > 0` 的比例、补采成功/失败数，进入日报/周报。

### 5.2 已知入口

| 包 | 列表页/JSON 摘要 | 详情页/JSON 补采入口 | 选择器/字段 | 当前状态 |
|---|---|---|---|---|
| `qinyun_journals` | 新版 `article_line` 里 `div.abstract_body`；内嵌 `strArticleListJson` 当前未映射摘要 | 旧版 `view_abstract.aspx?file_no=...&flag=1`；新版文章页 | `<span id="Abstract">`、`div.abstract_body`；DOI `<span id="DOI">` | 已接入 `enrich_abstract`；样测抽样 5 刊中 2 刊首条有摘要（有结果 3 刊中 2 刊）、6/9 条 |
| `rhzh_journals` | HTML `div.search-abstract`；搜索 JSON `abstractinfoCn`（已映射）；`current-data` 的 `abstractinfoCn` 当前未映射 | `current-data` JSON 的文章对象；详情页 `/article/id/...` | `abstractinfoCn`/`abstractinfoEn`；详情 `div.article-abstract` | 已接入同名补采；样测 0/5 有结果刊、0/15 条，需修字段/选择器 |
| `custom_toc_journals` | JSON API 可能带摘要，但当前 `parse_json_toc` 只映射 title/url/authors/doi/year/issue | 文章 URL 常见：`/CN/abstract/abstract...shtml`、`/article/doi/...`、`/CN/10...`、`/CN/Y...`、`view_abstract.aspx`、`paperDigest.aspx`、`/client/paper/...` | 需按模板族配置；不能用一个通用选择器硬套 788 本 | **尚未实现**；建议先做高频模板族（Magtech 摘要页、view_abstract、paperDigest） |
| `cnki_cbpt` | 关键词检索的 `p.highText` 可能带摘要 | CBPT 详情、CNKI 详情/下载页 | CNKI 门户列表通常无摘要；详情常见登录/验证码 | 不把详情作为摘要来源；当前按缺口处理 |
| `magetech_journals` | HTML/JSON 列表字段 | 一般不需要 | `abstractCn`/`abstractEn`、HTML `j-abstract` | 列表已有；样本 3/4 首条 |
| `founder_journals` | rc-pub JSON `summary`/`enSummary` | 一般不需要 | `summary` | 列表已有；4/5 |
| `paperonce_journals` | `Abstract_Chinese`/`Abstract_English` | 一般不需要 | 同左 | 列表已有；3/3 |
| `sancai_journals` | `Abstract_Chinese`/`Abstract_English` | 一般不需要 | 同左 | 列表已有；2/2 |
| `oa_rss_journals` | RSS `description` | 一般不需要 | description | 已有；样本 2/3，注意可能只是导读不是完整摘要 |

### 5.3 工程实现约束

- **命名沿用**：`enrich_abstract`（bool，默认 true）、`abstract_enrich_limit`（int，默认 5）。qinyun/rhzh 的 `crawler.py` 已在 `latest_issue` 分支读取这两个参数；但当前 `manifest.json` 的 `parameters_schema` 还没有声明它们，**任务层暂时不能显式关闭/调整**。正式使用前必须补 schema，否则“可关闭/可调上限”只是代码能力。
- **请求成本**：只对缺摘要条目发请求；每刊最多 N 条；同一 opener/CookieJar；超时沿用包级 `timeout_seconds`；失败捕获异常后返回原 item。
- **占位过滤**：当前 qinyun/rhzh 的补采只判断 `not item.get("abstract")`，还没有统一占位词表；这是下一版的质检项，不能把“摘要/Abstract/暂无”当成功。
- **CNKI 边界**：CBPT 门户列表是主入口；详情/下载页遇到验证码/登录就停止，不绕过。若必须补 CNKI 摘要，只能接受“公开列表没有”的缺口，或用其他合法公开元数据源，不能抓详情页硬绕。
- **custom 边界**：788 本异构站点，详情补采要按模板族配置；先做“摘要页 URL 可识别且 HTML 结构稳定”的族，其余留空，不做模糊正文抽取。
- **指标**：`abstract_rate = 有摘要条数 / 有结果条数`；按包、按刊、按模板族统计；补采失败单独计数，不和“本来就没有摘要”混在一起。

### 5.4 实验结论

- 2026-11-24 每日实验：141 条中 **51 条有摘要（36.2%）**；按首条计，founder 4/5、paperonce 3/3、sancai 2/2、magetech 3/4、oa_rss 2/3、supplement 2/3、flagship 1/1；cnki/custom/hep/vsb/qinyun/rhzh 首条均为 0。
- qinyun/rhzh 补采后实验：qinyun 3 本有结果、6/9 条有摘要、首条 2/3 刊；rhzh 5 本有结果、0/15 条有摘要、首条 0/5 刊；重试后 rhzh 5/5 通过，说明 502 可重试。
- 结论：**摘要补采只能解决“详情页/JSON 确实有摘要”的模板**；CNKI 和 custom 的大部分站点不能靠通用补采解决，必须接受缺口或做模板级适配。

---

## 6. 日更语义

### 6.1 国内：当前期轮询 + 去重

国内包的 `latest_issue` 每次运行都重新抓“当前可见期”，不是按发布日期增量：

1. 读取 `current_url` 或默认当期入口（如 magetech `/CN/current`、qinyun 当前期、rhzh `/cn/article/current`）。
2. 解析整期文章；`external_id` 来自站内 ID/DOI/URL 哈希。
3. 平台按 `journal_key + external_id` 计算身份哈希：已存在则更新，内容哈希不变记 `unchanged`，变了记 `updated`；新条目记 `inserted`。
4. 同一批次内重复条目记 `batch_duplicates`，不重复入库。

由此得到：

- **“今天”= 当前可见期**，不是“今天发布”。样本里出现 2026 年第 5/10/11 期，不能证明都是当天发布。
- **换期才会大量新增**；同一期重复跑主要是 `unchanged`，成本低、幂等。
- **可能漏期**：如果两次轮询之间跳过了一期，而站点只展示当前期，就会漏。需要周/月回补，按过刊索引/期次页补抓（custom 的 `issue_link`、qinyun 旧版 `issue_list`、magetech 过刊页等）。
- **单次 0 条不等于停更**：502/维护/UNSUPPORTED 很常见；记录 warning，下一次继续轮询，连续失败再降级。
- **噪声**：目录/封面/封底/征稿/启事/稿约/新闻/通知要在解析层过滤；qinyun 的“目录、封面、封底”就是样本中的真实噪声。

### 6.2 国外：发布日期窗口 + DOI 去重

国外不能用“当前期”语义，应该用发布日期窗口：

- `lookback_days` 默认 30 天；任务 `time_range.from/to` 优先；每日任务建议窗口 1–7 天，周补 30 天，月审计 90 天。
- OpenAlex 用 `from_publication_date`/`to_publication_date`；Crossref 用 `from-pub-date`/`until-pub-date`；PubMed/arXiv 用各自日期参数。
- 每天窗口向前重叠 1–3 天，抵消索引滞后/重复；平台按 DOI 去重，内容哈希判更新。
- OpenAlex 有索引滞后：2026-11-24 的 7 天样本最新到 11-17~20，没有 11-24 当天记录；不能把“当天 0 条”判成源故障。
- Crossref 的 `published`/`published-online`/`issued` 可能不一致；统一取一个 `published_at` 口径并记录来源，不能混用。

### 6.3 对比

| 维度 | 国内包 | 国外包 |
|---|---|---|
| 时间语义 | 当前期，不是发布日期 | 发布日期窗口 |
| 去重键 | `journal_key + external_id` | `doi` |
| 新增判断 | 换期/新文章 | 日期窗口内新 DOI |
| 回补 | 过刊索引/期次页（未做全历史） | 7/30/90 天窗口重跑 |
| 摘要 | 列表优先，详情/JSON 补采 | API 字段优先，缺失可补 |
| PDF | 只存链接，仅 magetech 部分模板 | 只存链接，不下载 |
| 失败 | 502/UNSUPPORTED/0 条，重试 | 429/5xx/滞后，退避/换源 |

### 6.4 重试、噪声与回补

- **平台重试**：平台对可重试的执行错误最多 3 次；包内单刊 502/0 条只写 `warnings`，不会自动按刊重跑，需要下一次轮询或人工重跑失败刊。
- **失败台账**：每批记录 `journal_name`、URL、状态码、异常、首次/最近失败时间；连续 3 次失败再降级为 blocked/backlog。
- **噪声过滤**：标题黑名单（目录/封面/封底/征稿/启事/稿约/新闻/通知/编委会）、导航标签（首页/上一页/下一页/更多/过刊/登录）、`[摘要]`/`PDF`/`HTML Full Text` 等；按刊 `relaxed_title_filter` 只在确有需要时开。
- **回补策略**：国内每周扫一次失败刊和过刊索引，每月按核心名单重算覆盖；国外每日窗口 + 每周 30 天 + 每月 90 天；回补结果同样走身份去重，不重复入库。

---

## 7. 给国外期刊的复用方式

### 7.1 JCR/Scopus 只做 watchlist

- JCR/Scopus 用于**选刊、分区、学科和 ISSN 对照**，不作为日更文章源；它们的文章级检索/导出受订阅和许可限制，不能默认有 API 权限。
- watchlist 落到期刊维表：`journal_key`、刊名、ISSN/eISSN、出版社、学科、分区、OA 状态、官网、可用源适配器、API 权限、备注。
- 维表匹配沿用国内的严格口径：**ISSN/eISSN 优先，其次完全同名**；base name/fuzzy 只进 `ambiguous`，不计覆盖。
- JCR/Scopus 的许可和费用单独记录；不在仓库里存订阅内容。

### 7.2 源适配器

| 源 | 角色 | 主要字段 | 成本/限制 | 注意 |
|---|---|---|---|---|
| 出版社 API | 最高优先级（有权限时） | 标题、作者、摘要、DOI、日期、卷期页、License | 按机构订阅/API key；有配额和条款 | 只取元数据，不取 PDF 全文；按出版社拆包 |
| PubMed E-utilities | 生物医学主源 | PMID、DOI、标题、作者、摘要、日期、期刊 | 免费；有速率限制 | 结构化摘要要转纯文本；无 DOI 时用 PMID |
| Crossref | 广义 DOI 元数据 | DOI、标题、作者、摘要、日期、卷期页、License | 免费；礼貌池 `mailto` | 摘要常缺失；日期类型多，要统一 |
| OpenAlex | 广义发现/补全 | DOI、标题、作者、机构、摘要倒排、OA、被引、日期 | 免费额度/礼貌池；有索引滞后 | 摘要要还原倒排索引；不能当“当天发布”保证 |
| arXiv | 预印本补充 | arXiv ID、标题、作者、摘要、日期、分类 | 免费；Atom API | 不是同行评审版本；无 DOI 时单独身份键 |
| 官网 RSS | 当期目次补充 | 标题、链接、作者、摘要、期次、日期 | 免费；只最新一期 | 复用 oa_rss 模式；description 可能只是导读 |

建议优先级：**出版社 API/官网 RSS > PubMed（生物医学）> Crossref > OpenAlex > arXiv（预印本）**；同一刊多源时保留 `source` 字段，不覆盖原始记录。

### 7.3 每日日期窗口 + DOI 去重

- 以 `published_at` 为时间轴，不用“最新一期”替代“今天”。
- 每日窗口建议 1–7 天，向前重叠 1–3 天；任务 `time_range` 可覆盖 `lookback_days`。
- 身份键用 DOI；平台按 DOI 去重，内容哈希判更新。
- **无 DOI 的源要单独建包**：如 arXiv 用 `arxiv:<id>`、PubMed 无 DOI 用 `pmid:<id>`；不要改现有包的 `identity_fields`（平台升级禁止改身份键）。
- 记录 `published_at` 的来源（online/print/issued），缺失时留空并告警，不用抓取时间冒充发布日期。

### 7.4 摘要与字段差异

| 源 | 摘要形态 | 处理 |
|---|---|---|
| OpenAlex | `abstract_inverted_index` | 按位置还原为纯文本；缺失则留空 |
| Crossref | JATS XML/HTML | 去标签、去 `Abstract` 前缀；可能没有 |
| PubMed | 结构化摘要（BACKGROUND/METHODS 等） | 保留段落标签的纯文本；不要只取第一段 |
| arXiv | 纯文本摘要 | 直接使用；标注预印本 |
| RSS | description，可能是导读/HTML | 去标签；标注 `abstract_source=rss`；不保证完整 |
| 出版社 API | 取决于权限和字段 | 有则用；没有不补全文 |

统一要求：

- `abstract` 存纯文本；保留 `abstract_source`（`list`/`detail`/`openalex`/`crossref`/`pubmed`/`arxiv`/`rss`）。
- 占位文本拒绝；最小长度按语言配置。
- 作者可能是数组/字符串/分号分隔；统一成可检索文本，但保留原始格式字段（如 `authors_raw`）以便回溯。
- 机构、通讯作者、ORCID、License、OA、被引等字段按源能力保留；没有就空，不推断。
- 撤稿/勘误/新闻/评论要按来源规则过滤；flagship 已排除 Nature `d41586` 新闻和明显勘误/撤稿标题，可作为参考。

### 7.5 源覆盖审计

建议每周/每月生成国外源覆盖报告，复用国内的“覆盖 + backlog”思路：

| 指标 | 说明 |
|---|---|
| watchlist 总数 | JCR/Scopus 选出的目标刊 |
| `covered` | 至少一个源能稳定返回近期文章 |
| `partial` | 有文章但缺摘要/DOI/日期等关键字段 |
| `no_source` | 没有可用公开源/API |
| `blocked` | 付费墙/登录/许可不允许 |
| `ambiguous` | ISSN/刊名不唯一 |
| 每刊近期条数 | 近 7/30 天文章数，判断源是否真的在更新 |
| 字段完整率 | 摘要、DOI、日期、作者、机构 |
| 源失败率/延迟 | 429/5xx、索引滞后、平均延迟 |
| 成本 | 请求数、API 配额、付费源费用 |

原则：

- 覆盖率按“刊 × 源”统计，不按“平台总刊数”冒充。
- 一个刊可以多源；主源失败时按优先级降级，但保留 `source` 和失败记录。
- 没有源的刊进 backlog，不硬凑；付费源只给“必须刊”，先算成本。
- 报告落 `journal_catalog/foreign/`（未来目录），字段和国内 coverage 保持同构，便于复用脚本。

### 7.6 不要直接复用的部分

- 不要把国内 `latest_issue` 直接搬到国外；国外必须用发布日期窗口。
- 不要复用 CNKI/CBPT、PaperOnce、方正、三才、VSB、HEP 这些国内平台适配器；它们只适用于对应国内站点。
- 不要按单刊建包；国外也按“源/出版社/模板”分包。
- 不要下载 PDF 或抓全文；国外同样只存元数据和链接。
- 不要把 JCR/Scopus 数据当可自由分发的元数据；许可先核验。

---

## 8. 当前数字与实验结论

> 以下均来自 2026-11-24 的文件，不是实时复核；数字冲突时以对应 CSV/MD 为准。

### 8.1 核心覆盖

| 指标 | 数值 |
|---|---:|
| 核心名单并集 | 3461 |
| 已入包 | **2065（59.7%）** |
| 仅在 2377 目录 | 169 |
| 版本歧义 | 14 |
| 新增候选 | 1213 |
| 中文核心覆盖 | 1725 / 3117 |
| 英文核心覆盖 | 340 / 344 |
| 2377 目录覆盖 | 1856 / 2377（78.1%） |
| 平台在册期刊 | **3028**（按各包 `journals.json` 合计；flagship 4 刊为代码内置，单列） |

包内核心刊数（2026-11-24 覆盖报告）：custom 575、cnki 390、magetech 344、supplement 295、rhzh 226、qinyun 116、founder 54、paperonce 41、oa_rss 11、vsb 8、hep 5。

### 8.2 Adapter backlog

| 分类 | 数量 |
|---|---:|
| A-优先适配 | 12 |
| B-可重试 | 74 |
| C-需SPA适配 | 138 |
| D-仅PDF/图片 | 74 |
| E-登录/验证码/WAF | 571 |
| F-无官网/仅代理 + 其他失败 | 357（116 + 241） |
| G-已验证需扩包 | 1 |
| **合计** | **1227** |

优先级：P1 1、P2 12、P3 74、P4 138、P5 1002。策略是先做 G/A/B，C/D/E/F 默认暂缓或跳过；C 组和 B151 held 都按这个口径进 backlog，不硬加。

### 8.3 每日实验（每包随机 5 本）

- 13 个学术包、61 本刊（sancai 仅 2、flagship 仅 4）；**141 条文章元数据、48 本有结果、13 本失败**。
- 有结果的条目 **标题/文章 URL 100%**；全部 141 条中：作者 72、摘要 51、DOI 49、PDF 链接 8（仅 magetech）、`published_at` 9（仅 supplement/flagship）。
- 按包 pass：cnki 5/5、custom 5/5、founder 5/5、hep 5/5、vsb 5/5、magetech 4/5、rhzh 4/5、oa_rss 3/5、paperonce 3/5、qinyun 3/5、supplement 3/5、sancai 2/2、flagship 1/4。
- 13 本失败以 **502 / UNSUPPORTED / 0 items** 为主；失败可重现，说明日更必须带重试和失败记录。
- 噪声：qinyun《中国临床新医学》首条为“2026年 第10期 目录、封面、封底”；需要在解析层过滤。
- “今天”口径：国内包是当前期（2026 年第 5/10/11 期等），不是当天发布；supplement 的 OpenAlex 近 7 天最新到 11-17~20，没有 11-24 当天记录；flagship 的 AI 关键词只命中 1 条 Science。

### 8.4 摘要与补采

| 口径 | 结果 |
|---|---|
| 全部条目摘要 | 51 / 141（36.2%） |
| 首条有摘要的包 | founder 4/5、paperonce 3/3、sancai 2/2、magetech 3/4、oa_rss 2/3、supplement 2/3、flagship 1/1 |
| 首条无摘要的包 | cnki 0/5、custom 0/5、hep 0/5、vsb 0/5、qinyun 0/3、rhzh 0/4 |
| qinyun/rhzh 补采后 | qinyun 3 本通过、6/9 条有摘要、首条 2/3 刊；rhzh 5 本通过、0/15 条、首条 0/5 刊 |

qinyun 补采有效的两本：盐城工学院学报（自然科学版）339 字、中国环境管理 241 字；rhzh 5 本通过但摘要仍为空，说明字段/选择器未命中，不是“没有摘要”。

### 8.5 WorkBuddy B151 验收

- 输入 151 本、8 个批次、15 个字段，齐全、无重复、证据 JSON 一致。
- WorkBuddy 自检 `ok` 108 本；主线程 live 复核后：**接受 76 本（70.4%）、held 31 本、rejected 1 本**；其余 43 本 blocked/fail 保持原结论。
- 接受分布：custom 55、magetech 10、qinyun 5、cnki 3、rhzh 2、hep 1。
- 拒绝：高等学校化学学报（仅 1 条“封面和目次”，非真实文章）。
- 31 本 held 集中在 SSL 证书 5、rhzh host 白名单 4、magetech host 白名单 8、qinyun host 白名单 2、其余 12（SPA/PDF/0 条/过采集等）；全部进 backlog，不写回。
- 冒烟 18/18；平台 `151 passed + 72 subtests`。
- C 组首批：计划 34 本，live 25 pass（custom 20、paperonce 4、magetech 1）、9 fail；说明“agent 建议”和“可写回”之间必须有一道 live 验收。

### 8.6 结论

1. **元数据+链接成立**：有结果的条目都有标题和文章 URL；没有下载 PDF。
2. **字段差异是常态**：摘要/作者/DOI 随包差异大，不能用一个“有摘要”假设覆盖全部包。
3. **国内日更是当前期轮询**：适合追新期，不适合证明“当天发布”；要严格日更必须加发布日期窗口或在线优先。
4. **批量补录必须 live 复核**：WorkBuddy 94 本建议 → 76 本可写回；单次 0 条、502、封面条目都不能直接采信。
5. **失败要进 backlog**：1227 本已探测未入包，A/B/G 可做，C/D/E/F 暂缓；不硬加、不绕过。

---

## 9. 未解决问题

| # | 问题 | 现状/证据 | 影响 | 下一步 | 不做 |
|---|---|---|---|---|---|
| 1 | **CNKI 摘要** | 当期样本 0/15；关键词检索的 `highText` 可能带摘要，但不稳定；CNKI 无 DOI；详情/下载常见登录/验证码 | CNKI 390 本核心刊的摘要覆盖率低 | 先用 CBPT 公开列表；评估“公开摘要字段是否足够”；不足则接受缺口或换合法元数据源 | 不绕验证码、不抓详情/下载页 |
| 2 | **custom 详情页** | 788 本异构站点；当前只保证标题+链接，JSON 类才有作者/DOI；摘要 0/5；`parse_json_toc` 未映射 abstract | custom 是最大包（575 本核心刊），摘要缺口最大 | 按模板族做详情补采：Magtech 摘要页、`view_abstract.aspx`、`paperDigest.aspx`、`/client/paper/`；每族先样测 | 不做通用正文抽取、不抓 PDF |
| 3 | **qinyun/rhzh 模板** | qinyun 补采首条 2/3 有结果刊；rhzh `current-data` 含 `abstractinfoCn` 但未映射，详情 `div.article-abstract` 未命中；参数字段未进 manifest | 两包共 475 本目录，摘要能力不稳定 | 先修 rhzh 字段映射；再按模板复核 qinyun/rhzh 详情选择器；补 manifest `enrich_abstract`/`abstract_enrich_limit`；加占位过滤 | 不假设所有模板同一选择器 |
| 4 | **国内日期字段** | 国内包只有 `year`/`issue`，没有统一 `published_at`；issue 常是“2026年第5期”或空 | 无法按真实发布日期排序/去重；“今天”只能是当前期 | 有公开在线优先/发布日期就补；没有就保留 issue + 期顺序；报告中明确“非发布日期” | 不用抓取时间冒充发布日期 |
| 5 | **国外覆盖率/成本** | 尚无 PubMed/arXiv 适配器；OpenAlex 有滞后；JCR/Scopus 许可、出版社 API 费用/配额未核验；无国外源覆盖报告 | 不能承诺国外日更覆盖率；付费源可能超预算 | 先做 watchlist + OpenAlex/Crossref 日期窗口 MVP；再补 PubMed/arXiv/RSS；每周源覆盖审计；付费源只给必须刊 | 不默认 JCR/Scopus 有文章 API；不先买大包 |

其他已知债务：

- 853 条历史目录缺 `data_source`（见 1.3）；新批次必须补齐，旧批次不追溯改写。
- `summarize_core_sources.py` 的日期是常量，跑之前要确认；后续可参数化。
- 平台总刊 3028 不含 flagship 的 4 刊；统计口径要写清楚，避免和“核心覆盖 2065”混用。

---

## 10. 证据索引

- 进度与批次：`docs/current-progress.md`（2026-11-24 各节）
- 核心覆盖：`journal_catalog/core/core-coverage-2026-11-24.md` / `.csv`
- 核心来源统计：`journal_catalog/core/core-source-summary-2026-11-24.md` / `.json`
- 适配 backlog：`journal_catalog/core/core-adapter-backlog-2026-11-24.md` / `.csv`
- 每日实验：`journal_catalog/core/daily-sample-summary-2026-11-24.md`、`daily-sample-2026-11-24.csv`、`daily-sample-items-2026-11-24.csv`
- qinyun/rhzh 补采后实验：`journal_catalog/core/daily-sample-qy-rh-after-2026-11-24.csv`、`daily-sample-qy-rh-after-2026-11-24-items.csv`
- WorkBuddy B151：`journal_catalog/core/workbuddy/b-acceptance-summary-2026-11-24.md`、`b-acceptance-2026-11-24.csv`、`b-applied-2026-11-24.csv`
- 2377 维表：`journal_catalog/journals.json`
- 包源码：`crawler_packages/academic/<package>/`（`README.md`、`journals.json`、`manifest.json`、`crawler.py`）
- 脚本：`scripts/build_core_coverage.py`、`build_adapter_backlog.py`、`summarize_core_sources.py`、`apply_workbuddy_b151.py`、`smoke_core_additions.py`、`experiment_daily_sample.py`
- 平台去重/入库：`crawler_platform/storage.py`、`crawler_platform/protocol.py`（`identity_digest`、`content_digest`）
