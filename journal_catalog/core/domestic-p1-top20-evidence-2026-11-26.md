# 国内 P1 Top20 探测证据汇总（2026-11-26）

- 证据来源：`.local/domestic-p1-top20/agent1.csv/md`、`agent2.csv/md`、`agent3.csv/md`、`agent4.csv/md`（只读，原始文件未改动）。
- 排序口径：agent1 = 第 1–5 本，agent2 = 第 6–10 本，agent3 = 第 11–15 本，agent4 = 第 16–20 本；共 20 本。
- 探测边界：公开页面只读；未登录、未绕验证码/WAF、未下载 PDF；未改采集包/DB/任务，未 commit。
- **写回口径：本文件只是证据汇总，尚未做 live 复验；未 live 验证前不写回任何采集包/DB/任务。**

## 0. 结论速览

- 原始 status：**ok 11 / no_current 4 / blocked 3 / warn 1 / pdf_only 1**。
- 写回分诊：**可写回 7 / 待定 6 / 不可写回 7**（不可写回 = status blocked 3 + no_current 4）。
- 可写回清单：管理世界、中国法学、体育学研究、经济与管理评论、电工技术学报、农业现代化研究、管理科学（A-，期次待复核）。
- 不可写回主因：验证码 1、WAF 1、方正 SPA 1、CNKI 腾云未开通 2、官网无当期 1、官网目次停更 1。

## 1. 状态与写回分诊

### 1.1 原始 status 计数

| status | 数量 | 期刊 |
|---|---:|---|
| ok | 11 | 管理世界、中国法学、体育学研究、经济与管理评论、统计与决策、南京社会科学、电工技术学报、农业现代化研究、兰州大学学报(社会科学版)、管理科学、体育学刊 |
| no_current | 4 | 中国社会科学、经济与管理、会计研究、陕西师范大学学报(哲学社会科学版) |
| blocked | 3 | 中外法学、当代经济科学、南京审计大学学报 |
| warn | 1 | 城市规划学刊 |
| pdf_only | 1 | 大连理工大学学报(社会科学版) |
| **合计** | **20** | — |

### 1.2 写回分诊（未 live 复验，暂不写回）

- **可写回候选：7 本**——平台/入口/链接正则/中文摘要证据齐全，可进入写回候选；仍需逐本 live 复验后才写。
- **待定：6 本**——摘要不可采、仅英文摘要、仅 PDF、微信承载或期次滞后，需要适配扩展或人工确认。
- **不可写回（blocked/no_current）：7 本**——当前无可用公开当期页面，保持阻塞或另找兜底源。

| status | 数量 | 可写回 | 待定 | 不可写回 |
|---|---:|---:|---:|---:|
| ok | 11 | 7 | 4 | 0 |
| warn | 1 | 0 | 1 | 0 |
| pdf_only | 1 | 0 | 1 | 0 |
| blocked | 3 | 0 | 0 | 3 |
| no_current | 4 | 0 | 0 | 4 |
| **合计** | **20** | **7** | **6** | **7** |

#### 可写回候选清单（7）

| rank | 期刊 | 目标包（package_guess） | 已知风险/复核点 |
|---:|---|---|---|
| 1 | 管理世界 | custom_toc_journals | 本期 12 条、10 条/页，需翻页（第 2 页参数 curpage=2&pagesize=10） |
| 2 | 中国法学 | custom_toc_journals | 15 篇单页；历史采集器 UA 曾 502，本次浏览器 UA 200 |
| 5 | 体育学研究 | qinyun_journals | 12 条含“专题导读 2026(4):0-0”，需过滤 |
| 7 | 经济与管理评论 | custom_toc_journals | 目录页无摘要，详情页有摘要/关键词 |
| 14 | 电工技术学报 | magtech_journals | 23 篇，需剔除“目录”0-0 条目；过刊 https 偶发超时 |
| 16 | 农业现代化研究 | rhzh_journals | 旧 CA 链会 TLS self-signed，需 requests verify=True 或更新 CA，禁用 -k |
| 18 | 管理科学 | vsb_journals | A-：站点最新 2026,39(3)，过刊仅到 2023，写回前须复核期次是否停更 |

> 口径说明：`管理科学` 证据本身完整，但期次新鲜度有疑点；若 live 复核确认停更/无更新，则降为“待定”，此时为可写回 6 / 待定 7 / 不可写回 7。
>
> 分布：前 15 本 5 本（管理世界、中国法学、体育学研究、经济与管理评论、电工技术学报）；第 16–20 组新增 2 本（农业现代化研究、管理科学 A-）。

#### 待定清单（6）

| rank | 期刊 | 待定原因 | 可用的部分 |
|---:|---|---|---|
| 11 | 统计与决策 | 官网无站内 HTML 文章页，文章全部指向微信公众号；需 custom_toc 扩展微信二级抓取 | 2026-21 列表 12 条/页、共 97 页；微信图文含摘要 |
| 12 | 南京社会科学 | paperDigest/过刊/colType 均 302 到验证码；摘要与落地页不可采 | 首页内嵌 2026-10 目次 17 条公开，题录+链接可提取 |
| 13 | 城市规划学刊 | warn：最新仅 2026-03，疑未更新；文章页仅中文 PDF，无摘要/HTML | 14 条标题+PDF 链接可采 |
| 17 | 兰州大学学报(社会科学版) | paperDigest 302 到 WKH3 验证码；摘要与落地页不可采 | 2026-05（v.54 No.261）15 条题录+链接可提取 |
| 19 | 大连理工大学学报(社会科学版) | pdf_only：目录仅标题+作者+页码+PDF 附件，无文章 HTML/摘要 | 12 条题录可采；暂不能入常规 vsb 包 |
| 20 | 体育学刊 | 详情页仅英文 Abstract，无中文摘要/关键词 | 2026-5 年期页 17 条，文章链接可用 |

#### 不可写回清单（7）

| rank | 期刊 | status | 阻塞原因 |
|---:|---|---|---|
| 3 | 中国社会科学 | no_current | 官网为新闻门户，`/kbw/zgshkx/` 仅简介/订阅/投稿，无当期或过刊文章入口；founder 仅投审稿需登录 |
| 4 | 中外法学 | blocked | 根域 meta refresh 到 `Error.aspx?code=2`；`/WKG/WebPublication/index.aspx?mid=zwfx` 302 到 `showValidateCode.aspx` 验证码 |
| 6 | 当代经济科学 | blocked | 方正 SPA 壳，HTML 无当期；`findBySld?sld=jjkx` 返回 data:null，无 siteId/publicationIndexId |
| 8 | 经济与管理 | no_current | CNKI 腾云采编未开通，根域 302→Quit→`Error.aspx?code=3`，无公开当期目录 |
| 9 | 会计研究 | no_current | 同《经济与管理》，腾云采编未开通，`Error.aspx?code=3` |
| 10 | 南京审计大学学报 | blocked | Wengine WAF 403（报 IP 58.19.5.221 无权限），HTTP/HTTPS 均 403；未绕过 |
| 15 | 陕西师范大学学报(哲学社会科学版) | no_current | 官网“本期目录/往期回顾”最新止于 2023 年第 6 期，2024–2026 目次缺失；所测 15 条为 2023 旧目次 |

## 2. 20 本结论表

### 2.1 状态、平台与写回结论

| rank | 期刊 | status | items | platform | package | abstract | pagination | 分诊 | 关键结论/阻塞 |
|---:|---|---|---:|---|---|---|---|---|---|
| 1 | 管理世界 | ok | 12 | custom_toc | custom_toc_journals | yes | yes | 可写回 | 2026-11，12 条/2 页，详情有中文摘要 |
| 2 | 中国法学 | ok | 15 | custom_toc | custom_toc_journals | yes | no | 可写回 | 2026-5，15 篇单页，内容提要齐全 |
| 3 | 中国社会科学 | no_current | 0 | custom | none | n/a | n/a | 不可写回 | 官网无当期/过刊入口 |
| 4 | 中外法学 | blocked | 0 | cnki_cbpt | cnki_cbpt | unknown | unknown | 不可写回 | 验证码 + Error.aspx?code=2 |
| 5 | 体育学研究 | ok | 12 | qinyun | qinyun_journals | yes | no | 可写回 | 2026-4，12 条含 0-0 专题导读 |
| 6 | 当代经济科学 | blocked | 0 | founder | founder_journals | unknown | unknown | 不可写回 | 方正 SPA，无 siteId/公开 API |
| 7 | 经济与管理评论 | ok | 8 | custom_toc | custom_toc_journals | yes | no | 可写回 | 2026-6，8 篇单页，详情有摘要 |
| 8 | 经济与管理 | no_current | 0 | cnki_cbpt | cnki_cbpt | n/a | n/a | 不可写回 | 腾云采编未开通 |
| 9 | 会计研究 | no_current | 0 | cnki_cbpt | cnki_cbpt | n/a | n/a | 不可写回 | 腾云采编未开通 |
| 10 | 南京审计大学学报 | blocked | 0 | magetech | magetech_journals | unknown | unknown | 不可写回 | WAF 403，IP 无权限 |
| 11 | 统计与决策 | ok | 12 | custom_toc | custom_toc_journals | yes | yes | 待定 | 文章全在微信公众号，需二级抓取 |
| 12 | 南京社会科学 | ok | 17 | cnki_cbpt | cnki_cbpt | captcha | no | 待定 | 首页目次公开，摘要页验证码 |
| 13 | 城市规划学刊 | warn | 14 | custom_toc | custom_toc_journals | no | no | 待定 | 最新仅 2026-3，仅 PDF 无摘要 |
| 14 | 电工技术学报 | ok | 23 | magtech | magtech_journals | yes | no | 可写回 | 2026 年 41 卷 21 期，摘要完整 |
| 15 | 陕西师范大学学报(哲学社会科学版) | no_current | 15 | custom_toc | custom_toc_journals | yes | no | 不可写回 | 目次停在 2023-6，15 条为旧目次 |
| 16 | 农业现代化研究 | ok | 26 | rhzh | rhzh_journals | yes | no | 可写回 | 2026 年 47 卷 5 期，中文摘要完整 |
| 17 | 兰州大学学报(社会科学版) | ok | 15 | cnki_cbpt | cnki_cbpt | no | no | 待定 | 2026-05，15 条；摘要页验证码 |
| 18 | 管理科学 | ok | 12 | vsb | vsb_journals | yes | no | 可写回（A-） | 2026,39(3)；过刊仅到 2023，需复核停更 |
| 19 | 大连理工大学学报(社会科学版) | pdf_only | 12 | vsb | vsb_journals | no | no | 待定 | 仅 PDF 附件，无文章 HTML/摘要 |
| 20 | 体育学刊 | ok | 17 | custom_toc | custom_toc_journals | yes | no | 待定 | 2026-5 年期页；仅英文摘要 |

### 2.2 入口与链接证据

| rank | 期刊 | current_url | link_regex |
|---:|---|---|---|
| 1 | 管理世界 | http://www.mwm.net.cn/web/bqym | `^/web/xq\?leafId=\d+&docId=\d+$` |
| 2 | 中国法学 | https://clsjp.chinalaw.org.cn/portal/list/index.html?id=1938 | `^/portal/article/index\.html\?id=\d+&cid=\d+$` |
| 3 | 中国社会科学 | — | — |
| 4 | 中外法学 | — | —（验证码，未实测） |
| 5 | 体育学研究 | https://ntxb.nipes.cn/tyxyj/njtyxyxbsk/article/issue/2026_4 | `^/tyxyj/njtyxyxbsk/article/abstract/\d+$` |
| 6 | 当代经济科学 | https://jjkx.xjtu.edu.cn/ | —（SPA，无条目） |
| 7 | 经济与管理评论 | http://jjyglpl.sdufe.edu.cn/qkml1/jjyglpl2026nd6q.htm | `^http://jjyglpl\.sdufe\.edu\.cn/info/\d+/\d+\.htm$` |
| 8 | 经济与管理 | https://jjgl.chinajournal.net.cn/EditorB2N/Error.aspx?code=3 | —（错误页） |
| 9 | 会计研究 | https://kjyj.chinajournal.net.cn/EditorB2N/Error.aspx?code=3 | —（错误页） |
| 10 | 南京审计大学学报 | http://xbbjb.nau.edu.cn/sjxyxb/home | —（WAF 403） |
| 11 | 统计与决策 | http://www.tjyjc.com/news/56/ | `^https://mp\.weixin\.qq\.com/s/[A-Za-z0-9_-]+$` |
| 12 | 南京社会科学 | https://njsh.chinajournal.net.cn/WKG/WebPublication/index.aspx?mid=njsh | `^https?://njsh\.chinajournal\.net\.cn/WKG/WebPublication/paperDigest\.aspx\?paperID=[0-9a-f-]{36}$` |
| 13 | 城市规划学刊 | http://upforum.wupen.org/Data/List/xksd?lang=1 | `^https?://upforum\.wupen\.org/Data/View/\d+\?lang=1$` |
| 14 | 电工技术学报 | https://dgjsxb.ces-transaction.com/CN/volumn/current.shtml | `^https?://dgjsxb\.ces-transaction\.com/CN/abstract/abstract\d+\.shtml$` |
| 15 | 陕西师范大学学报(哲学社会科学版) | http://www.xuebao.snnu.edu.cn/wenke/bqml_wk.htm | `^http://www\.xuebao\.snnu\.edu\.cn/info/1072/\d+\.htm$` |
| 16 | 农业现代化研究 | https://nyxdhyj.isa.ac.cn/cn/article/current | `^https?://nyxdhyj\.isa\.ac\.cn/article/doi/10\.13872/j\.1000-0275\.\d{4}\.\d+$` |
| 17 | 兰州大学学报(社会科学版) | https://ldsk.chinajournal.net.cn/WKH3/WebPublication/index.aspx?mid=LDSK | `^https?://ldsk\.chinajournal\.net\.cn/WKH3/WebPublication/paperDigest\.aspx\?paperID=[0-9a-f-]{36}$` |
| 18 | 管理科学 | http://glkx.hit.edu.cn/dqml.htm | `^https?://glkx\.hit\.edu\.cn/info/\d+/\d+\.htm$` |
| 19 | 大连理工大学学报(社会科学版) | http://xbsk.dlut.edu.cn/info/1915/4863.htm | `^http://xbsk\.dlut\.edu\.cn/system/_content/download\.jsp\?urltype=news\.DownloadAttachUrl&owner=\d+&wbfileid=[0-9A-F]+$` |
| 20 | 体育学刊 | https://tyxk.scnu.edu.cn/book/2026nian/di5qi/ | `^https?://tyxk\.scnu\.edu\.cn/a/\d{8}/\d+\.html$` |

> 注：`current_url` 为空的 2 本（中国社会科学、中外法学）表示未找到公开当期页；错误页/403 页保留原 URL 作为证据。链接正则以 CSV 字段为准。

## 3. 原因分类

### 3.1 不可写回 7 本

| 原因 | 数量 | 期刊 |
|---|---:|---|
| 验证码墙 | 1 | 中外法学 |
| WAF/IP 403 | 1 | 南京审计大学学报 |
| 方正 SPA 无 siteId/公开 API | 1 | 当代经济科学 |
| CNKI 腾云采编未开通（Error.aspx?code=3） | 2 | 经济与管理、会计研究 |
| 官网无当期/过刊入口 | 1 | 中国社会科学 |
| 官网目次停更 | 1 | 陕西师范大学学报(哲学社会科学版) |

### 3.2 待定 6 本

| 原因 | 数量 | 期刊 |
|---|---:|---|
| 摘要页验证码（题录可采） | 2 | 南京社会科学、兰州大学学报(社会科学版) |
| 文章承载在微信公众号（无站内文章页） | 1 | 统计与决策 |
| 仅英文摘要 | 1 | 体育学刊 |
| 期次滞后 + 仅 PDF 无摘要（warn） | 1 | 城市规划学刊 |
| 仅 PDF 附件（pdf_only） | 1 | 大连理工大学学报(社会科学版) |

### 3.3 可写回候选的已知风险

- **管理世界**：12 条分 2 页，适配器必须处理 `curpage` 翻页。
- **中国法学**：15 篇单页；历史采集器 UA 曾 502，本次浏览器 UA 200，写回后需用浏览器 UA 复测。
- **体育学研究**：12 条含“专题导读 2026(4):0-0”，需按页码/标题过滤。
- **经济与管理评论**：目录页无摘要，必须进详情页取摘要。
- **电工技术学报**：23 篇/7 栏目，需剔除“目录”0-0 条目；过刊 https 首访偶发 25s 超时。
- **农业现代化研究**：curl 旧 CA 链报 `self signed certificate in certificate chain`，不是站点阻断；用 requests verify=True 或更新 CA，禁用 `-k`。
- **管理科学**：A-；站点最新 2026,39(3)，过刊仅到 2023，写回前复核是否停更/延迟。
- **相对链接正则**：管理世界、中国法学、体育学研究 的 `link_regex` 以 `/` 开头，是站内相对路径；写回/适配时需与 `current_url` 的 origin 拼接，不能直接当绝对 URL 用。

## 4. 平台/包判断纠正

| 期刊 | 历史/原判断 | 本次证据 | 处理建议 |
|---|---|---|---|
| 农业现代化研究 | custom | rhzh（页面含“北京仁和汇智”，`/cn/article/current`、`/article/doi/`） | 写回时改 `rhzh_journals` |
| 兰州大学学报(社会科学版) | chinajournal/custom | cnki_cbpt（WKH3/WebPublication） | 写回时改 `cnki_cbpt` |
| 管理科学 | custom | vsb（`vsbscreen.min.js`、SiteBuilder 指纹） | 写回时改 `vsb_journals` |
| 大连理工大学学报(社会科学版) | custom | vsb（SiteBuilder），但内容为 pdf_only | 改 `vsb_journals`，但暂不入常规 vsb 包 |
| 体育学刊 | blocked（“目次仅文本无链接”） | custom_toc；`/book/2026nian/di5qi/` 年期页有文章链接 | 入口改为 `/book/` 年期页，状态可恢复 |
| 南京社会科学 | — | cnki_cbpt / WKG；内容入口是 `index.aspx`，不是 EditorGN | 只抓首页内嵌目次，勿请求 paperDigest/colType |
| 南京审计大学学报 | magetech（历史目录） | WAF 403，平台未能 live 验证；与电工技术学报的 `magtech` 疑为同一平台拼写差异 | 写回前统一确认平台名；未确认前保持 blocked |
| 统计与决策 | — | custom_toc + 微信公众号承载 | 需扩展微信二级抓取，或只收标题+微信链接 |
| 中外法学 | cnki_cbpt | cnki_cbpt，但验证码阻断，链接模式未实测 | 保持 blocked，不绕过 |

## 5. 下一步建议

1. **先 live 复验可写回 7 本，再写回**：每本按“目录页 + 1 篇文章页”各 1 次请求复验，使用浏览器 UA、直连（`--noproxy '*'`）；复验通过才写回。按平台分组：custom_toc（管理世界、中国法学、经济与管理评论）、qinyun（体育学研究）、magtech（电工技术学报）、rhzh（农业现代化研究）、vsb（管理科学）。
2. **写回时同步修正平台/包**：农业现代化研究→rhzh、兰大→cnki_cbpt、管理科学/大连理工→vsb；不要沿用历史 custom 标记。
3. **待定 6 本按优先级处理**：
   - 统计与决策：确认 12 条是否为全期篇数（官微目录图文仅见 5 篇摘要节选），再决定扩展微信二级抓取还是只收标题+链接。
   - 南京社会科学、兰州大学学报：只抓 WKG/WKH3 首页内嵌目次，摘要验证码不重试、不绕过；若目录强依赖摘要则暂不写回。
   - 体育学刊：确认英文摘要能否入库；入口固定 `/book/` 年期页，不用新闻版目次（仅 12 条纯文本）。
   - 城市规划学刊：确认 2026-03 之后是否另有发布渠道；无摘要则仅题录+PDF 链接。
   - 大连理工大学学报：PDF/OCR 或另找文章页；暂不入常规 vsb 包。
   - 管理科学：先复核期次新鲜度，再决定升“可写回”或降“待定”。
4. **不可写回 7 本**：
   - 中国社会科学、经济与管理、会计研究：改用 CNKI/万方文献页或人工兜底，不再打官网当期。
   - 中外法学、南京审计大学学报：保持 blocked，不绕验证码/WAF；南京审计可在更换网络环境后复核。
   - 当代经济科学：必须先拿 siteId/publicationIndexId，不要盲试接口；优先 CNKI/万方兜底。
   - 陕西师范大学学报：另找知网/采编平台公开当期；2023 旧目次不得当 2023-6 之后使用。
5. **统一约束**：未 live 验证前不写回；不绕过验证码/WAF；不下载 PDF；不改原始 agent 文件；写回前保留本证据表作为依据。

## 6. 数据质量与口径说明

- **agent3.csv 表头与其他三份不同**（`journal,home_url,status,...`，无 `package_guess`）；5 行 `journal` 均有值，已按行顺序与 `agent3.md` 核对一致，本次无需补空名。其 `package_guess` 为按 platform 推断，已在 CSV 备注中标注。
- `items` 是探测到的当期/页面条目数，不等于期刊实际篇数；`no_current` 的 15 条是 2023 年旧目次，不能当当期。
- `abstract_visible=captcha` 表示摘要页被验证码阻断；`unknown` 表示页面不可达/未测到；`n/a` 表示无当期页面可测。
- `current_url` 为空表示未找到公开当期页（中国社会科学、中外法学）；其余错误页/403 页保留原 URL 作为证据。
- `blocked_or_note` 以状态/结论前缀开头（`ok`、`ok（有条件）`、`blocked`、`no_current`、`warn`、`pdf_only`），后接关键证据或阻塞原因，便于筛选。
- `pagination` 仅表示本次探测页面是否需要翻页；`yes` 的管理世界有 2 页，统计与决策有 97 页列表。
- 平台判断以页面指纹为准；历史目录中的 custom 标记有 4 处需纠正（农业现代化研究、兰州大学学报、管理科学、大连理工大学学报）。
- 平台拼写：南京审计大学学报沿用 agent2 的 `magetech`，电工技术学报为 `magtech`；疑为同一玛格泰克平台的不同拼写，南京审计因 WAF 未能 live 验证，写回前需统一确认。
- 期刊名按 agent CSV 原文保留；`陕西师范大学学报(哲学社会科学版)` 为半角括号，写回匹配时需与目录现有名称核对（全/半角差异）。
- 统计与决策的 `items=12` 可能不是全期篇数；官微目录图文只展示 5 篇摘要节选，需复核。

---

**最终提醒：以上 20 本均未在本次汇总中做 live 复验；未 live 验证前不写回任何包、DB 或任务。**
