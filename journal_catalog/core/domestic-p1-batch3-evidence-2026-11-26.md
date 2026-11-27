# 国内 P1 81–196 探测证据汇总（2026-11-26）

- 证据来源：`.local/domestic-p1-batch3/agent01..12.csv/md`（只读探测；共 116 本，前 11 组 10 本、末组 6 本）。
- 探测边界：公开页面只读；未登录、未绕验证码/WAF、未下载 PDF；未改包/DB/任务，未 commit。
- 复核口径：写回前均用各包生产 parser live 复核；本表只记复核通过项。

## 0. 结论速览

- 原始 status：blocked 17 / fail 11 / login 2 / no_current 13 / ok 43 / pdf_only 4 / warn 26
- 分诊：**写回 42 / 待定 31 / 不可写回 43**。
- 写回 42 本：custom_toc 15、cnki 15、rhzh 6、magetech 4、vsb 1、sancai 1；覆盖 yiigle 医学刊 9 本、CNKI WK*/portal 15 本、仁和/玛格泰克/三才/VSB 其余。
- parser 修补：custom_toc 增加 yiigle `section_start_regex` 用法、pair_link `url_template`、目次/封面噪声过滤与“浏览次数”标题清理；magetech 支持 `/CN/abstract/abstractN.shtml` 并过滤封面目次；sancai 新增郑大医学版 API 站点。

## 1. 写回清单（生产 parser live 复核）

| 排名 | 期刊 | 包 | live 条数 |
|---:|---|---|---:|
| 81 | 铁道标准设计 | cnki_cbpt | 27 |
| 84 | 航空材料学报 | magetech_journals | 12 |
| 90 | 地下空间与工程学报 | magetech_journals | 37 |
| 94 | 河南师范大学学报(自然科学版) | custom_toc_journals | 19 |
| 100 | 兰州大学学报(自然科学版) | cnki_cbpt | 17 |
| 102 | 磁共振成像 | custom_toc_journals | 28 |
| 111 | 郑州大学学报(医学版) | sancai_journals | 37 |
| 116 | 航天返回与遥感 | custom_toc_journals | 14 |
| 126 | 听力学及言语疾病杂志 | cnki_cbpt | 22 |
| 129 | 热加工工艺 | rhzh_journals | 33 |
| 131 | 中华显微外科杂志 | custom_toc_journals | 22 |
| 133 | 电子元件与材料 | custom_toc_journals | 20 |
| 135 | 华侨华人历史研究 | cnki_cbpt | 14 |
| 136 | 腐蚀与防护 | rhzh_journals | 15 |
| 137 | 高等学校化学学报 | magetech_journals | 19 |
| 138 | 中华眼科杂志 | custom_toc_journals | 15 |
| 140 | 航天器环境工程 | rhzh_journals | 9 |
| 141 | 中华整形外科杂志 | custom_toc_journals | 15 |
| 143 | 中华胸心血管外科杂志 | custom_toc_journals | 12 |
| 148 | 哈尔滨商业大学学报(社会科学版) | cnki_cbpt | 12 |
| 151 | 哈尔滨工业大学学报(社会科学版) | custom_toc_journals | 19 |
| 152 | 心理研究 | magetech_journals | 11 |
| 153 | 烟台大学学报(哲学社会科学版) | cnki_cbpt | 12 |
| 154 | 中国细胞生物学学报 | custom_toc_journals | 16 |
| 158 | 中华医学遗传学杂志 | custom_toc_journals | 11 |
| 162 | 实用肿瘤杂志 | cnki_cbpt | 14 |
| 163 | 中医药导报 | custom_toc_journals | 40 |
| 167 | 中国胶粘剂 | cnki_cbpt | 10 |
| 169 | 中国中西医结合肾病杂志 | cnki_cbpt | 28 |
| 178 | 青岛科技大学学报(自然科学版) | vsb_journals | 6 |
| 183 | 中华医学科研管理杂志 | custom_toc_journals | 14 |
| 184 | 无损检测 | rhzh_journals | 15 |
| 186 | 中华医学美学美容杂志 | custom_toc_journals | 19 |
| 187 | 中国斜视与小儿眼科杂志 | cnki_cbpt | 15 |
| 188 | 中国中西医结合耳鼻咽喉科杂志 | cnki_cbpt | 15 |
| 189 | 中华心律失常学杂志 | custom_toc_journals | 15 |
| 190 | 哈尔滨医科大学学报 | cnki_cbpt | 24 |
| 191 | 真空与低温 | rhzh_journals | 14 |
| 192 | 影像诊断与介入放射学 | cnki_cbpt | 13 |
| 193 | 生物技术 | cnki_cbpt | 16 |
| 194 | 中国小儿血液与肿瘤杂志 | cnki_cbpt | 15 |
| 196 | 云南农业大学学报 | rhzh_journals | 19 |

## 2. 待定（31 本，暂不写回）

| 排名 | 期刊 | probe status | 原因 |
|---:|---|---|---|
| 83 | 中国畜牧杂志 | warn | 苏迪 CMS；站点停在第10期 |
| 88 | 建筑学报 | warn | 目次纯文本，无文章链接 |
| 92 | 时珍国医国药 | warn | 方正 SPA，静态无目录 |
| 93 | 煤炭转化 | warn | 方正 SPA，静态无目录 |
| 98 | 中华医院感染学杂志 | warn | rhzh prepublish JS 模板，当期目录未取到 |
| 99 | 中华危重病急救医学 | pdf_only | 仅 PDF 版目次 |
| 101 | 有色金属(冶炼部分) | warn | magtech 目录可用但最新只到 2025-6 |
| 105 | 当代世界社会主义问题 | ok | 纯文本整期目录，无单篇链接/摘要 |
| 106 | 领导科学 | warn | 最新 2026-3，仅 5 篇有链接 |
| 107 | 中华医院管理杂志 | warn | yiigle 2026-08 期，疑似滞后 |
| 108 | 合成生物学 | warn | magtech 目录停在 2025 年 |
| 114 | 给水排水 | warn | 站点年期止于 2023 |
| 120 | 出土文献 | ok | 纯文本“作者：篇名”，无文章链接 |
| 122 | 光通信研究 | warn | founder 当期页为空 |
| 124 | 分析科学学报 | warn | 目录停在 2022 |
| 125 | 福州大学学报(自然科学版) | warn | 当期未抓到（issue_list 空/超时） |
| 144 | 高校应用数学学报A辑 | pdf_only | 仅整篇 PDF |
| 147 | 芙蓉 | warn | 纯文本目录，无单篇链接 |
| 149 | 大数据 | warn | 方正 SPA，无 SSR 目录 |
| 150 | 图书馆理论与实践 | warn | CBPT 门户读取超时 |
| 156 | 建筑遗产 | warn | VSB 站点停更于 2025-1 |
| 160 | 艺术工作 | warn | VSB 停更 2025-6，纯文本无链接 |
| 161 | 中医学报 | ok | 纯文本目录，无单篇链接；CNKI 验证码 |
| 164 | 中国卫生信息管理杂志 | warn | CBPT 过刊入口 404，实走 WKA |
| 165 | 食品与发酵科技 | warn | 2026 仅 1 期且无期次标识 |
| 170 | 中国性科学 | warn | 当期目录空，issue_browser 502 |
| 173 | 土木工程与管理学报 | pdf_only | 目录仅内嵌 PDF |
| 177 | 南昌大学学报(理科版) | ok | 当期停在 2025年49卷6期，站点疑似滞后 |
| 179 | 武汉大学学报(医学版) | warn | Vue SPA，纯 JS 渲染 |
| 182 | 中华心血管病杂志(网络版) | warn | 已迁站，仅最新发布，无当期目次 |
| 185 | 自动化与仪器仪表 | pdf_only | 仅 2016 年版 PDF，站点停更 |

## 3. 不可写回（43 本）

| 排名 | 期刊 | probe status | 原因 |
|---:|---|---|---|
| 82 | 现代地质 | blocked | 方正/JS SPA 空壳 |
| 85 | 无机盐工业 | blocked | 方正/JS SPA 空壳 |
| 86 | 药学学报 | fail | TLS 证书链/主机名错误 |
| 87 | 轴承 | blocked | 方正/JS SPA 空壳 |
| 89 | 中药材 | fail | 入口不可用 |
| 91 | 渔业现代化 | fail | TLS 证书链/主机名错误 |
| 95 | 中华肿瘤防治杂志 | no_current | 官网无公开当期目录 |
| 96 | 水利经济 | blocked | 访问被拦截/无公开当期 |
| 97 | 防灾减灾工程学报 | fail | TLS 证书链/主机名错误 |
| 103 | 中共党史研究 | no_current | 官网无公开当期目录 |
| 104 | 广西民族大学学报(哲学社会科学版) | no_current | 官网无公开当期目录 |
| 109 | 建筑科学 | fail | 入口不可用 |
| 110 | 中国有色冶金 | blocked | 验证码/登录拦截 |
| 112 | 空气动力学学报 | no_current | 官网无公开当期目录 |
| 113 | 建筑钢结构进展 | blocked | 方正/JS SPA 空壳 |
| 115 | 激光杂志 | no_current | 官网无公开当期目录 |
| 117 | 海洋工程 | blocked | 方正/JS SPA 空壳 |
| 118 | 印染 | blocked | 验证码/登录拦截 |
| 119 | 质谱学报 | blocked | 访问被拦截/无公开当期 |
| 121 | 中华地方病学杂志 | login | 需登录/SSO/校园 VPN |
| 123 | 化学与生物工程 | no_current | 官网无公开当期目录 |
| 127 | 重庆师范大学学报(自然科学版) | fail | DNS 不存在 |
| 128 | 合成树脂及塑料 | blocked | 验证码/登录拦截 |
| 130 | 江西师范大学学报(自然科学版) | fail | 连接超时/端口不可达 |
| 132 | 中国档案 | no_current | 官网无公开当期目录 |
| 134 | 化学研究与应用 | no_current | 官网无公开当期目录 |
| 139 | 化工设备与管道 | fail | DNS 不存在 |
| 142 | 农业考古 | no_current | 官网无公开当期目录 |
| 145 | 收获 | no_current | 官网无公开当期目录 |
| 146 | 数学学报 | blocked | 验证码/登录拦截 |
| 155 | 高原科学研究 | blocked | 验证码/登录拦截 |
| 157 | 中国法医学杂志 | blocked | 验证码/登录拦截 |
| 159 | 俄罗斯文艺 | fail | 入口不可用 |
| 166 | 中国急救复苏与灾害医学杂志 | no_current | 官网无公开当期目录 |
| 168 | 中国医药导报 | no_current | 官网无公开当期目录 |
| 171 | 腹腔镜外科杂志 | no_current | 官网无公开当期目录 |
| 172 | 医学动物防制 | blocked | 验证码/登录拦截 |
| 174 | 微生物学免疫学进展 | blocked | 验证码/登录拦截 |
| 175 | 中国中西医结合皮肤性病学杂志 | blocked | 验证码/登录拦截 |
| 176 | 医学研究杂志 | fail | TLS 证书链/主机名错误 |
| 180 | 宁夏医科大学学报 | login | 需登录/SSO/校园 VPN |
| 181 | 现代医学 | blocked | 方正/JS SPA 空壳 |
| 195 | 中华眼科医学杂志(电子版) | fail | 连接超时/端口不可达 |

## 4. 说明

- 写回清单：`journal_catalog/core/domestic-p1-batch3-applied-2026-11-26.csv`。
- yiigle 9 本为**题录级**：目次/标题/链接可采，文章摘要页为 WAF/CAPTCHA，不公开取摘要。
- CNKI WK* 与 portal 部分条目摘要内联；paperDigest 摘要页可能要求验证码，摘要 best-effort。
- 未写回项保持原状；blocked/no_current/login/fail 不绕过，留后续人工或授权源处理。
