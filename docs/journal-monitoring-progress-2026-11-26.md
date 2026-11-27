> 本文件为伙伴分支 680f8bb 的进度归档，保留原始运行编号与验收陈述。部署、调度器状态、测试数字及旧待办仅指该分支当时环境；合并后的当前状态以 current-progress.md 为准。

# 当前进度与待办

更新时间：2026-11-26（北京时间）。

> 项目全史、四份对话对应、关键决策与当前路线见 [project-history.md](project-history.md)。本文件保留逐次运行明细。

## 2026-11-26 核心 backlog A/B 直连重试与写回

- 对 backlog 的 A/B 类 56 本（B 54 + A 2）做**直连重试**（禁代理，每本 ≤4 请求）：**写回 8 / 待定 26 / 不可写回 22**；证据 `journal_catalog/core/domestic-core-retry-evidence-2026-11-26.csv/md`。
- 写回 8 本（生产 parser live 复核后）：
  - custom_toc **3.10.7（849）**：南京审计大学学报（10）、海军航空大学学报（15）、数学进展（16，CCJ API）；
  - magetech **1.16.9（417）**：心理学报（14）、现代制造工程（19，bjast 新域）；
  - paperonce **1.1.3（78）**：棉纺织技术（16）；
  - qinyun **1.9.5（173）**：植物遗传资源学报（16，www 主机 + 期次页）；
  - rhzh **1.3.7（328）**：遥测遥控（17，spacejournal 新址）。
- 写回清单：`journal_catalog/core/domestic-core-retry-applied-2026-11-26.csv`。
- 关键发现：之前一批 502 是代理/链路假象；直连后恢复 8 本。其余 48 本仍是停更（手术学 2018、流体机械 2023、长江流域 2024 等）、域名失效（世界历史/国外文学/电网技术/遥测旧域等）、证书链/TLS 栈、JS 挑战、纯文本/PDF、或无当期。
- 测试：custom 47、magetech 35、paperonce 15、qinyun 36、rhzh 35；平台 **181 passed + 81 subtests**。
- smoke run 53（monitor 64，manual，已归档）：5 包 **28 条入库、0 rejected**，8 本全部有数据。
- 覆盖重算：平台国内总刊 **3185**；核心 **2225/3461（64.3%）**；仅在目录 113、歧义 12、新增候选 1111；backlog **1123**（A11/B46/C69/D73/E566/F357/G1）。
- P1 1–196 累计写回仍为 **64 本**；本轮 8 本属于 backlog B/A 类，不计入 P1 数字。

## 2026-11-26 P1 待定 31 本复测与补写回

- 对 batch3 的 31 本待定项按原因分 5 组只读复测：文本目次 7、SPA/JS 6、停更 8、PDF-only 4、拦截/超时 6；证据 `.local/domestic-p1-recheck/agent01..05.csv/md`。
- **新写回 4 本**：
  - custom_toc **3.10.6（846）**：大数据（方正 Nuxt SSR 当期 15 条）；
  - magetech **1.16.8（415）**：福州大学学报(自然科学版)（issue_list 2026-6，16 条）；
  - cnki **1.12.7（846）**：图书馆理论与实践（CBPT portal 2026-5，12 篇）、中国卫生信息管理杂志（CBPT portal 2026-5，24 篇）。
- 写回清单：`journal_catalog/core/domestic-p1-recheck-applied-2026-11-26.csv`；3 包测试 custom47/magetech35/cnki32，平台 **181 passed + 81 subtests**。
- smoke run 52（monitor 63，manual，已归档）：3 包 **14 条入库、0 rejected**；magetech partial 仅 1 条摘要补采为空；4 本全部有数据。
- 仍待定/不可写回 27 本（待定 23 + 不可写回 4）：文本目次 7（建筑学报、当代世界社会主义问题、出土文献、芙蓉、中医学报、艺术工作、领导科学，仍无单篇链接）；停更 8（中国畜牧、有色金属、中华医院管理、合成生物学、给水排水、分析科学学报、建筑遗产、南昌大学学报，均无新期）；PDF-only 4（中华危重病急救医学、高校应用数学、土木工程与管理、自动化与仪器仪表）；SPA 3（时珍国医国药、煤炭转化、武汉大学学报医学版，findBySld 仍 null）；另有中华心血管网络版/光通信研究（首页混多期，暂不写）、食品与发酵科技（2026 仅第 1 期）、中华医院感染（仅单篇首发）、中国性科学（空目录）。复测证据：`journal_catalog/core/domestic-p1-recheck-evidence-2026-11-26.csv/md`。
- CNKI 噪声过滤补充：稿约/编后/会议召开/典型案例，图书馆门户由 16 条收敛为 12 篇研究论文。
- 覆盖重算：平台国内总刊 **3177**；核心 **2217/3461（64.1%）**；仅在目录 113、歧义 12、新增候选 1119；backlog **1131**（A11/B54/C69/D73/E566/F357/G1）。
- P1 1–196 累计写回 **64 本**（Top20 9 + 21–80 9 + 81–196 42 + 复测 4）。

## 2026-11-26 国内 P1 81–196 复核与写回

- 12 组只读探测（116 本，前 11 组 10 本、末组 6 本）：status **ok 43 / warn 26 / blocked 17 / no_current 13 / fail 11 / pdf_only 4 / login 2**；证据 `journal_catalog/core/domestic-p1-batch3-evidence-2026-11-26.csv/md`。
- 分诊：**写回 42 / 待定 31 / 不可写回 43**；写回项全部用生产 parser live 复核，未直接采信 agent。
- 写回并导入 42 本（只升 patch，按实际平台归包）：
  - custom_toc **3.10.5（845）**：yiigle 9 本（磁共振成像、中华显微外科、中华眼科、中华整形外科、中华胸心血管外科、中华医学遗传学、中华医学科研管理、中华医学美学美容、中华心律失常）+ 河南师范大学学报(自然科学版)、航天返回与遥感、电子元件与材料、哈尔滨工业大学学报(社科版)、中国细胞生物学学报、中医药导报；
  - cnki **1.12.6（844）**：铁道标准设计、兰州大学学报(自然科学版)、听力学及言语疾病杂志、华侨华人历史研究、实用肿瘤杂志、中国胶粘剂、中国中西医结合肾病杂志、中国斜视与小儿眼科杂志、中国中西医结合耳鼻咽喉科杂志、哈尔滨医科大学学报、哈尔滨商业大学学报(社科版)、影像诊断与介入放射学、烟台大学学报(哲社版)、生物技术、中国小儿血液与肿瘤杂志；
  - rhzh **1.3.6（327）**：热加工工艺、腐蚀与防护、航天器环境工程、无损检测、云南农业大学学报、真空与低温；
  - magetech **1.16.7（414）**：航空材料学报、地下空间与工程学报、心理研究、高等学校化学学报；
  - vsb **1.2.5（14）**：青岛科技大学学报(自然科学版)；
  - sancai **1.0.4（3）**：郑州大学学报(医学版)。
- 写回清单：`journal_catalog/core/domestic-p1-batch3-applied-2026-11-26.csv`。
- parser 修补：custom_toc 支持 yiigle `section_start_regex` 用法、pair_link `url_template`（JS `viewPaper()` 链接）、“目次/封面”噪声过滤与“浏览次数/附件下载”标题清理；magetech 支持 `/CN/abstract/abstractN.shtml` 并过滤封面目次；sancai 新增郑大医学版 API 站点。
- 测试：custom 47、magetech 35、cnki 32、rhzh 35、vsb 19、sancai 3；平台 **181 passed + 81 subtests**。
- smoke run 50（monitor 61，manual，跑完归档）：6 包 **52 条入库、0 rejected**；custom 9、magetech 15、cnki 6、rhzh 9、vsb 3、sancai 10。CNKI 肾病杂志首轮瞬时 0 条，单刊 run 51（monitor 62）重试 **3 条成功**并归档；14 本抽检全部有数据。
- 覆盖重算：平台国内总刊 **3173**；核心 **2213/3461（63.9%）**（+42）；仅在目录 116、歧义 12、新增候选 1120；backlog **1132**（A11/B54/C70/D73/E566/F357/G1）。
- 说明：yiigle 9 本为**题录级**（摘要页 WAF/CAPTCHA，不公开取摘要）；CNKI WK* 部分摘要内联、paperDigest 摘要 best-effort；未写回项（text-only、TLS、SPA、停更、验证码等）保持原状，不绕过。

## 2026-11-26 国内 P1 21–80 复核与写回

- 10 组只读探测（60 本，每组 6 本）：status **ok 11 / warn 11 / blocked 16 / fail 10 / pdf_only 5 / no_current 4 / login 3**；证据 `journal_catalog/core/domestic-p1-batch2-evidence-2026-11-26.csv/md`。
- 分诊：**写回 9 / 待定 18 / 不可写回 33**；写回项全部用生产 parser live 复核，未直接采信 agent/WorkBuddy。
- 写回并导入 9 本（只升 patch）：
  - custom_toc **3.10.4（830）**：系统工程（10 条，题录级，文章链接为 CNKI kcms2）；
  - qinyun **1.9.4（172）**：中国园林（19 条）；
  - magetech **1.16.6（410）**：控制理论与应用（21 条）；
  - cnki **1.12.5（829）**：农村金融研究（6 条，WKH3 题录）、高教探索（17 条，portal 含摘要）、中华中医药学刊（46 条，portal 含摘要）；
  - rhzh **1.3.5（321）**：工程科学与技术（32 条，内联摘要）、水文地质工程地质（24 条）、现代大学教育（11 条）。
- 写回清单：`journal_catalog/core/domestic-p1-batch2-applied-2026-11-26.csv`。
- parser 修补：rhzh 增加 gzip 解码、相对 `article/id` 链接、Vue `resName` 模板；magetech 过滤“YYYY-MM目录”标签。rhzh 新增 3 项单测。
- 测试：custom 46、qinyun 36、magetech 34、cnki 32、rhzh 35；平台 **181 passed + 81 subtests**。
- smoke run 49（monitor 60，manual，跑完归档）：5 包 **34 条入库、0 rejected**；cnki 9、magetech 10（partial：1 条摘要补采为空）、qinyun 3、rhzh 9、custom 3；9 本全部有数据。
- 覆盖重算：平台国内总刊 **3131**；核心 **2171/3461（62.7%）**（+9）；仅在目录 153、歧义 13、新增候选 1124；backlog **1137**（A12/B55/C72/D73/E567/F357/G1）。
- 待定 18：外语教学（纯文本无链接）、国际政治研究（TLS 证书链）、思想教育研究（停更 2022）、档案学通讯、妇女研究论丛（2025-05）、天津社科/求是学刊（纯文本）、管理现代化（题录+知网验证码，期次滞后）、学习与探索/江西社科/地方财政研究（仅 PDF/扫描图）、学前教育研究/教育与职业（仅封面图）、教育理论与实践（目录以新闻发布）、医学与社会（仅 2019）、基础教育（2021 停更）、北理工学报（仅最新录用）、流体机械（2023 停更）。
- 不可写回 33：blocked 16（验证码/腾云未开通/方正 SPA）、fail 10（TLS/超时/404/DNS）、no_current 4、login 3；均未绕过登录/验证码/WAF。
- 已知缺口：magetech 控制理论与应用摘要 0（详情页无摘要，首页内联摘要尚未解析）；系统工程为标题级题录，无作者/摘要。

## 2026-11-26 国内 P1 Top20 复核与写回

- Top20 live 复核：**7 可写回 / 6 待定 / 7 不可写回**；证据 `journal_catalog/core/domestic-p1-top20-evidence-2026-11-26.csv/md`。
- 实际写回并导入 **9 本**：
  - custom_toc **3.10.3（829）**：管理世界、中国法学、经济与管理评论、体育学刊；
  - qinyun **1.9.3（171）**：体育学研究；
  - magetech **1.16.5（409）**：电工技术学报；
  - rhzh **1.3.4（318）**：农业现代化研究；
  - vsb **1.2.4（13）**：管理科学；
  - cnki **1.12.4（826）**：兰州大学学报（社科版，题录 list-only，摘要验证码 best-effort）。
- 平台 smoke run 48：9 本全部入库，44 条；magetech 首次瞬时失败、重试后 completed 20 条；其余包 completed。没有绕过登录/验证码/WAF。
- 平台国内总刊 **3122**；核心覆盖 **2162/3461（62.5%）**（另有 3 本旧覆盖重匹配：CHINESE HERBAL MEDICINES、新型炭材料、物理化学学报）；backlog **1139**（A12/B55/C73/D73/E568/F357）；核心新增候选 **1126**、仅在目录 **160**、歧义 **13**。
- 写回清单：`journal_catalog/core/domestic-p1-applied-2026-11-26.csv`；包测试 custom 46、qinyun 36、magetech 34、rhzh 32、vsb 19、cnki 32；平台测试 **181 passed + 81 subtests**。
- 待定/不可写回：统计与决策（微信文章）、南京社会科学（摘要验证码）、城市规划学刊/大连理工（仅 PDF）、体育学刊已写回但仅部分中文摘要、中国社会科学无当期、中外法学验证码、当代经济科学 SPA、南京审计 WAF、经济与管理/会计研究腾云未开通、陕师大学报停更。

## 2026-11-25 Q1 五批验证与 bulk 优化

- 5 个 Q1 分层批次 run 23–27（250 本，30 天窗口，per_journal 20）：**1703 条、184/250 刊有结果、66 本 0 条、DOI 1703/1703、摘要 1240/1703（72.8%）**；source_api 全 OpenAlex；8 个 429 warning 均出现在 OpenAlex 空结果转 Crossref 的兜底请求上；无包级 failed。
- 批次耗时：run23 3.2、run24 5.2、run25 10.1、run26 13.4、run27 15.4 分钟，合计 **47.3 分钟/250 本**；按此全量逐刊约 **单 Worker 16.5h、双 Worker 8.3h**，日更不可接受。
- 已验证 OpenAlex 支持多 ISSN OR 查询（3 个 ISSN 一次 638 条）；正在做 **bulk_window**（100 ISSN/次、cursor 分页、DOI 去重、映射回期刊），目标把全量压到几十分钟级。
- `foreign_q1_journals` **1.1.0 bulk** 完成：26 项包测试；200 本 live 5.1 分钟（逐刊同批约 9.7 分钟），bulk 全量 2 Worker 预计 1–2 小时级。
- **1.1.1 频次标注**：JCR `PUBLICATION FREQUENCY` 已补到 Q1 watchlist 和包的 `publication_frequency/issues_per_year/frequency_class`；选刊标签第 3 位显示“频次:年刊/季刊/月刊…”。包 5,238 本：季刊 1,358、月刊 1,154、双月刊 910、年刊 751、半年刊 159、每年 3 期 146、周刊 43、未知/每年 N 期 185。同步修复非 bulk“记录全被过滤仍算成功”的 0 条误判；包测试 31 项、平台测试 **181 passed + 81 subtests**。
- 0 条分析：5 批 66 本 0 条中 42 本低频/年刊，真正值得 Crossref 兜底的仅 7 本；bulk 默认不做全量 Crossref 兜底，保留可选 90 天零条探针。
- 首批 500 本 bulk 验证 run 28：**6.5 分钟、2918 条、359/500 刊有结果、141 本 0 条（低频为主）、DOI 2918/2918、摘要 2466/2918（84.5%）、source_api 全 OpenAlex、0 warning、per_journal max 20**；inserted 2376、updated 31、unchanged 511（去重正常）。bulk 全量 11 批双 Worker 预计约 40 分钟。
- 2026-11-26 全量 bulk run 29–39：用户决定“500 本够了，全量就算了”，已停止 Worker；29–31 在停止前完成（2918/3789/6562 条，数据保留），32–39 标 `USER_CANCELLED`，11 个 monitor 全部归档，无 Worker 残留。**不删除已完成三批数据**；本次报告只用 run 28 的 500 本。
- 2026-11-26 当天用户改为继续全量：恢复第 4–11 批（run 40–47），全部 completed；Worker A 收尾时 MariaDB 死锁（1213），但 8 个 package_run 都已完成，数据无损；Worker B 正常退出。全量覆盖 run 28/30/31/40–47，共 11 批。
- **全量报告已生成**：
  - `foreign_q1_full_2026-11-26_journals.csv`（5,238 行）与 `_report.html`（图表 + 可搜索逐刊表）；
  - `foreign_q1_full_2026-11-26_items.csv`（53,136 条，79.4MB）、`_abstracts.csv`（35,685 条，72.5MB）、`_items.html`（53,136 条，76.9MB，分页搜索）；
  - 5,238 本中 **4,549 本有结果、689 本 0 条**（低频/年刊 261 + 窗口内无新文 428）；53,138 条、DOI 100%、摘要 35,685（67.2%）；同 DOI 合并 2 条；
  - 全量 edition：SCIE 37,086、SSCI 9,685、ESCI 6,232、AHCI 87、未知 46。
- 500 本报告脚本（逐刊 CSV/HTML + 文章 CSV/分页可搜索 HTML）已生成，使用 run 28，输出 `foreign_q1_500_2026-11-26_*`：
  - 逐刊：500 行、2918 条、359 本有结果、141 本 0 条（低频/年刊 70、窗口内无新文 71）、DOI 100%、摘要 84.5%；
  - 文件：`foreign_q1_500_2026-11-26_journals.csv`、`foreign_q1_500_2026-11-26_report.html`、`foreign_q1_500_2026-11-26_items.csv`、`foreign_q1_500_2026-11-26_abstracts.csv`、`foreign_q1_500_2026-11-26_items.html`。
  - 注意：run 28 是 watchlist 前 500，主要 ESCI/AHCI，不代表全 Q1；已完成 29–31 的 1,500 本数据保留，未生成报告。
- 知网/万方补刊分析：核心候选 2,385 本，但仅 210 本有目录/万方官网 URL，2,175 本只有知网导航页；最可执行的是 169 本 `catalog_only`；报告 `journal_catalog/core/cnki-wanfang-opportunities-2026-11-25.csv/md`。

- 国内可补好刊清单：P1 196（S1 已有证据 27 + S3 目录 URL 169；A 147/B 13/未标 36）、P2 万方官网候选 25、P3 仅知网导航 Top 100、P4 暂不推荐 764（阻断/失败/仅 PDF 代表 14）；平台聚类 P1：自建/机构 127、chinajournal 26、CNKI CBPT 11、yiigle 11、玛格泰克 9、仁和 7、方正 3 等。**URL 均未 live 验证**。文件 `journal_catalog/core/domestic-addable-2026-11-26.csv/md`。

## 2026-11-25 国外 Q1 包与首轮验证

- 新建 **`foreign_q1_journals` 1.0.1**：5,238 本（Q1 全学科，排除 41 本已知 Inactive），OpenAlex 主源、失败回退 Crossref，DOI 身份，`lookback_days` 默认 **30**，`per_journal_limit` 20，只存元数据+链接、不下载 PDF。
- 平台目录上限从 5,000 行/4MB 放宽到 **10,000 行/8MB**，网页选刊接口实测返回 5,238 本；平台测试 **172 passed + 81 subtests**。
- 首轮验证 run 19（40 本、14 天窗口）：102 条，DOI 102/102，摘要 76/102；22/40 刊有结果，18 本 0 条均为窗口外或 erratum，无 warning/失败。
- 30 天对照 run 20：**201 条**，inserted 99、unchanged 102、rejected 0；与 14 天窗口已有 102 条完全重合且全部 unchanged，新增 99 条为 10 月下旬—11 月上旬文章；28/40 刊有结果，DOI 201/201，摘要 138/201（68.7%），无 warning/失败。
- 结论：30 天窗口更适合日更（补索引滞后，重复由 DOI + first/last 去重吸收）；正式批次使用 30 天。
- 批次脚本：`scripts/create_foreign_q1_batches.py`，50 本/批 → **105 个 manual monitor**（末批 38 本），dry-run 通过；不自动入队、不建 daily。
- Q1 图表报告：`journal_catalog/foreign/foreign_q1_report_2026-11-25.html`。
- 全量 Q1 日更还需要 **OpenAlex 免费 key**：无 key 实测 **1,000 请求/天、$0.1/天、10 请求/秒**（当前剩余 606）；5,238 本/天必须用免费 key（10 倍预算，$1/天、30 请求/秒）。key 放本地 `.env` 的 `CRAWLER_SECRET_OPENALEX_API_KEY`，平台启动时会加载；不要把 key 发聊天。下一步先跑 5 批/250 本规模验证，再决定是否全量 105 批。

## 2026-11-25 国外 Q1 watchlist 与源覆盖审计

- 已解压用户提供的 `期刊.zip` 到 **`journal_catalog/source/periodicals_2026-11-25/`**（79,782 个文件、约 462MB，含 `SOURCE_MANIFEST.json` 和原 zip SHA256）；**没有运行包内爬虫脚本**。
- 数据资产：
  - **JCR 2025 逐刊 JSON 22,643 本**：分区/JIF/JCI/AIS、ISSN/eISSN、出版社、学科、Edition；
  - **Scopus 官方来源表 45,262 行 × 52 列**：Active/Inactive、Coverage、Publisher、ASJC 学科（无分区列）；
  - **知网全量期刊 11,674 本**：核心收录、影响因子、ISSN/CN、主办单位、学科分布；
  - **万方官网供应商 CSV** 2.56MB：刊名/ISSN/CN/官网/供应商/置信度。
- 正式 watchlist：**JCR 2025 全学科 Q1 共 5,279 本**（SCIE 2,958、SSCI 1,331、ESCI 941、AHCI 42、其他 7；Scopus Active 5,140、Inactive 41、Unknown 98；`include_daily=yes` 5,238）。文件：`journal_catalog/foreign/foreign_journals_q1_2026-11-25.csv`。
- 源审计样本：200 本（按 Scopus Life/Health/Physical/Social/Unknown 各 40 本分层）：`foreign_q1_audit_sample_2026-11-25.csv`。
- 200 本审计结果：
  - **OpenAlex 有记录 183/200（91.5%）**，DOI 覆盖 99.97%，摘要覆盖 62.3%，32 本 90 天条数 >100 需分页；
  - **Crossref 有记录 176/200（88.0%）**，DOI 100%，摘要仅 33.3%；存在 ISSN 记录分裂，必须主 ISSN/eISSN 双路探测；
  - **PubMed 生物医学子集 56/60（93.3%）**，DOI 100%、摘要 74.8%；注意年份级 PubDate 和 `[PDAT]` 不稳定，建议用 `[EDAT]`；
  - **RSS 映射 Q1 全量命中 1,638/5,279（31.0%）**；200 样本命中 56 本、90 天有更新 39 本；ScienceDirect feed 无摘要/DOI/精确日期，RSS 只能当“新一期信号”。
- 选源结论：**OpenAlex 主源 + Crossref DOI 兜底**（176 本），7 本 OpenAlex-only，16 本 90 天无记录，1 本 PubMed 主源；摘要源 OpenAlex 133、PubMed 44、Crossref 7、无 16；DOI 源 OpenAlex 182、PubMed 1、无 17。汇总：`foreign_source_audit_q1_2026-11-25.csv/md`。
- 网络：全程直连（OpenAlex/Crossref/NCBI/Nature RSS 已测），**没有启用 Clash/系统代理/TUN，也没有设置全局代理变量**；Europe PMC 直连超时，PubMed 改用 NCBI E-utilities。
- 下一步：写国外源适配器（OpenAlex/Crossref/PubMed/RSS），先 manual 小样本 live 验证，再扩到 Q1 全量；不建 daily 任务。

## 2026-11-25 翻页与详情页摘要修复（国内收口）

- 审计报告：[pagination-audit-2026-11-25.md](../journal_catalog/core/pagination-audit-2026-11-25.md)、[abstract-detail-audit-2026-11-25.md](../journal_catalog/core/abstract-detail-audit-2026-11-25.md)。
- 包版本已升级并导入：`cnki_cbpt` **1.12.3**、`custom_toc_journals` **3.10.2**、`magetech_journals` **1.16.4**、`qinyun_journals` **1.9.2**、`rhzh_journals` **1.3.3**、`hep_mirror_journals` **1.1.1**、`paperonce_journals` **1.1.2**、`vsb_journals` **1.2.3**。
- 翻页：
  - custom_toc 统一 latest_issue 分页层：plain/pair/issue 自动发现（同 host/path、仅页码参数、排除年份/期次参数、期次标记一致、最多 10/20 页、0 新增/重复页停止）；json/onclick 只在显式配置时翻页，避免“机电工程”类 API 串期。
  - cnki 去掉固定 19 页上限，新增 `max_pages_per_journal`（1–40，默认 20），校验 `yearId/issueId`，JS pager 只告警不硬猜。
  - magetech latest_issue 接入分页；STAE 改 `pageSize=200` + `pageNum` 循环；qinyun/rhzh 增加受限期次分页和跨期过滤；founder/paperonce/sciengine/sancai/oa/vsb/hep 为单页/整期接口，无需翻页。
  - 翻页验收 run **14**：CNKI 68 条（卫生研究 25 + 临床骨科 43）、custom 44 条（粉煤灰 24 + 机电工程 20），共 112 条，0 warning。
- 摘要：
  - 新增/增强详情页补采：hep（`citation_abstract`）、magetech（`#zhaiyao`/`#collapseOne`）、paperonce（`#LbZY`）、vsb（`article-abstract`/`【摘要】`/meta）、custom（多模板选择器）、rhzh（优先 `dc.description`）；只填空、限量、限速。
  - 同批 48 本对照 run **16**：摘要 **55/92（59.8%）→ 91/95（95.8%）**；magetech 0/9→10/10、rhzh 6/10→10/10、custom 2/10→10/10、hep 0/6→6/6、paperonce 4/6→6/6、vsb 0/6→4/6；oa 4/6（详情无摘要）、sancai 4/4。
  - run 16：95 fetched、0 inserted、17 updated（补摘要）、78 unchanged、0 rejected。
- 扩大测试 run **15**：12 包、**192 本**（大包 20/包，小包全量），**362 条**，inserted 232、updated 23、unchanged 107、rejected 0；所有包 completed/partial，**无 failed/timed_out/PROTOCOL_ERROR**。逐刊 182 ok / 1 zero / 9 failed，失败均为站点/模板级：结构工程师 403、东南国防医药 404、清华大学教育研究 RSS 非法、南京师范工程技术 unsupported、生物医学工程研究 404、湖北中医药/西部医学 unsupported、浙江林业科技 404、中国生态农业 IncompleteRead；空间科学与试验学报 0 条无 warning。报告：[run-journals-15-2026-11-25.md](../journal_catalog/core/run-journals-15-2026-11-25.md)。
- 大样本 run **17**：12 包、**402 本**（大包 50/包、小包全量；3113 的 12.9%），每刊最多 10 条、每刊最多补 1 条摘要；**3635 条**，inserted 3192、updated 17、unchanged 417、rejected 0；所有包 completed/partial，**无 failed/timed_out/PROTOCOL_ERROR、无翻页类 warning**。逐刊 370 ok / 3 zero / 29 failed，失败均为站点/模板级（403/404/417/412、超时、unsupported、RSS 非法等）。报告：[run-journals-17-2026-11-25.md](../journal_catalog/core/run-journals-17-2026-11-25.md)。
- 大样本发现并修复 magetech 通用解析缺口：`中国医药导刊` 的 DOI 形如 `10.1009-0959.2026.110001`（无 `/`），旧正则漏掉 17 条；已放宽 `/CN/10.*` 通用匹配并升 **1.16.4**，单测 31 通过，单刊补验 run 18 抓到 **17 条**。另两本 0 条为站点问题：大坝与安全 502、现代纺织技术 404。
- 说明：run 15/17 的逐刊上限分别为 2/10 条，翻页深检目前覆盖已知多页刊（卫生研究、临床骨科、粉煤灰、机电工程）；402 本大样本仍是抽样，不等于 3113 本逐本验证。
- 修复 magetech 农学学报：当期多个条目共用 `id="art2"`，external_id 增加 DOI/URL 兜底；旧记录已 re-key 到 DOI，run15 农学学报恢复 2 条（受平台每刊上限）。
- 测试：12 个包单测共 **237 passed**；平台 **164 passed + 81 subtests**。验收监控 #31/#32/#33/#34/#36 均已归档。
- 结论：国内公开源链路收口；剩余是站点级 blocked/不可采，不是平台/协议问题。下一步转国外日更。

## 2026-11-25 每日全量去重与更新时间标记（已实现）

- 迁移 **005**：所有包数据表新增 `sys_last_changed_at` / `sys_change_count`，回填 `last_changed=first_seen`、`change_count=1`（避免把“仅再次采集”误标为更新）；13 张表 **269 行**已回填，新增 `idx_last_changed`。
- 入库语义：新插入 `last_changed=first_seen=last_seen`、`change_count=1`；只有内容哈希变化才更新 `last_changed` 并 `change_count+1`；unchanged 只更新 `last_seen`。
- 数据页/API：`/api/v1/data` 支持 `since` + `change=new/updated/changed`，返回 `first_seen_at/last_seen_at/last_changed_at/is_new/is_updated`；数据页新增“变更类型”筛选、“首次发现/最近更新”列和“新增/更新”标记。界面只保留 **全部 / 今天有变动** 两项（后端仍支持细分 new/updated/changed）。
- 新脚本：`create_full_crawl_monitors.py`（12 包按 100 本/批 dry-run 为 37 个 manual 任务）、`report_run_journals.py`、`report_cross_package_duplicates.py`、`audit_identity_fields.py`。run #8 报告：48 刊、47 ok、1 failed（安徽师范大学学报社科版 TIMEOUT）；跨包 DOI 61 条、0 重复；身份审计 17 包、0 high。
- 验收（HEP 2 本未入库刊，monitor #30 已归档）：
  - run 9 首次：inserted 4，`first=last=changed`，`change_count=1`；
  - run 10 连跑：inserted 0 / unchanged 4，`last_seen` 前进、`last_changed`/`change_count` 不变；
  - run 12 模拟内容变化（改标题+内容哈希）：updated 1 / unchanged 3，`last_changed` 前进、`change_count=2`，标题恢复；
  - run 13 再跑：unchanged 4，`last_changed` 保持；
  - API 三种筛选正确、非法参数 422；浏览器数据页验证通过（“今天新增”90 条、新增标记正常）。
  - 平台测试 **164 passed + 83 subtests**。
- 结论：每日抓取→去重→更新时间标记链路已完成；**自动 daily 任务尚未创建**，需要用户确认后再建 Scheduler 任务。
- 下一步：国外期刊 JCR/Scopus watchlist + 100–200 本源覆盖审计；需要用户提供 JCR/Scopus 文件路径。

## 2026-11-25 国内分包抽样平台测试（run #8）

- 手动监控 **#29「国内分包抽样-2026-11-25」**：12 个国内包、47 本近期验证通过的刊，每刊最新一期最多 2 条、关闭摘要补采、单刊 15s、单包 300s；跑完后已归档。
- run #8 **partial**：抓取 **92** 条，inserted **86**、unchanged **6**、rejected **0**；**11 包 completed，sancai partial**。
- 逐包条数：cnki 8、magetech 9、qinyun 10、rhzh 10、sancai 2、paperonce 6、founder 10、oa_rss 6、vsb 6、hep 6、custom 10、sciengine 9。
- 唯一包级 partial：sancai 的安徽师范大学学报（社会科学版）`URLError: timed out`，属站点级；同包合肥师范学院学报 2 条正常。无协议错误、无 rejected。
- oa_rss 6 条全部 **unchanged**，验证了入库去重链路；magetech 农学学报、sciengine 中国科学数据各 1 条（当期只解析到 1 篇，非协议错误）。
- 明细：`.local/platform-package-sample-test-2026-11-25-details.csv`；汇总：`.local/platform-package-sample-test-2026-11-25-result.json`；脚本：`scripts/platform_package_sample_test.py`、`scripts/run_platform_package_sample_worker.py`。
- 结论：12 个国内包的平台链路均可用；站点级超时保留记录，不阻塞后续。

## 2026-11-25 WorkBuddy accepted 写回与国内公开源收口

- WorkBuddy 84 条 accepted 全部按目标包做生产 parser live 复核：known 42 本首轮 **16 pass / 16 warn / 10 fail**；warn/fail 经第二轮恢复 **10 pass / 18 warn / 0 fail**；custom 42 本首轮 **13 pass / 2 warn / 3 fail / 24 needs_adapter**，24 本经 agent 补配置后 **10 pass / 11 warn / 3 fail**，另载人航天 EXTRA 修复后 pass。
- 写回并导入 **85 本**：
  - **SciEngine 新建包 `sciengine_journals` 1.0.1（14 本）**：公开 JSON API、DOI 身份、只存 PDF 链接；新增最新卷期发现 `getJournalLatestVolumeAndIssue`，每次先追最新期、失败或最新期无有效文章回退固定快照；live 抽 4 本 60 条、14 本合计 314 条通过 `output_schema`。
  - **known 34 本**（magetech 5、qinyun 6、rhzh 6、founder 11、cnki 4、paperonce 2）：含 4 本 RHZH `current-data?publisherId=` 修复、兵工自动化换期页、13 本经协议/解析修复后恢复（四川大学学报 gzip、新疆石油/测试技术噪声、电焊机 HTML 标记、玉米/农机/南京信息/军事护理、现代检验 legacy paperopen、断块噪声、现代应用物理投稿须知、耐火材料 DOI 链接、农学学报 http）。
  - **custom 37 本**：13 本首轮 pass + 2 本可修 warn（商业经济 GB2312、吉林农大团队介绍）+ 21 本 JSON/pair 配置 + 载人航天 link_base 修复；其中 8 本 NoteFirst 统一 `IssueId=0` 自动当期。
- 包版本（后为支持全量选刊，cnki/magetech/rhzh/founder 的 patch 位已上调）：`cnki_cbpt` **1.12.2（825）**、`custom_toc_journals` **3.10.1（825）**、`magetech_journals` **1.16.2（408）**、`qinyun_journals` **1.9.1（170）**、`rhzh_journals` **1.3.2（317）**、`founder_journals` **1.2.2（101）**、`paperonce_journals` **1.1.1（77）**、`sciengine_journals` **1.0.1（14）**。平台总刊 **3113**。
- 冒烟：accepted-known 34 本中 21 本首轮 **21/21**、补充 13 本 **13/13**；custom **37/37**；SciEngine live 抽样通过。包内单测：cnki 20、custom 30、magetech 13、qinyun 19、rhzh 17、founder 7、paperonce 7、sciengine 13；平台 **151 passed + 72 subtests**。
- 核心覆盖 **2150/3461（62.1%）**；中文 **1811/3117**、英文 **339/344**；候选 **1129**、版本歧义 **13**、仅在目录 **169**、补录入包 **1255**。backlog **1142**（A12、B55、C73、D73、E571、F357、G1）。2377 覆盖仍 **1856/2377（78.1%）**；2377 外 **1254**（新增 85 本均为核心名单候选，不在 2377 内）。
- 未写回：custom 3 本 parser 缺口（哈工大社科版 onclick 标题/URL 模板、矿山机械与浙大理工嵌套 JSON）、magetech 数据与计算（当期 502）、石河子（TLS 弱套件）、rhzh 海军航空/现代大学教育/科普研究（旧模板）、4 本仅放宽证书可采（国际政治研究、西电学报、植物遗传资源学报、农学学报已改 http 写回）；97 本 held 不写回，保留 backlog。
- 审计：`.local/accept/verified-known*.csv/md`、`verified-custom.csv/md`、`custom-adapter-configs.csv/md`；写回清单 `journal_catalog/core/sciengine-applied-2026-11-25.csv`、`workbuddy/accepted-known-applied-2026-11-25.csv`（34 行）、`workbuddy/custom-applied-2026-11-25.csv`（37 行）。
- 国内公开可采核心已接近上限（剩余以登录/验证码/WAF、PDF-only、无当期、嵌套 SPA、TLS 为主）；下一步按计划转国外日更，先向用户说明再启动。

## 2026-11-25 平台全量测试暂停

- 为验证所有国内期刊在平台上可跑，创建 manual monitor **#28** / run **#7**：12 个国内包、2775 本，每刊最新一期 2 条、关闭摘要补采、item_limit=目录数×2、单包超时 7200s。
- Worker 顺序执行，CNKI 825 本首包约 13 分钟仍无输出（包只在结束时写 `items.jsonl`，没有中途进度）；用户因太晚叫停。
- 已停止 Worker/子进程；run #7 的 12 个 package_runs 标记 `failed / USER_CANCELLED`，monitor #28 已归档；**没有结果、没有包级报错**，不能判定通过。
- 白天改按包/分批重跑：先小包，再 founder/paperonce/qinyun，rhzh/magetech/cnki/custom 按 50–100 本/批；每批 manual、per_journal_limit=1–2、关摘要补采、timeout 10–15s；站点级 502/SSL 记已知问题，协议错误/整包失败才修。通过后再转国外。
- 新对话接手提示词：`C:\Users\86139\Desktop\IDIW_新对话_接手提示词_2026-11-25.md`。

**待开发需求（2026-11-25 用户提出）：** 每日抓取所有期刊、跨天去重、标记更新时间。平台已有 `sys_identity_hash`、`sys_first_seen_at`/`sys_last_seen_at`、`sys_content_hash` 和 `inserted/updated/unchanged` 统计；缺 `sys_last_changed_at`、每日全量预设/`all_journals`、新增/更新视图、跨包 DOI 重复报告、全量分批/并行编排和失败刊报告。国内“最新一天”是当前期快照的新增，不是发布日期；国外用 `published_at` 窗口。验收标准见接手提示词 4.5 节。

## 2026-11-25 WorkBuddy 合集验收（199 行）

- 13 个 Task、199 行；逐行只读 live 证据复核：**109 evidence_ok、14 weak、27 blocked、45 fail、4 alias_confirmed**。
- 初步写回分类：**84 accepted_candidate**（可进入生产 parser 复核）+ **14 SciEngine JSON 适配**（16 行去重后 14）+ **97 held**（A12 5 条非论文、2 条停更、3 条重复、1 条已在包、14 weak、27 blocked、45 fail）+ **4 英文别名**。
- 关键问题：A12 天津社会科学/领导科学/节能技术/艺术工作/出土文献的 items 不是论文；中国现代手术学杂志 2018、妇女研究论丛 2025 停更；6 本 NoteFirst `article_link_regex` 只匹配根路径；CNKI 3 本 `list_ok_detail_blocked`；RHZH 现代应用物理/机械工程材料频控；SciEngine 文章页 SPA 必须走 `selectArticlesInJournalOfVolumeAndIssue` JSON；NPE 的 ISSN 证据错误需废弃。
- **未写回、未改包/DB/任务**；下一步按目标包/模板做生产 parser live 复核，再分批 apply→smoke→import。
- 验收文件：[summary-2026-11-25.md](../.local/accept/summary-2026-11-25.md)、[merged-final.csv](../.local/accept/merged-final.csv)。

## 2026-11-24 摘要补充（qinyun/rhzh/custom）

- qinyun **1.8.0**：详情 enrichment（`Abstract`/`CnAbstractValue`/标签段）+ 目录噪声过滤 + base href 修复；单测 18 项。
- rhzh **1.2.0**：`current-data.abstractinfoCn` + 详情 `article-abstract`（平衡 div、拒绝 `{{@...}}` 占位），12s 间隔；单测 17 项。
- custom **3.9.0**：JSON `fields.abstract`/常见字段 + 详情通用容器；每刊默认最多 3 条；单测 28 项。
- 主线程独立 live 复测：qinyun 9/9、rhzh 13/15、custom 12/15，合计 **34/39（87%）**；改造前 6/39。三包已导入；平台 151 + 72 subtests 全过。
- CNKI **1.11.1**：portal 列表 `div.paperBox` 摘要 + WK 同会话 `paperDigest` 详情；单测 20 项，平台 151+72 全过。主线程复测 5 本 15/15 有摘要；agent 抽样 10 本 49/50。已导入。中国骨与关节杂志有 2 条格式指南（非研究论文），后续可再加标题过滤。
- 思路文档：[domestic-journal-pipeline-2026-11-24.md](domestic-journal-pipeline-2026-11-24.md)；各包报告在 `.local/abstract-reports/`。

## 2026-11-24 日记实验（每包随机 5 本）

- 13 个学术包各随机抽 5 本（sancai 仅 2、flagship 仅 4，共 61 本），用生产 parser 抓当前最新：**141 条文章元数据、48 本有结果、13 本失败**。
- 有结果的条目 **标题/文章 URL 100%**；作者/摘要/DOI 因包差异大（founder/paperonce/sancai/supplement 较全，cnki 无 DOI，custom/qinyun/rhzh/vsb/hep 常无作者或摘要）；**PDF 链接仅 magetech 8/12 条**，其余包只有文章页/DOI，未下载任何 PDF。
- “今天”口径：国内包是**当前期**（2026 年第 5/10/11 期等），不是按发布日期增量；supplement 用 OpenAlex 近 7 天，最新到 2026-11-17~20，无 11-24 当天记录；flagship 是 AI 关键词模式，只命中 1 条 Science。
- 发现的问题：qinyun 首条“目录、封面、封底”噪声；13 本失败以 502/UNSUPPORTED/0 条为主，随机样本可重现，日更任务需重试和失败记录。
- 报告：[daily-sample-summary-2026-11-24.md](../journal_catalog/core/daily-sample-summary-2026-11-24.md)；逐刊/逐条：[daily-sample-2026-11-24.csv](../journal_catalog/core/daily-sample-2026-11-24.csv)、[daily-sample-items-2026-11-24.csv](../journal_catalog/core/daily-sample-items-2026-11-24.csv)；脚本 `scripts/experiment_daily_sample.py`。

## 2026-11-24 英文 17（supplement）

- 用 OpenAlex/Crossref 反查 17 本英文缺失刊，全部找到 ISSN。
- **11 本新写入 supplement**（1.1.2，338 本），冒烟 **5/5**、supplement 单测 9 项、平台 151 + 72 subtests。
- 另 **2 本**（Bio-Design and Manufacturing、Gastroenterology Report）本来就在 supplement，因覆盖脚本只索引 `issn` 单字段、未拆多 ISSN 而未匹配；已修 `scripts/build_core_coverage.py` 增加 `split_issns()`，按多 ISSN 严格匹配后计入覆盖。
- 剩余 **4 本**（ACTA GEOLOGICA SINICA ENGLISH EDITION、CHINA ELECTROTECHNICAL SOCIETY TRANSACTIONS…、CHINESE HERBAL MEDICINES、JRMGE）supplement 已有同刊记录，但核心名单行无 ISSN、刊名不同；按“只认 ISSN/CN/完全同名”不计覆盖，已追加 WorkBuddy **Task 4** 做官方别名确认。
- 当前英文覆盖 **340/344**；核心覆盖 **2065/3461（59.7%）**；中文 **1725/3117**；平台总刊 **3028**；backlog **1227**（A12、B74、C138、D74、E571、F357、G1）；2377 覆盖 **1856/2377**，2377 外 **1169**。
- WorkBuddy 合集追加 **Task 3（版本歧义 14）** 和 **Task 4（英文别名 4）**，Task 5 预留。

## 2026-11-24 C 组首批（25 本）

- C 组 163 本拆分：主线程先做 magetech 26 + paperonce 8 = 34 本；live 复核 **25 pass**（custom 20、paperonce 4、magetech 1）、9 fail。
- 25 本写回：`custom_toc_journals` **3.8.0（788）+20**、`paperonce_journals` **1.1.0（75）+4**、`magetech_journals` **1.15.0（403）+1**；冒烟 **9/9**；平台 **151 passed + 72 subtests**，包内 custom 19、magetech 12、paperonce 5。
- C 组首批后核心覆盖 **2052/3461（59.3%）**；中文 **1725/3117**、英文 **327/344**；平台总刊 **3017**；2377 覆盖 **1856/2377**，2377 外 **1158**；backlog **1240**（C 138）。
- 9 本失败（南昌大学学报医学版、大地构造与成矿学、天然气工业、应用与环境生物学报、教育与职业、数据与计算发展前沿、断块油气田、浙江大学学报.工学版、科学观察）已并入 WorkBuddy Task 2E。
- WorkBuddy 统一合集：`C:\Users\86139\Desktop\WorkBuddy_任务合集_IDIW_2026-11-24.md`。C 组剩余 138 本（Task 2A SciEngine 16、2B custom 82、2C CNKI 9+RHZH 11、2D Founder 11、2E main 9）+ B151 31 held（Task 1）；后续新任务追加到合集 Task 3，不再一份一份发。
- 统计报告：同一批 `core-coverage/core-source-summary/core-adapter-backlog/out-of-2377` 文件已重算。

## 2026-11-24 B151 写回（76 本）

- WorkBuddy B151 验收：151 本齐全；108 本 `ok_current` 经主线程逐本 live 复核后 **76 本写回**（custom 55、magetech 10、qinyun 5、cnki_cbpt 3、rhzh 2、hep 1）；31 本 held、1 本 rejected（高等学校化学学报仅封面）；43 本 blocked/fail 保持原结论。验收/写回清单：[b-acceptance-summary-2026-11-24.md](../journal_catalog/core/workbuddy/b-acceptance-summary-2026-11-24.md)、[b-applied-2026-11-24.csv](../journal_catalog/core/workbuddy/b-applied-2026-11-24.csv)。
- B151 写回后的包版本：`custom_toc_journals` **3.7.0（768）**、`magetech_journals` **1.14.0（402）**、`qinyun_journals` **1.7.0（164）**、`rhzh_journals` **1.1.0（311）**、`cnki_cbpt` **1.10.0（821）**、`hep_mirror_journals` **1.1.0（6）**；`supplement_journals` **1.1.1（327，仅同步 2377 状态）**。B151 写回后平台总刊 **2992**。
- 2377 状态：深圳大学学报（人文社会科学版）由 blocked 转 promoted（入 custom_toc），**2377 覆盖 1856/2377（78.1%）**；promoted 959、blocked 518、pending_adapter 3、剩余 521。
- 冒烟 **18/18**；平台 **151 passed + 72 subtests**，包内 custom 19、magetech 12、qinyun 5、rhzh 6、cnki 9、hep 5、supplement 9。
- B151 写回后核心覆盖 **2027/3461（58.6%）**；中文 **1700/3117**、英文 **327/344**；仅在目录 169、版本歧义 **14**、新增候选 **1251**；2377 外 **1133**。
- B151 写回后 backlog 降至 **1265**：A 12、B 75（31 held + 1 rejected + 43 non-ok）、C 163、D 74、E 583、F 357、G 1。
- 来源：8 本 public_platform（3 本 CBPT 门户、3 本 PaperOnce/paperopen 等）和 1 本 HEP 公开镜像，已按 `非官网`/`公开平台`/`采集:公开镜像` 标注；其余为官网页面。6 本首条为目录/封面/献辞/专刊简介（真实文章仍在），2 本可解释 warn（江苏农业科学页面已换期、中国数字医学期望首篇不在本次页面）。
- 31 本 held 已生成 WorkBuddy 桌面任务：`C:\Users\86139\Desktop\WorkBuddy_任务_IDIW_B151待适配31本_2026-11-24.md`；输入 [b-held-2026-11-24.csv](../journal_catalog/core/workbuddy/b-held-2026-11-24.csv)，输出目录 `journal_catalog/core/workbuddy/b-held-rescue-2026-11-24/`。待 WorkBuddy 交付后由主 agent live 验收，不直接采信。
- 修复：`build_core_coverage.py` 的 `read_core_lists()` 现在排除 `b-` 前缀，避免把 `.local/core/b-verify-*.csv` 当核心名单输入。

## 2026-11-24 A34+G6 适配（收尾）

- 6 个只读 agent 探测 A34+G6 共 40 本；主线程逐本 live 复核 27 本（26 pass + 1 warn、0 fail），全部写回并导入。写入清单 [core-a5g6-additions-applied-2026-11-24.csv](../journal_catalog/core/core-a5g6-additions-applied-2026-11-24.csv)。
- `custom_toc_journals` 升 **3.6.0（713）**，新增 26 本；`qinyun_journals` 升 **1.6.0（159）**，新增地质与勘探 1 本。
- 新增通用适配能力：cookie 会话（yiigle 5 本）、按刊 `max_response_bytes`（电子学报 4.5MB）、`section_start_regex`/`section_end_regex`/`last_section_regex` 切段（电子学报/中国出版/中国科学.信息科学/ELIGHT/yiigle/粉煤灰）、`pagination` 分页（粉煤灰 4 页）；qinyun 新增 JS 跳转跟随（地质与勘探）与封面/目录过滤。
- 冒烟：按包抽测 9/9 + 特殊路径补测 5/5，共 **14/14 通过**；测试 custom_toc 19、qinyun 5、平台 **151 passed + 72 subtests**。
- A5G6 批次结束时核心覆盖 **1951/3461（56.4%）**；中文 **1624/3117**、英文 **327/344**；平台总刊 **2916**；当时 2377 覆盖 **1855/2377**，2377 外 **1058**（含 3 本早期内置）。
- A5G6 批次结束时 backlog 降至 **1341**：A 12、B 151、C 163、D 74、E 583、F 357、G 1。A 12 本为纯文本目录/停更/403（中国现代手术学杂志 2018 停更、妇女研究论丛 2025 停更、中国细胞生物学学报 502、网络与信息安全学报 403、出土文献/哲学与文化/天津社会科学/铸造/领导科学/节能技术/钟山/艺术工作无篇级链接）；G1 为外语教学（仅日期噪声），均保留 backlog，不硬加。
- B 151 仍等 WorkBuddy 交付；主 agent 到 B 先暂停验收，不重复跑。未动总包合并、未创建自动扫刊任务、未绕过登录/验证码/WAF。

## 2026-11-24 英文核心刊

- 英文 324 本探测：283 本可读（231 ok_current + 52 ok_current_search）、34 blocked、7 fail；平台以 Springer 98、Elsevier 51、custom 22、SciOpen 14、magtech 13、Nature 8、KeAi 7 为主。
- live 复核后，现有 5 包可吃下 **35 本**（custom 18、rhzh 11、magetech 6）；已写回并导入：`cnki_cbpt` 1.9.0（818）、`magetech_journals` 1.11.0（375）、`custom_toc_journals` 3.1.0（566）、`qinyun_journals` 1.4.0（157）、`rhzh_journals` 1.0.18（307）。入包前每包抽 4 本真实抓取冒烟，**12/12 通过**。
- 英文剩余用 `supplement_journals`（OpenAlex/Crossref，标非官网）兜底：计划 266 本（有 ISSN），ISSN 统一格式化为 `xxxx-xxxx` 后写入 **261 本**，supplement 升到 **1.1.0（327 本目录，maxItems 347）**；5 本 ISSN 不合法跳过。入包前抽 10 本真实抓取冒烟，**9/10 通过**；1 本 `Frontiers of Structural and Civil Engineering` 默认窗口为空（OpenAlex 记录停在 2025-11，调大 `lookback_days` 可返回，已记录）。supplement 包 9 项单测与 `tests_platform` 151 项均通过。
- backlog 适配补充：CMA-CMC 10 本（`magetech_journals` 新增 `a.lunwen` 变体解析，单测 12 项 + 冒烟 5/5）写入 magetech；H 31 本复核后 20 本写回（官网 14、HEP 2、CAST 3、vsb 1），`外语教学` 因仅返回 1 条日期噪声从 vsb 包剔除并保留 backlog；G7 冒烟 7/7。
- A 集群适配（shu/chinawriter/cnj）：6 本写入 `custom_toc_journals`——应用科学学报、运筹学学报（Magtech dqml 变体，`article_link_regex` + `relaxed_title_filter`）、中国当代文学研究（chinawriter 公开平台，标 `非官网`）、气象与环境科学、电子测量与仪器学报、电子测量技术（cnjournals 平台，自定义链接 regex）。custom 升 **3.4.0（579）**，冒烟 **6/6**；芙蓉/花城只有纯文本目录、无篇级链接，未入包，保留 backlog。
- A4 大轮：10 个 agent 覆盖 A 组 154 本，**139 本 ok**（125 ok_current + 14 ok_current_search）、11 fail、4 blocked；126 本有 regex 的中文候选经 custom adapter 逐本实测，**108 pass、5 warn、13 fail**。108 本写入 `custom_toc_journals` **3.5.0（687）**，冒烟 **10/10**；5 warn（中国出版 88 条、中国科学信息科学 148 条等跨期/过采集）与 13 fail 保留 backlog。
- A5G6 批次结束时包：`cnki_cbpt` 1.9.0（818）、`magetech_journals` 1.13.0（392）、`custom_toc_journals` **3.6.0（713）**、`qinyun_journals` **1.6.0（159）**、`rhzh_journals` 1.0.19（309）、`vsb_journals` 1.2.2（12）、`hep_mirror_journals` 1.0.2（5）、`supplement_journals` 1.1.0（327）。
- 核心口径修复：`scripts/build_core_coverage.py` 的 `read_core_lists()` 之前会把 `.local/core/probe-verify-*.csv` 也当成核心名单源，导致分母多出 probe 变体（如“中国水利水电科学研究院学报(中英文)”）。已统一排除 `probe-/review-/core-/sample`，核心并集回到 **3461**，当时覆盖 1810；来源统计、2377 外清单、backlog、学科分布均已重算。
- A5G6 批次结束时核心覆盖 **1951/3461（56.4%）**；中文 **1624/3117**、英文 **327/344**；新增候选 **1326**（中文社科 970、中文理工医 339、英文 17），版本歧义 **15**；当时 2377 覆盖 **1855/2377（78.0%）**，平台总期刊 **2916**，其中 **1058** 本在原 2377 外（含 3 本早期内置）。
- A5G6 批次结束时 backlog 总计 **1341** 本：A 12、B 151、C 163、D 74、E 583、F 357、G 1；G1 为外语教学日期噪声，A 12 为纯文本/停更/403。报告 [core-adapter-backlog-2026-11-24.md](../journal_catalog/core/core-adapter-backlog-2026-11-24.md)。
- 统计报告：[core-coverage-2026-11-24.md](../journal_catalog/core/core-coverage-2026-11-24.md)、[core-source-summary-2026-11-24.md](../journal_catalog/core/core-source-summary-2026-11-24.md)、[out-of-2377](../journal_catalog/out-of-2377-journals-2026-11-24.csv)、[学科分布](../journal_catalog/core/core-discipline-distribution-2026-11-24.md)。

## 2026-11-23 Qoder CN 续跑

- 接续 Qoder CN 会话 `c71db827-8c8e-487d-9847-79c5211d7b1c`：理工医 300 本探测已合并，`verify` CSV 121 行中 **79 本 items>0**；按 parser 写入 5 个包。
- 中文社科续跑：social verify 93 行中 **72 本 items>0**，复核批 18 行中 **12 本 items>0**，合并去重 **84 本**写回 5 个包：`cnki_cbpt` 1.4.0（751）、`magetech_journals` 1.6.0（236）、`custom_toc_journals` 2.6.0（463）、`qinyun_journals` 1.0.8（140）、`rhzh_journals` 1.0.13（251）。5 个新版本已导入平台。
- 第二批（理工医 259 本 + 版本歧义 17 本）：8 个只读 agent 探测 276 本，证据经 live 复核后 **96 本 items>0**（cnki 16、magetech 40、custom 16、qinyun 9、rhzh 15）；5 包升到 `cnki_cbpt` 1.5.0（767）、`magetech_journals` 1.7.0（276）、`custom_toc_journals` 2.7.0（479）、`qinyun_journals` 1.0.9（149）、`rhzh_journals` 1.0.14（266）并导入。
- 第三批（中文社科 400 本）：8 个只读 agent 探测，live 复核后 **91 本 items>0**（magetech 32、custom 20、rhzh 19、cnki 17、qinyun 3；另 1 本 vsb 入口暂未纳入这 5 包）；5 包再升并导入：`cnki_cbpt` 1.6.0（784）、`magetech_journals` 1.8.0（308）、`custom_toc_journals` 2.8.0（499）、`qinyun_journals` 1.1.0（152）、`rhzh_journals` 1.0.15（285）。
- 第四批（中文社科 400 本）：8 个只读 agent；批 3 达 150 轮上限后拆成 3a/3b 各 25 本补跑。400 本中 150 本可读，live 复核 **84 本 items>0**（magetech 33、custom 31、cnki 12、rhzh 6、qinyun 2）；5 包升到 `cnki_cbpt` 1.7.0（796）、`magetech_journals` 1.9.0（341）、`custom_toc_journals` 2.9.0（530）、`qinyun_journals` 1.2.0（154）、`rhzh_journals` 1.0.16（291）。
- 第五批（社科剩余 202 本，8 小批 25-26 本）：115 本可读，live 复核 **76 本 items>0**（magetech 28、cnki 22、custom 18、rhzh 5、qinyun 3）；批 1 因 SSE 传输错误拆 1a/1b 补跑；5 包再升并导入：`cnki_cbpt` 1.8.0（818）、`magetech_journals` 1.10.0（369）、`custom_toc_journals` 3.0.0（548）、`qinyun_journals` 1.3.0（157）、`rhzh_journals` 1.0.17（296）。
- 最新核心刊覆盖 **1485/3461**，新增候选 **1791**（中文社科 1080、中文理工医 387、英文 324），版本歧义 **16**；2377 覆盖率仍 **1855/2377（78.0%）**，平台总期刊 **2449**，其中 591 本在原 2377 外。
- 五批升级包均已导入平台；入包前已用 `scripts/smoke_core_additions.py` 对社科第四批每包抽 4 本（qinyun/rhzh 全部）真实抓取，**19/19 通过**；后续每批 apply 后先冒烟再 import。包级冒烟 cnki/magetech/custom/rhzh 通过，qinyun 东北农业科学当前 502（此前 verify 有 24 条，保留待复测）。`tests_platform` **151 passed, 72 subtests passed**。
- 适配 backlog：已探测但未入包 **1484** 本，已汇总为 [core-adapter-backlog-2026-11-23.csv](../journal_catalog/core/core-adapter-backlog-2026-11-23.csv) 和 [报告](../journal_catalog/core/core-adapter-backlog-2026-11-23.md)：A 优先适配 158、B 可重试 145、C 需 SPA 适配 157、D 仅 PDF 69、E 登录/验证码/WAF 567、F 无官网/其他失败 356、G 已验证只差扩包 1、H 缺复核 31。脚本 `scripts/build_adapter_backlog.py` 会自动发现新的 `probe-results-*` 目录，每批探测后重跑追加；策略是扫完全量核心目录后再按站点集群批量适配 A/G/B，C/D/E/F 默认暂缓或跳过。
- 便携 MariaDB 与研究模式 API 已重启；未启动 Worker/Scheduler，未新增自动任务。
- 统计报告：[core-coverage-2026-11-23.md](../journal_catalog/core/core-coverage-2026-11-23.md)、[core-source-summary-2026-11-22.md](../journal_catalog/core/core-source-summary-2026-11-22.md)、[out-of-2377](../journal_catalog/out-of-2377-journals-2026-11-22.csv)、[adapter backlog](../journal_catalog/core/core-adapter-backlog-2026-11-23.md)。

## 2026-11-22 增量（本次实施）

- 新增 `oa_rss_journals` `1.1.0`：读取期刊官网公开 `/oa/rss.aspx` 当期 RSS，收录 18 本 2377 目录期刊；标签 `采集:官网RSS` + `当期核验` + `目录:2377`。39 本高校 CMS 期刊逐站探测中 18 本 RSS 可解析，《中医眼耳鼻喉杂志》RSS 停在 2012 年，作为源站停更未纳入；其余 21 本为 404/500/非 RSS。另对 1290 本 pending 广扫 `/oa/rss.aspx`，新增《机械与电子》1 本（2026-09）；《江西师范大学学报（自然科学版）》RSS 停在 2023 年，未纳入。另抽测 194 本 magetech pending 的 `/CN/current`：139 失败、55 空，0 本命中，不新增包。
- RSS 解析保留标题、作者、摘要、期次、年份、DOI 和官网文章链接；以“目录/封面/封底/征稿/启事/稿约”结尾的整期目录条目会过滤。包内 4 项单测通过；`vsb_journals` 另有 4 项单测通过；平台 `tests_platform` 148 项通过。
- 平台导入 `oa_rss_journals`（1.0.1 时）结果表 `pkg_data_000015`；临时验证任务 #26 手动运行 #5，`fetched=100`、`inserted=100`、`rejected=0`，100 条覆盖全部 17 本（每本 6 条，最后一本 4 条），验证后已归档；包随后升到 1.1.0（18 本，新增机械与电子）并重新导入。
- 18 本 OA RSS 与 11 本 VSB 从补充包 `pending_journals.json` 标为 `promoted`；回迁清单分别为 [oa-rss-promoted-2026-11-22.csv](../journal_catalog/oa-rss-promoted-2026-11-22.csv) 和 [vsb-promoted-2026-11-22.csv](../journal_catalog/vsb-promoted-2026-11-22.csv)。新增 `vsb_journals` `1.2.0`：VSB sitebuilder 集群 91 本逐站探测，11 本当期目录可直接解析（厦门大学学报哲学社科版、中国粉体技术、东方论坛、外文研究、长江学术、同济大学学报社科版、社会科学家、贵州医科大学学报、职业技术教育、井冈山大学学报社科版、俄罗斯学刊）；同济的文章链接指向超星阅读页，井冈山指向知网，分别标注 `文章页:超星`/`文章页:知网`。平台导入结果表 `pkg_data_000016`，临时任务 #27 手动运行 #6（当时 6 本）`fetched=78`、`inserted=78`、`rejected=0`，验证后已归档；包随后扩到 1.2.0（11 本）并重新导入。
- 新增 `hep_mirror_journals` `1.0.0`：qinyun 批 3 探测发现郑州大学学报（工学版）、重庆医科大学学报、重庆邮电大学学报（社会科学版）在 HEP 中国高校科技期刊集群公开镜像有当期目录；文章链接和标题可读，但明确标注 `采集:公开镜像` + `非官网` + `当期核验` + `目录:2377`，结果表 `pkg_data_000017`。HEP 仅作为官网超时/412/WAF 时的公开镜像，不下载全文。
- `magetech_journals` 升到 `1.2.0`：新增《科学技术与工程》1 本，读取官网公开 JSON 当期 API（2026年31期 36 篇；抽样前 5 条标题/作者/DOI/摘要正常），共 159 本。qinyun 批 3 另有《美术教育研究》只有 TOC 文本、无文章级链接，未纳入；《福建轻纺》《自动化与仪器仪表》无当期，高教学刊为 CNKI 登录墙。
- `qinyun_journals` 升到 `1.0.4`：新增 9 本新版勤云当期目录（创意设计源、华南农业大学学报社科版、南开管理评论、右江民族医学院学报、河北北方学院学报社科版、湖南工业大学学报及其社科版、现代远程教育研究、生物化学与生物物理进展），支持显式 `current_url` 和内嵌 JSON 目次；9 本全部实测 11–26 篇，共 118 本。
- `magetech_journals` 升到 `1.2.1`（162 本）：新增中国农业资源与区划、中国图象图形学报、电讯技术 3 本当期 HTML；中国卫生政策研究连接被重置、工程科学与技术当期页无可解析文章，继续留 pending。
- 新增 `custom_toc_journals` `1.0.0`：qinyun 批 1/2 的 4 本自定义 CMS 当期页（乐府新声、国际城市规划、应用昆虫学报、北方园艺）全部实测可解析，结果表 `pkg_data_000018`；来源标签 `采集:官网当期目次` + `当期核验` + `目录:2377`。
- `cnki_cbpt` 升到 `1.0.3`（515 本）：CBPT 复核 134 条候选，仅 6 本 `type_benqi` 返回真实文章；其余 500/空页不纳入。新增湖南师范大学教育科学学报、唐史论丛、哲学动态、内蒙古师范大学学报（哲社/自科）、原生态民族文化学刊。
- `custom_toc_journals` 升到 `1.1.1`（9 本）：追加 founder 批 3 的 5 本独立当期页（辐射研究与辐射工艺学报、遥感学报、针刺研究、铁道科学与工程学报、高分子学报）；通信与信息网络学报、高压电器首页当期区会混入历史文章，未纳入。
- rhzh 探测发现《光电工程》官网 `/oee/article/current` 可读 15 篇，但旧 RHZH 解析器路径不匹配；已加入 `custom_toc_journals` 1.1.2（10 本），其余 rhzh 站点仍待复核。
- founder 批 2：16 本方正经 rc-pub 全链路实测（家政学刊、机械传动/强度、机车电传动、软件导刊等）加入 `founder_journals` 1.0.1（36 本）；山东大学学报哲社版、当代美术家 2 本静态 TOC 加入 `custom_toc_journals` 1.1.3（12 本）。
- founder 批 1：9 本方正 rc-pub 加入 `founder_journals`（45 本）；中南大学学报医学版、中国毕业后医学教育、中山大学学报医学版/自然科学版、人权、光学精密工程、发电技术 7 本静态 TOC 加入 `custom_toc_journals`（19 本）。
- CBPT `official_issue_page` 19 条复核后 9 条真实返回文章（天津理工大学学报、宏观质量研究、南大法学、东北师大学报哲社、江苏建筑职院学报、河南工程学院学报社科、江西农业大学学报、衡阳师范学院学报、许昌学院学报）加入 `cnki_cbpt` 1.0.4（524 本）。
- RHZH 两批复核：batch2 51 本 ok 中 43 本真实解析，batch1 52 本 ok 中 47 本真实解析，共 90 本加入 `rhzh_journals` 1.0.6；再补上海海事大学学报 current-data API，`rhzh_journals` 1.0.7 共 231 本。修复 `article-list` 空 id 解析，并保留 `current_url` 证据。
- CBPT 批 3：12 本 WKD 公开当期目次（透析与人工器官、郑州大学学报哲社、陶瓷研究、青海社会科学、食物经济与管理、马克思主义哲学研究、高师理科学刊、高等教育评论、鹿城学刊、黄河文明与可持续发展、黑龙江大学自然科学学报、齐鲁石油化工）加入 `cnki_cbpt` 1.0.6（536 本）；通信技术 type_benqi 实时复核 0 条，已撤回 pending。
- CBPT 批 1/2：73 + 67 本 WKD/门户当期页加入 `cnki_cbpt` 1.0.8（676 本）；26 + 6 本验证码/登录墙记为 blocked。通信技术 type_benqi 实时复核 0 条仍 pending。
- CNKI/CBPT 收口：CBPT WKD/门户当期页加入 `cnki_cbpt` 1.0.9（677 本）；CNKI 公开 portal/Magtech/PDF 当期页加入 `custom_toc_journals` 1.4.0（100 本）；VSB/RHZH 剩余未发现新的安全批量入口。
- CNKI 剩余近失中再补中华护理杂志、中国建设信息化、中国瓜菜、内科理论与实践 4 本，加入 `custom_toc_journals` 1.4.1（104 本，journal_keys 上限同步调到 200）。
- qinyun 批 1：上海商业、唐山学院学报入 `custom_toc_journals` 1.4.2（106 本）；70 本登录/无公开当期标 blocked。
- qinyun 批 3：43 本 CNKI WKD 当期页全部 live 通过，加入 `custom_toc_journals` 1.5.0（149 本）；27 本登录/验证码/无公开当期标 blocked。
- qinyun 批 2：48 本公开门户/WebPublication 当期页加入 `custom_toc_journals` 1.6.0（197 本）；13 本 blocked 回填，山西林业首页新闻排除。
- 其他来源批 1：10 本公开门户/当期页加入 `custom_toc_journals` 1.7.0（207 本）；2 本验证码/403 标 blocked。
- 其他来源批 2：工业工程、电气工程学报、植物保护学报 3 本 live 可解析，分别加入 RHZH/通用 TOC；Yiigle 13 本与部分 RHZH 仍因 302/SSL 不入包，3 本 blocked 回填。
- magetech 批 1：30 本公开 `/CN/current`/CMA-CMC 当期页 live 通过，加入 `custom_toc_journals` 1.8.0（238 本）；3 本维护/502 标 blocked，其余超时/停更留 pending。
- misc 小批：无线互联科技、西亚非洲、财贸经济 3 本加入 `custom_toc_journals` 1.8.1（241 本）；中国医院建筑 302 未纳入。
- magetech 批 4：15 本公开当期页加入 `custom_toc_journals` 1.9.0（256 本）；8 本维护/502 标 blocked，4 本 fail 留 pending。
- magetech 小批 1：6 本可重新解析（中国农业科技导报、中国医学科学杂志英文版、中国医学创新、北京化工大学学报、中国家禽、作物学报）加入 `custom_toc_journals` 1.9.1（262 本）。
- magetech 小批 2：10 本可重新解析，加入 `custom_toc_journals` 1.9.2（272 本）；2 本维护/502 标 blocked。
- blocked 448 中 45 本可复核候选完成公开入口复测：**12 本**恢复并入包，**33 本**保留 blocked 并记录复测原因（403/412/WAF、登录/验证码、5xx/维护、超时、首页无当期等），不绕过任何访问限制。回迁清单 [blocked-retry-promoted-2026-11-22.csv](../journal_catalog/blocked-retry-promoted-2026-11-22.csv)。
- `custom_toc_journals` 升到 **2.2.0（382 本）**：blocked 复测新增 11 本；pending_adapter 探测回迁 37 本；剩余 35 本二次深挖再回迁 23 本（外国文学研究、大理大学学报、教育科学、文史哲、曲靖师范学院学报、武汉体育学院学报、海关与经贸研究、竞争情报、统计理论及其应用、联勤军事医学、肝癌电子杂志、高等学校计算数学学报（英文版）、南昌大学学报（工科版）、哈尔滨医药、固体力学学报、图书馆建设、实用临床医学、应用心理学、地质学报、钢铁研究学报、大连医科大学学报、水产学杂志、经济科学）。解析器新增 `/EN/10.x`、`/CN/Y2026/...` 文章链接、公开 JSON 列表 API（`json_api`）、onclick 文章页（`onclick_link`）、过刊索引取最新一期（`issue_link`）、相对链接基址（`link_base`）、按刊链接正则（`article_link_regex`）、表格“标题+摘要链接”配对（`pair_link`）、过刊索引跳过空期（`require_articles`）、JSON API 页面参数解析（`params_from_page`/`api_url_template`）、文章 URL 模板与作者对象数组；过滤 `[Abstract]`/`[Cited by]`/编委会/摘要计数等导航标签。
- `magetech_journals` 升到 **1.3.1（171 本）**：新增管理学报（显式 `current_url`）、仿生工程学报（旧版模板）、《化学进展》（`api_mode=stae` 读取 magetech 3.0 JSON API）；pending_adapter 回迁 8 本。
- `founder_journals` 升到 **1.1.0（90 本）**：新增武汉大学学报（理学版）、通信与信息网络学报（英文）、通信学报、野生动物学报，全部走方正 rc-pub JSON API；海洋科学集刊停在 2017 年，未纳入。
- `cnki_cbpt` 升到 **1.1.1（684 本）**：新增中国心血管杂志、湖南邮电职业技术学院学报、疑难病杂志、蚕业科学、铁合金、防爆电机（CBPT 公开门户 `type_benqi`），以及迁移到 CNKI 腾云新站的南昌大学学报（人文社会科学版）。
- pending_adapter 165 本完成 5 批公开入口探测与复核：**55 本**入包（custom_toc 37、magetech 8、founder 4、cnki_cbpt 6），**75 本**转 blocked（登录/验证码/WAF、停更/旧期、TLS 证书异常、无公开当期）。回迁清单 [pending-adapter-promoted-2026-11-22.csv](../journal_catalog/pending-adapter-promoted-2026-11-22.csv)。
- 剩余 35 本 pending_adapter 二次深挖（5 批并行规格探测）：**24 本**入包（custom_toc 23、cnki_cbpt 1），**8 本**转 blocked（方正空壳 SPA、停更、TLS 证书链缺失、仅纯文本/封面无文章入口），**3 本**保留 pending_adapter（管理科学当期页停在 39(3)；地下空间与工程学报、心理与行为研究官网超时）。回迁清单 [pending-adapter-promoted-round2-2026-11-22.csv](../journal_catalog/pending-adapter-promoted-round2-2026-11-22.csv)。
- 2377 目录覆盖更新为 **1855/2377（78.0%）**，累计回迁 **958** 本，剩余 **522** 本（blocked **519**，pending_adapter **3**）。
- 6 个仅当期包新增 `keywords` 模式（**仅对当期目次做本地关键词过滤，不是全刊检索**）：`custom_toc_journals` 2.2.1、`founder_journals` 1.1.1、`paperonce_journals` 1.0.2、`oa_rss_journals` 1.1.1、`vsb_journals` 1.2.1、`hep_mirror_journals` 1.0.1。匹配标题/摘要/作者/DOI；query 多词按 AND、aliases 按 OR；默认仍为 `latest_issue`。6 包 keyword 单测 15/5/5/5/5/5 项通过。
- 平台期刊选择器按 `package_key` 注入能力标签，并可直接筛选：`能追新期，也能搜关键词`（原始五包）、`能追新期，只能筛本期`（custom_toc/founder/paperonce/vsb）、`能追订阅，只能筛订阅`（oa_rss）、`能追镜像，只能筛镜像`（hep_mirror）、`只能查论文摘要`（supplement）、`只能搜旗舰刊`（flagship）；筛选框改为“标签筛选/全部标签”。平台回归 `149 passed, 72 subtests passed`。
- 所有期刊包只采集元数据（标题/作者/摘要/DOI/期次/文章 URL）并写入 MySQL 文本结果表，**不下载 PDF**；`magetech_journals` 仅保存 `pdf_url` 链接字段，不会抓取文件。历史全量期次枚举（“一键全历史”）尚未实现，当前只有“当期目次”和“关键词检索/当期关键词过滤”。
- 采集包名称后新增“说明”小标签，鼠标悬停显示白话解释（覆盖已安装的 16 个采集包）；`/api/v1/packages`、`/api/v1/monitors/<id>/packages`、`/api/v1/assistant/catalog` 均返回 `help` 字段，任务创建/来源设置/助手来源页均已展示。平台回归 `150 passed, 72 subtests passed`。
- 国内核心刊覆盖框架：新增 `scripts/build_core_coverage.py`，读取 `.local/core/*.csv`（CSSCI/CSTPCD/CSCD/北大核心等），按 ISSN/CN/刊名与现有 1858 条包内刊、2377 目录匹配，输出已入包/仅在目录/歧义/新增候选，并按核心级别、学科、现有包、采集模式、元数据/PDF 能力分类。核心名单仅在本地研究使用，报告会标注 official/reference。
- 国内核心刊补录：CSSCI 909、CSTPCD 2218、CSCD 1341、北大核心 1987（均公开转载参考版）合并去重 **3461** 本；与现有包精确匹配后 **已入包 975、仅在目录 170、版本歧义 28、适配复核剩余 5、新增候选 2288**（中文社科 1405、中文理工医 559、英文 324）。累计补入 **81** 本：cnki_cbpt 21、magetech 22、custom_toc 30、qinyun 7、rhzh 1；复核 23 本已入包，5 本仍待适配。同时修复 CBPT WKD `paperID` 解析和 magetech 新版 `/CN/Y...` 当期模板回退。报告 [core-coverage-2026-11-22.md](../journal_catalog/core/core-coverage-2026-11-22.md)、[入包计划](../journal_catalog/core/core-additions-ready-2026-11-22.csv)、[复核剩余](../journal_catalog/core/core-review-remaining-2026-11-22.csv)。包版本：cnki_cbpt 1.2.0、magetech_journals 1.4.1、custom_toc_journals 2.4.0、qinyun_journals 1.0.6、rhzh_journals 1.0.11。
- 2377 外期刊登记：平台现有 **84 本**不在原 2377 目录（81 本核心补录 + 3 本早期内置：数据分析与知识发现、图书情报工作、软件学报）；`qbzl` 是 2377 内《情报资料工作》的别名，不重复计。清单 [out-of-2377-journals-2026-11-22.csv](../journal_catalog/out-of-2377-journals-2026-11-22.csv)，平台总数因此为 **1939**，2377 覆盖率仍为 **1855/2377（78.0%）**。
- 核心刊来源统计：新增 `scripts/summarize_core_sources.py`，按核心名单（CSSCI/扩展、北大核心、CSTPCD、CSCD）、平台/供应商、学科、优先级、名单质量输出统计，供后续排期使用。当前：3461 本核心刊，已入包 975、仅在目录 170、版本歧义 28、适配复核剩余 5、新增候选 2288；按平台待探测 2288、CNKI CBPT 274、自定义 CMS 201、仁和 158、玛格泰克 134、勤云 77、方正 54、PaperOnce 37 等。报告 [core-source-summary-2026-11-22.md](../journal_catalog/core/core-source-summary-2026-11-22.md)、[JSON](../journal_catalog/core/core-source-summary-2026-11-22.json)。

### 期刊包元数据与 PDF 能力（2026-11-22 核对）

| 包 | 数据来源 | 主要元数据 | 摘要 | DOI | PDF |
|---|---|---|---|---|---|
| magetech_journals | HTML/JSON | 标题/作者/摘要/DOI/年卷期页 | 有 | 有 | **保存 pdf_url 链接，不下载文件** |
| founder_journals | 方正 JSON API | 标题/作者/摘要/DOI/年/期/页 | 有 | 有 | 当前不提取 |
| paperonce_journals | PaperOnce JSON API | 标题/作者/摘要/DOI/年/期 | 有 | 有 | 当前不提取 |
| qinyun_journals | HTML/JSON | 标题/作者/摘要/DOI/年 | 多数有（模板差异） | 有 | 当前不提取 |
| rhzh_journals | HTML/JSON | 标题/作者/摘要/DOI/年 | 有 | 有 | 当前不提取 |
| sancai_journals | HTML/JSON | 标题/作者/摘要/DOI/年 | 有 | 有 | 当前不提取 |
| cnki_cbpt | CBPT 门户 HTML | 标题/作者/摘要/期 | 有 | **无 DOI 字段** | 当前不提取 |
| custom_toc_journals | HTML + 部分 JSON API | 标题/文章 URL；JSON 类加作者/DOI/年/期 | 普通 HTML 通常无；JSON 类也多为空 | 仅 JSON 类 | 当前不提取 |
| vsb_journals | HTML | 标题/文章 URL | 无 | 无 | 当前不提取 |
| hep_mirror_journals | HTML 镜像 | 标题/文章 URL | 无 | 无 | 当前不提取 |
| oa_rss_journals | RSS XML | 标题/作者/摘要/年/期 | 有（视 RSS） | 视 RSS | 当前不提取 |
| supplement_journals | OpenAlex/Crossref | 标题/作者/单位/摘要/DOI/年卷期页/OA/被引 | 有 | 有 | 元数据源，无 PDF |
| flagship_journals | OpenAlex/Crossref | 标题/作者/单位/摘要/DOI/年卷期页/OA/被引 | 有 | 有 | 元数据源，无 PDF |

PDF 结论：**平台目前不抓取、不保存 PDF 文件**；只有 `magetech_journals` 会把 PDF 下载地址存成 `pdf_url` 字符串。其他包即使文章页有 PDF，也没有提取或下载。后续做核心刊覆盖报告时，会增加 `meta_source`（JSON/HTML/RSS/OpenAlex）和 `pdf_status`（有链接/无链接）两列。

## 2026-11-21 增量（本次实施）

- `magetech_journals` 升级到 `1.1.2`：新增 `collect_mode: keywords | latest_issue`，当期目次读取 `/CN/current`；实测《数据分析与知识发现》13 条；抽查中央音乐学院学报 11 条、中国临床护理 12 条、中国消毒学杂志 16 条，可回收部分 403/分页停滞站；华南理工自然科学版、中国农业气象当期页可访问但暂无可解析文章。
- `cnki_cbpt` 升级到 `1.0.2`：新增 `collect_mode`，当期目次读取 `paper_list/type_benqi` 并跟随 `paperPage_list` 分页；实测三峡大学学报（人文社会科学版）16 条、哈尔滨体育学院学报 14 条；潮学研究仍为 HTTP 500，属服务端故障。
- `rhzh_journals` 升级到 `1.0.2`：新增 `collect_mode`，依次尝试 `/cn/article/current`、`/article/current`、`/cn/article/latest`，复用 `article-list` 解析；实测上海工程技术大学学报 10 条，并过滤“目次/封面”条目。
- `sancai_journals` 升级到 `1.0.2`：新增 `collect_mode`，当期模式读取 `api/api/Web/LastIssueList`；实测合肥师范学院学报 10 条。
- 新增 `supplement_journals` `1.0.2`（补充期刊包）：可运行部分为 2377 外文组中的 66 本 OpenAlex/Crossref 刊，UI 明确标注 `采集:OpenAlex/Crossref` + `非官网`，文章元数据不是从官网页面爬取；另有 1480 本 2377 未适配刊保存在包内 `pending_journals.json`（2026-11-21 已回迁 173 本，剩余 1307 本；其中 PaperOnce 69 本另建 `paperonce_journals` 1.0.0，北大方正新平台 20 本另建 `founder_journals` 1.0.0，勤云 5 本回到 `qinyun_journals` 1.0.3），UI 标注 `采集:待适配` + `官网候选` + `目录:2377`，详细的供应商/模板来源保留在 JSON 字段，暂不参与调度；清单见 [补充包暂存清单](supplement-journals-2026-11-21.md)。原 `openalex_journals` 包已删除；用户任务 #4“人工智能”已迁移到补充包，旧演示任务 #3 及其数据已清理。新增回迁记录见 [journal-promotion-2026-11-21.md](journal-promotion-2026-11-21.md)。
- 2026-11-21 回迁结果：79 本当期目次验证刊加入 `magetech_journals` 1.1.4（158 本）、`rhzh_journals` 1.0.4（140 本）、`sancai_journals` 1.0.3（2 本）；2377 目录内覆盖 1070/2377，剩余 1307 本。CBPT 本批 80 本全部 HTTP 500，暂不硬加；PaperOnce 69/75、北大方正新平台 20/25、勤云 5/262 回迁。
- 新增抽样诊断报告 [remaining-journal-diagnosis-2026-11-21.md](remaining-journal-diagnosis-2026-11-21.md)：北大方正/PaperOnce 多为 SPA + 公开 JSON API，不是验证码；南京航空航天大学学报出现 HTTP 412 + 空 DOM，属强前置校验；PaperOnce 正确 API 前缀为 `/api/api/`。
- 全量回归补充：RHZH `latest_issue` 在上海工程技术大学学报取得 10 条；工程科学学报当期页只有占位 `article-list`，会明确告警，keywords 模式正常。该 API-only 站点需后续补 issue API，不能把 RHZH 当期模式理解为全目录可用。
- 验证：magetech 9 项、CBPT 8 项、RHZH 6 项、Sancai 3 项、PaperOnce 4 项、北大方正 4 项、勤云 3 项、补充包 9 项单测通过；平台 `tests_platform` 118 项通过。勤云 `qinyun_journals` 的 `latest_issue` 尚未实现（新旧 ASP.NET/新版模板差异较大），留作下一批；新验证的 403/分页停滞刊也尚未自动加回中文包目录，需按刊复测后再加入。


本次仅同步文档，未重跑全源采集、未修改业务代码、未创建任务、未重启服务。网络可用性、目录规模和测试数字均注明最近验收时间，不代表每天自动复核。

## 一、当前架构

- 平台采用可插拔爬虫工具包架构：导入、参数校验、独立环境、进程执行、队列、调度、去重入库和查询 API 由平台管理。
- 源码位于 `crawler_packages/<category>/<package_key>/`；安装文件位于 `crawler_platform_runtime/packages/<category>/<package_key>/<version>/<digest>/`。不能直接修改已安装的旧版本文件，升级需增加包版本并重新导入。
- 六类目录为 `news`、`academic`、`patents`、`reference`、`entities`、`community`，目录分类不等于插件的检索能力。
- 数据存入 MySQL，每个采集包独立一张结果表，表名由平台分配为 `pkg_data_<id>`。不回到旧系统的“新闻/论文/专利各一张业务表”方案。
- 当前源码中的固定平台表共 10 张，含内部版本表：`crawler_packages`、`monitors`、`monitor_packages`、`monitor_runs`、`package_runs`、`monitor_resource_matches`、`proxy_endpoints`、`proxy_run_assignments`、`weekly_reports`、`schema_migrations`；另加各包的结果表。
- 平台当前使用 Python 3.14。平台与包的解释器小版本仍需匹配，尚未实现多 Python 运行时自动选择或容器调度。

## 二、已完成

| 项目 | 已有实现与最近证据 | 边界 |
| --- | --- | --- |
| 任务归档、恢复 | 2026-11-06 已落库并上线；归档停止后续采集和周报，历史结果、匹配和运行记录保留；恢复默认停用 | 正在采集或生成周报时需等待结束才能归档，不做任务硬删除或删结果表 |
| 未归档任务名称唯一 | Unicode 规范化、空格合并和大小写折叠后计算名称指纹，数据库唯一索引兜底；同关键词仅提醒 | 不同名称、相同主题可建立不同任务；不做装备名/主题实体自动合并 |
| 数据预览分页 | 2026-11-06 已完成每组 10 页、页码点击、输入页数跳转；保留任务、来源和标题筛选 | 本次未更改底层分页查询方式 |
| DeepSeek 对话建任务 | 独立 `/assistant` 页面；支持对话生成并修改新任务草案、来源参数、别名、北京时间计划；只有检查并二次确认后才创建 | 模型不能直接访问数据库、运行命令、修改旧任务或启动采集；会话仅在当前页面内存 |
| 助手草案校验 | 校验来源能力、参数 Schema、名称、周期、上限；确认凭据有效 15 分钟并绑定草案与插件版本；修改后重检 | 对“所有期刊”等语义要求仍缺少硬性校验，见下文 |
| 助手能力目录 | `configs/assistant-source-profiles.json` 区分 `keyword`、`feed`、`identifier`、`site`；未知能力或含敏感配置的包不自动开放给助手 | 目前为平台侧配置，未扩展成新版插件协议 |
| 助手七场景实测 | 2026-11-06 使用 9 次真实 DeepSeek 调用，7 项实际建库、回读参数，5 项完整满足配置要求、2 项部分满足；测试任务 #14–#20 均已停用归档，运行记录为 0 | 这是任务配置验收，不是爬取数量、相关性、摘要获取率或长期成功率测试 |
| Google 新闻 RSS 别名修复 | 2026-11-08 已正式升级到 `1.0.3`；主词与去重后的别名逐项请求，交错合并、按编号/相同 URL 去重，共用总上限；失败保留部分结果并告警 | 旧版 `1.0.2` 只使用主 `query`；历史运行不会自动补采；各词沿用任务的语言和地区设置 |
| Google RSS 真实验收 | 主词“科学智能”及别名“AI for science”“AI4S”分别返回 49、35、38 条；合计上限 12，最终有 5 条仅来自别名；正式安装环境另测主词＋别名成功返回 6 条 | 结果只保留在验收输出中，未写文章数据库、未创建监控；请求数随词数增长且受执行截止时间限制 |
| Google 包升级保留性 | 2026-11-08 核对结果表仍是 `pkg_data_000003`，9 项任务来源配置及默认配置摘要未变，环境 Python 3.14.7 健康 | 后续新运行使用新包；不需要重建已有任务 |

任务归档相关迁移为 `crawler_platform/migrations/004_monitor_archive.sql`。DeepSeek 助手和别名修复没有新增数据库表。

## 三、此前已接入的能力

- 百度百科、Wikipedia、Google 新闻 RSS、新浪新闻、通用 RSS、USPTO 专利号查询，以及中外文期刊包已有代码和导入/验收记录。
- 五个中文期刊包在 2026-11-06 的正式平台目录验收中均已安装，不再是旧 README 所写的“尚未导入”：

| 中文期刊包 | 目录条目 | 默认选中 | 参数声明的单包选刊上限 |
| --- | ---: | ---: | ---: |
| 玛格泰克 `magetech_journals` | 98 | 3 | 30 |
| CBPT `cnki_cbpt` | 509 | 3 | 30 |
| 勤云 `qinyun_journals` | 104 | 1 | 30 |
| 仁和汇智 `rhzh_journals` | 122 | 1 | 30 |
| 西安三才 `sancai_journals` | 1 | 1 | 3 |
| 合计 | 834 | 9 | 不可直接视作一个任务能选择全部 |

以上为各包目录条目，未跨包去重，不代表 834 本独立期刊今天都可访问、都能返回足量文章。历史逐刊筛选和容量测试见目录内对应审计文档。

- 外文重点期刊包提供 Nature、Science、PNAS、Cell 公开元数据检索及摘要等字段；它不是 WoS、Scopus 或 Google Scholar 全库检索。
- USPTO 已完成按已知专利号查询的历史验收；本次文档同步未重测其最新访问和授权状态，不能将历史成功当成持续可用的保证。
- 通用 RSS 已有多地址配置和历史主题验收；不是所有网站的全库搜索，也不保证完整正文。
- 北京时间每日/每周调度、队列、租约和失败恢复已有实现与测试；此前已做加速冒烟及真实时刻触发验收，连续多自然日的真实运行仍应持续检查，不能仅凭手动成功认定长期稳定。
- 平台级代理池和 DeepSeek 证据引用周报已有实现。代理包侧遵守标准代理环境变量才能生效；周报与任务助手是独立功能。

## 四、已发现但尚未修复

### P1：助手的全部期刊范围未真正落实

- 用户要求“所有已接入中文期刊”时，助手选择了五个包，但最终落库仍是默认的 9 个条目，约为 834 个目录条目的 1.1%。
- 助手文本还出现“4 个包/实际 5 个包”“journal_keys 留空/实际合并默认值”等不一致。
- 模型承认看不到完整目录，草案却仍能通过结构校验并允许确认，说明当前校验只保证参数合法，不保证需求覆盖完整。
- 改进方向：平台确定性解析“全部/标签/指定期刊”范围，预览实际选中数和未覆盖数；超出单包上限应阻止确认或规划分批，不能静默退回默认选择。尚未实施。

### P1：等义词与相关概念混用

- “军事智能体”被扩展为 `autonomous weapons`、`intelligent unmanned systems` 等更宽泛的相关类目，并进入独立 OR 匹配。
- 本轮仅检查任务配置，没有实际采集，不能给出这组新扩词的误收率。
- 改进方向：分开原词、等义翻译、同义词、相关概念；相关概念默认不启用，用户确认后才增加。尚未实施。

### P1：检索逻辑尚未统一

- 现有任务仍是一个主 `query` 加 `aliases`，并非统一的布尔检索计划。
- Google RSS 的别名遗漏已经在 `1.0.3` 修复，不再列为未完成事项。
- 通用 RSS 的单词、别名、关键词组目前仍并列 OR：只命中主词即可通过，可能绕过用户想表达的 AND 组。
- 尚未实现统一 AND/OR/NOT、字段约束、跨语言分组、按来源编译/降级和统一匹配解释。
- `query_plan_json` 只是已讨论的设计建议，当前未增加该字段，也未修改插件请求协议。
- 改进方向：先修 RSS 组合逻辑，再设计版本化结构检索计划和来源能力适配；不得承诺简单来源的多次检索等价于数据库原生布尔检索。尚未授权落地整套方案。

## 五、UI 改版状态

- 2026-11-08 按用户要求生成了“大模型辅助”桌面视觉稿：左右分栏、角色头像与消息气泡、标签式别名、来源删除/添加、弱化参数操作、底部固定检查和创建入口。
- **仅生成图片，尚未按新稿修改前端代码。**
- 现有页面的别名仍是每行一项的文本框，参数仍是弹窗，不是侧边抽屉；已有“检查配置/确认创建”按钮，但还没有按视觉稿固定吸底。
- 图片中的标签回车添加/点击删除、来源行删除/添加、AI 更新字段高亮等新交互不能视为已上线能力。
- 本轮不要求手机适配；后续仍以桌面端管理效率和现有平台风格为准。

## 六、验证与运行入口

- 最近完整代码回归：2026-11-22，`151 passed, 72 subtests passed`；同时 `custom_toc_journals` 15 项、`founder_journals` 5 项、`paperonce_journals` 5 项、`oa_rss_journals` 5 项、`vsb_journals` 5 项、`hep_mirror_journals` 5 项、`magetech_journals` 11 项、`cnki_cbpt` 9 项、`qinyun_journals` 3 项、`rhzh_journals` 6 项包内单测通过。
- Google 正式包 `1.0.3` 独立 Python 环境冒烟：退出码 0、状态 `completed`、6 条结果、协议数量一致、无警告，未写入业务数据库。
- 最近记录的服务检查：2026-11-08，`/health/live`、`/health/ready`、`/assistant` 返回 200，三个 Windows 后台任务显示 Running。2026-11-09 编写本文件时未重新做服务或全源网络验收。
- 平台地址：`http://127.0.0.1:8090/monitors`；助手：`http://127.0.0.1:8090/assistant`。
- 后台任务名：`IDIW-OSINT-serve`、`IDIW-OSINT-scheduler`、`IDIW-OSINT-worker`。启动前先检查，避免重复实例；此前出现过旧 API 进程仍响应的问题，已在当次重载时清理，启动/重载机制的单实例保障仍值得规范。
- 真实模型调用会产生 API 费用；本地单元测试使用模拟响应。`.env` 和密钥不写入文档或报告。

```powershell
.\.venv\Scripts\python.exe -m pytest tests_platform -q -p no:cacheprovider
```

测试中的真实临时虚拟环境用例曾在沙箱特殊临时路径下触发 pip 启动失败，在正常 Windows 临时目录下全量通过；应将该环境因素与业务功能失败区分。

## 七、建议的下一步

1. 优先补助手的覆盖范围硬校验、实际选刊数展示及文本/配置一致性，防止合法但不满足需求的草案被确认。
2. 区分同义扩词与相关扩词，修复 RSS 组合逻辑，使用正反例检验真实匹配效果。
3. 按用户确认后的视觉稿实施助手 UI；目前仍处于设计预览阶段。
4. 再推进统一检索计划、来源编译和组合检索编辑器，控制额外子查询数量和运行预算。
5. 持续验收真实跨日调度与失败恢复；复查外部来源访问状态。对外部署前完善鉴权、访问控制、备份和单实例服务管理。
6. 如需要“一键全历史”，为标准平台增加 `archive` 模式（按期枚举、时间范围/期数上限），自定义 CMS 逐站适配；只存元数据与文章 URL，不下载 PDF。

上述是待办与建议，不表示已实施，也不替代用户对下一轮工作的确认。

## 八、证据与代码索引

- [助手七场景完整报告](../reports/assistant-evaluation-20261106-224559.md)；[原始记录](../reports/assistant-evaluation-20261106-224559.json)。
- [Google RSS 实网验收记录](../reports/google-news-rss-aliases-20261108-115859.json)；[包说明](../crawler_packages/news/google_news_rss/README.md)。
- [助手服务](../crawler_platform/assistant.py)、[助手页面逻辑](../crawler_platform/task-assistant.js)、[能力目录](../configs/assistant-source-profiles.json)。
- [Google RSS 回归测试](../tests_platform/test_google_news_rss.py)、[助手回归测试](../tests_platform/test_assistant.py)、[任务归档回归测试](../tests_platform/test_monitor_archive.py)。
- [每日定时采集部署](daily-scheduled-collection.md)、[周报说明](weekly-intelligence-reports.md)。
- [中文期刊目录清理](journal-catalog-pruning-2026-10-30.md)、[供应商逐刊审计](supplier-journal-audit-2026-10-26.md)。
- [10 月历史待办快照](current-todo-2026-10-13.md)：部分问题已完成，以本文件的新状态为准。
