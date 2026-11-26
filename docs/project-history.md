# IDIW 项目全史与路线（2026-11-26）

> 用途：给新对话/新接手者一页看懂“这个项目为什么做成现在这样”。逐次运行明细仍以 [current-progress.md](current-progress.md) 为准；本文件只保留主线、决策与当前路线，避免整份阅读四份大导出。

## 0. 一句话定位

IDIW 是武汉大学信管研一“低空技术与经济”毕设的数据底座：**先做全学科期刊监测（国内核心 + 国外 JCR Q1），再把低空相关性筛选、结构化抽取、计量与证据核查做成 Agent，专利侧后接**。爬虫阶段只负责“广覆盖、可更新、可追溯的元数据 + 链接”，不按低空或核心筛掉候选。

## 1. 术语与关键数字

| 名词 | 含义 |
|---|---|
| 2377 | 万方 10,105 本中“能找到官网 URL”的候选目录，32 组；不是核心名单。 |
| 3461 | 核心名单四并集：北大核心 2023、CSSCI 来源+扩展 2023–2024、CSTPCD 2024、CSCD 2023–2024，按规范化刊名去重。 |
| 覆盖 | 只认 ISSN/CN/完全同名；基础名/模糊匹配只标 ambiguous，不计覆盖。2377 覆盖与核心覆盖分开统计。 |
| 包 | 按平台/模板划分（CNKI、玛格泰克、勤云、仁和、方正、VSB、三才等），不按学科；一个 monitor 可同时选多个包。 |
| journal_key | 包内期刊稳定键；国内身份 `journal_key + external_id`，国外/supplement 身份 DOI；跨包同 DOI 各存一条。 |
| pkg_data_xxxx | 每个包独立结果表；国外 Q1 为 `pkg_data_000020`。 |
| P1/P2/P3/P4 | 国内可补清单分层：P1 196 全核心可复核；P2 25 非核心；P3 100 仅知网导航（16 核心）；P4 764 阻断/失败/仅 PDF。 |
| backlog | 已探测但尚未入包的分类账：A 优先、B 可重试、C SPA、D 仅 PDF、E 登录/验证码/WAF、F 其他/无官网、G 已验证需扩包。 |
| bulk_window | 国外 Q1 批量模式：100 ISSN/次 OR 查 OpenAlex、cursor 分页、DOI 去重、映射回期刊。 |

当前核心数字：国内平台 **3185** 本；核心 **2225/3461（64.3%）**；backlog **1123**（A11/B46/C69/D73/E566/F357/G1）；仅在目录 113、歧义 12、新增候选 1111。国外 Q1 **5,238** 本 / **53,138** 条。

## 2. 时间线（五个阶段）

| 阶段 | 时间 | 关键动作 | 结果 |
|---|---|---|---|
| A. 部署与摸底 | 2026-11-23/24 | 部署 GitHub IDIW 到 `D:\IDIW`；关闭开机自启；解释 838/2377；确定研究模式与来源标注 | 6 个期刊包、838 个可选刊（834 中文 + 4 旗舰）；2377 中 831 已覆盖、1546 只有目录；3 个目录外中文刊 |
| B. 核心补刊 | 2026-11-21–24 | 建立 3461 核心口径；多 agent 只读探测；A/B/C/G 组按供应商补；WorkBuddy 分担低技术任务 | 核心覆盖 975 → 2052；WorkBuddy B151 76 本写回、C 组与 84 accepted 陆续写回；平台总刊 1939 → 3017 |
| C. 国内收口与国外准备 | 2026-11-24/25 | 每日去重实验；翻页与详情摘要修复；WorkBuddy 验收；全量测试暂停；明确国外“每天最新文章+链接、不存 PDF” | 摘要同批 59.8%→95.8%；平台 3113；run14/15/17 无协议错误；开始 JCR/Scopus 源审计 |
| D. 国外 Q1 | 2026-11-25/26 | JCR 2025 Q1 5,279/日更 5,238；OpenAlex 主源 + Crossref 兜底；bulk_window；500 试点 → 全量 11 批 | 5,238 本、53,138 条、DOI 100%、摘要 67.2%；500/全量 CSV+HTML 报告完成 |
| E. 国内 P1 回头补 | 2026-11-26 | P1 Top20 → 21–80 → 81–196 → 待定 31 复测 → backlog A/B 直连重试；生产 parser live 复核 + smoke | P1 累计写回 **64 本**；backlog 直连补 **8 本**（心理/南京审计/棉纺织/植物遗传/海军航空/现代制造/数学进展/遥测遥控）；核心 2225/3461；平台 3185 |

## 3. 四份对话导出对应

| 导出 | 大致会话 | 主题 | 关键转折 |
|---|---|---|---|
| `部署_IDIW_项目_2026-11-24_01-43.md` | 0d0248ee（推测） | 部署、838/2377、平台功能、研究模式、核心口径 | “不要只挑低空/核心，全部过一遍”；“平台统一每日更新即可”；“不要留自动任务”；来源必须标注 |
| `对话2_2026-11-25_01-10.md` | 9f023994 | 核心补刊、多 agent、WorkBuddy、A34/G6/B151 | 包按平台/模板；单刊不建包；“加包前多测几本”；WorkBuddy 只做证据，主线程验收 |
| `对话3_2026-11-25_01-10.md` | 12f6e69f（推测） | C 组、WorkBuddy 验收、国内收尾、国外需求、开源调研、全量测试暂停 | 国外重点是“每天拿最新文章信息+链接”，不是爬刊名/存 PDF；2775 本全量测试因耗时暂停 |
| `对话4_2026-11-26_12-56.md` | 031d9961（当前接手前） | 每日去重、翻页/摘要、Q1 watchlist/审计/bulk/全量报告、P1 196 | 全学科 Q1；免费 key；500→全量；10+ agent 并行；P1 196 补刊与 6 个已有包澄清 |

会话 ID 仅作辅助；以文件与 `current-progress.md` 的时间线为准。

## 4. 关键决策记录

| 决策 | 为什么 | 后果 |
|---|---|---|
| 全学科，不按低空筛选 | 低空相关性应由后续 Agent 按文章内容判断；目录阶段预筛会缩小覆盖 | 2377/3461 全量过一遍；低空标签后置 |
| 核心只认四名单并集 3461 | 2377 是万方 URL 候选，不是核心；知网/AMI/扩展版不能冒充核心 | 覆盖只认 ISSN/CN/完全同名；核心与 2377 分开统计 |
| 包按平台/模板，不按学科 | 同一平台解析器可复用；学科只是 tags | custom/qinyun/magetech/rhzh/vsb/cnki/sancai 等包；单刊不建包 |
| 不合并总包 | 用户先提总包后撤回；“先补完再分类” | 当前保持多包；monitor 可跨包选刊 |
| 只存元数据+链接，不下载 PDF | 用户存储与版权边界；筛选后再自行下载 | 标题/作者/摘要/DOI/年卷期页/文章 URL/可选 PDF 链接 |
| 不登录、不绕验证码/WAF | 合规与账号安全；校园订阅≠官方 API 授权 | blocked 留 backlog；正式授权 API 才加适配器 |
| 多 agent 只读探测 + 主线程 live 复核 | agent 的 ok 会混入新闻/PDF/检索页/停更；单 agent 大批次会撞轮次上限 | 10+ agent 并行；抓取最多 2 Worker；只有生产 parser items>0 才写回 |
| WorkBuddy 分担低技术耗时任务 | 积分充足、任务可拆分 | 统一桌面合集；主 agent 逐 Task live 验收，不直接采信 |
| 国内当期目次，国外 30 天窗口 | 国内“今天”是当前期快照；国外以 publication_date 补索引滞后 | 国内 latest_issue；国外 bulk_window + DOI 去重 |
| 每日去重用内容哈希 | 重复抓取不应算“更新”；只有内容变化才更新 last_changed | sys_first_seen/last_seen/last_changed/change_count |
| 研究模式、不建 daily | 用户研究用途，不希望后台常驻/开机自启 | 便携 MariaDB + API；Worker/Scheduler 不常驻；任务默认 manual |
| 免费源优先 | 用户成本敏感；OpenAlex/Crossref/PubMed/RSS 足够 | OpenAlex 免费 key；付费出版社 API 只在必须时提 |

## 5. 架构与数据模型

- 平台：插件化工具包 → manifest/journals.json/crawler.py → 导入时建独立环境与结果表 → monitor/run/package_run → Worker 执行 → 去重入库 → API/网页查询。
- 国内包（active）：`cnki_cbpt` 1.12.7（846）、`custom_toc_journals` 3.10.7（849）、`magetech_journals` 1.16.9（417）、`qinyun_journals` 1.9.5（173）、`rhzh_journals` 1.3.7（328）、`vsb_journals` 1.2.5（14）、`sancai_journals` 1.0.4（3）、`founder_journals` 1.2.2（101）、`paperonce_journals` 1.1.3（78）、`sciengine_journals` 1.0.1（14）、`oa_rss_journals` 1.1.1（18）、`hep_mirror_journals` 1.1.1（6）、`supplement_journals` 1.1.2（338）。
- 国外：`foreign_q1_journals` 1.1.1（5,238），`bulk_window`，OpenAlex 主源/Crossref 兜底，30 天/20 刊，DOI 身份。
- 结果表：每包一张 `pkg_data_xxxx`；去重身份国内 `journal_key+external_id`、国外/supplement DOI；`sys_first_seen_at`/`sys_last_seen_at`/`sys_last_changed_at`/`sys_change_count`。
- 解析家族：custom_toc（HTML/JSON/pair/onclick/issue/分页）、magetech（current/issue/STAE/abstract 路由）、qinyun、rhzh（article-list/resName/current-data）、vsb、cnki（WK*/portal/paperDigest/分页）、sancai API、founder rc-pub、paperonce、sciengine、oa_rss、hep mirror、supplement/OpenAlex/Crossref。
- 质量链路：probe CSV → 主线程 live parser verify → 按包 apply（升 patch、同步 maxItems/default）→ 包 pytest → tests_platform → import → manual smoke → 归档 → 重算 coverage/backlog/out_of_catalog。

## 6. 当前状态（2026-11-26 快照）

- 国内平台 **3185**；核心 **2225/3461（64.3%）**；backlog **1123**（E 566 为最大类）；P1 1–196 已全部探测，累计写回 **64 本**；backlog A/B 直连重试另补 **8 本**。
- batch3 复测后仍未写回 27：文本目次 7、停更 8、PDF-only 4、SPA 3、其它 5（心血管网络版/光通信首页混多期、食品 2026 仅 1 期、中华医院感染仅首发、中国性科学空目录）。backlog 直连重试 56 本中 48 本未写回（26 待定 + 22 不可写回）。
- 国外 Q1：5,238 本、53,138 条（唯一 DOI 53,136）、4,549 本有结果/689 本 0 条、DOI 100%、摘要 35,685（67.2%）；500 与全量报告均已生成。
- 测试：平台 **181 passed + 81 subtests**；包单测 custom47/qinyun36/magetech35/cnki32/rhzh35/vsb19/sancai3/paperonce15（随包版本可能变化，以实际 pytest 为准）。
- 环境：`研究模式-启动.bat` 启 API+便携 MariaDB；Worker/Scheduler 未常驻；本轮 monitor 60/61/62/63 均已归档。
- 工作区：大量包升级与平台改动**尚未提交**；按用户要求没有擅自 commit/push。

## 7. 未完成与风险

- 国内公开源已接近上限：剩余主要是登录/验证码/WAF、SPA、仅 PDF、纯文本目次、停更；继续只有文本目次适配或 P2/P3（非核心）两条路，核心覆盖收益有限。
- 低空 Agent 与专利侧尚未开始；专利计划：IPC `B64U/B64C/B64D/B64F/G08G5` + 公开日期游标，或独立上游。
- OpenAlex key 曾在聊天出现，应轮换；只放本地 `.env` 的 `CRAWLER_SECRET_OPENALEX_API_KEY`，不打印/不提交。
- 工作区未提交；旧文件 `journal_catalog/journals.json` 中兰大仍标 qinyun（legacy，需同步归属）。
- 一些 0 条/partial 属站点级（502/超时/摘要补采为空），不能据此判平台故障；重试要单刊/单包，避免整批重跑。
- 抽样结论必须标样本比例/每刊上限/selection/edition 偏差，不能把样本当全量。

## 8. 下一步路线（建议）

1. **国内收口**：冻结 P1 公开源；把 27 本未写回的处置写清（文本目次/TLS/SPA/停更/PDF），只在有明确适配收益时做文本目次或 TLS/SPA 适配。
2. **转毕设主线**：低空期刊/专利监测与深度分析 Agent——先定义低空产业链×技术栈本体、宽召回→语义精排、P-M-R-L+TRL、专利 T-E-S、论文-专利耦合与证据核查。
3. **专利侧**：按 IPC + 公开日期游标做独立上游；先只存专利元数据+链接。
4. **收尾工程**：轮换 OpenAlex key；整理未提交工作区（需用户确认后才 commit）；保持 manual/研究模式，不建 daily/Scheduler。

## 9. 信息源与读法

- 逐次运行明细：[docs/current-progress.md](current-progress.md)（顶部为最新）。
- 项目记忆：`C:\Users\86139\.qoder\projects\D--IDIW\memory\`（project-idiw-state、project-idiw-thesis、project-idiw-foreign-journals、reference-platform-testing、reference-domestic-addable-2026-11-26 等）。
- 用户偏好：`C:\Users\86139\.qoder\memory\`（研究部署、证据链、多 agent、成本、代理、交付等）。
- 大导出：桌面四份 md；不要整份读，按关键词/末尾片段检索。
- 关键产物：`journal_catalog/core/domestic-p1-*.csv/md`、`domestic-p1-batch2-*.csv/md`、`domestic-p1-batch3-*.csv/md`、`domestic-p1-recheck-*.csv/md`、`journal_catalog/foreign/foreign_q1_full_2026-11-26_*`。
