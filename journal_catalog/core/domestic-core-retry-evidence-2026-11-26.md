# 国内核心 backlog A/B 直连重试证据（2026-11-26）

- 来源：`.local/domestic-core-retry/agent01..10.csv/md`；56 本（B 类 54 + A 类 2）。
- 方式：直连、禁用代理、每本 ≤4 请求；未登录、未绕验证码/WAF、未下载 PDF。

## 结论

- **写回 8 / 待定 26 / 不可写回 22**。
- 写回 8 本：心理学报、南京审计大学学报、棉纺织技术、植物遗传资源学报、海军航空大学学报、现代制造工程、数学进展、遥测遥控。
- 之前大量 502 是代理/链路假象；直连后部分恢复，但仍有一批是停更/域名失效/证书链/JS 挑战/纯文本/PDF。

## 写回清单

| 期刊 | 包 | live 条数 | 最新期 |
|---|---|---:|---|
| 南京审计大学学报 | custom_toc_journals | 10 | 2026年第23卷第6期 |
| 心理学报 | magetech_journals | 14 | 2026年第58卷第11期（刊出日期 2026-11-25） |
| 数学进展 | custom_toc_journals | 16 | 2026年第55卷第06期 |
| 棉纺织技术 | paperonce_journals | 16 | 2026年第54卷第11期（2026-11-10） |
| 植物遗传资源学报 | qinyun_journals | 16 | 2026年第27卷第11期 |
| 海军航空大学学报 | custom_toc_journals | 15 | 2026年第5期 |
| 现代制造工程 | magetech_journals | 19 | 2026年第10期（总第553期 2026-10-18） |
| 遥测遥控 | rhzh_journals | 17 | 2026年第47卷第5期 |

## 待定/不可写回

| 期刊 | 重试状态 | 最新期 | 链接 | 分诊 | 原因 |
|---|---|---|---|---|---|
| 中国现代手术学杂志 | ok_stale | 2018年 22卷 4期 | yes | 样例 https://www.surgerychina.com/CN/abstract/abstract327.shtml | regex /CN/abstract/abstract(\d+)\.shtml | 待定 | 恢复但停更 2018 |
| 网络与信息安全学报 | blocked |  | no | 不可写回 | 4 请求：/cn/issue/2026/4 403/548B/0.24s（https 与 http 同）；cjnis.com.cn 无 www 证书主机名不匹配 SSL 错；首页  |
| 世界历史 | fail |  | no | 不可写回 | 2 请求均 NameResolutionError；223.5.5.5 与本地 DNS 均返回 Non-existent domain；同域 cssn.cn 可解析(103.247 |
| 中国食物与营养 | ok_non_official | 2023年04期 | no | 待定 | 恢复但非官网聚合页，2023 期 |
| 公共行政学报 | fail |  | no | 不可写回 | 2 请求：https 19.68s 后 WinError 10061 拒绝；http 18.13s 同样拒绝；DNS 解析到 140.119.168.39，但该 IP 443 直连 |
| 包装与食品机械 | ok_stale | 2023年 41卷 4期 | yes | 样例 https://qikan.cmes.org/bzyspjx/CN/10.3969/j.issn.1005-1295.2023.04.001 | regex /bzyspjx/CN/10\.3969/j\.issn\.1005-1295\.\d{4}\.\d{2}\.\d{3} | 导出 showArticleByLexeme.do?articleID=\d+ | 待定 | 恢复但期次冻结 2023 |
| 化工环保 | ok | 2024年03期 | no | 待定 | 代理站，最新 2024-03，纯文本无链接 |
| 北京行政学院学报 | fail |  | no | 不可写回 | www.bac.gov.cn 解析 120.52.186.8，http:80 / https:443 直连均约21s超时（curl 28） / 裸域 bac.gov.cn 无 A/ |
| 医学研究与战创伤救治 | maintenance |  | no | 待定 | http 根路径被维护页整体替换，无当期/无目录 / https 根路径证书与域名不匹配（curl 60） / 加 -k 访问 https 返回 IIS 404（315B），说明站 |
| 台大历史学报 | ok | 第77期（2026年6月出版） | yes | 待定 | TOAJ 二跳，仅题录；待文本/二跳适配 |
| 台大社会工作学刊 | ok | 第53期（2026年6月；第54期预计2026年12月待出刊） | no | 待定 | 各期目录页仅到期级条目（第6–54期，约49条），每期1个"完整版"整期PDF链接（Google Drive file/d/<id>/view） / 无篇级标题/作者/摘要，无法产 |
| 台湾大学美术史研究集刊 | ok | 第60期（2026年3月） | yes | 待定 | 多期混排+TOAJ 二跳，需期次切段 |
| 国外文学 | fail | 未知 | no | 不可写回 | 直连 DNS 失败：curl(6)，路由器与 AliDNS 223.5.5.5 均返回 NXDOMAIN；http/https/www 三态均不可达；pku.edu.cn 主域正常 |
| 国外电子测量技术 | ok | 2024年第43卷第12期 | yes | 待定 | 恢复但内容冻结 2024-12，滞后约 23 个月 |
| 国家教育行政学院学报 | partial | 2026年第10期（总第346期） | no | 待定 | 恢复但期页空壳/JS |
| 国际政治研究 | fail | 2026年第4期（上次基线） | no | 不可写回 | https 直连仍 curl(60)，缺中间证书（Missing Subject Key Identifier 同类问题）；http 301→https 同样失败；非 www ji |
| 土木工程学报 | fail | 未知 | no | 不可写回 | https 与 http 根路径均 200 但仅 129 字节 meta refresh 到 /DispatchInfo/Error.aspx?code=2；WKC/WebPubl |
| 大气科学学报 | partial | 无（仅简介页，无期次/目录） | no | 待定 | 直连可开但只有刊名/ISSN/CN/主办/简介/编委会等元数据，无当期目录、无文章链接；独立站被安全狗拦截（403自签名错误页），按要求不绕WAF；换 xb.nuist.edu.c |
| 山东社会科学 | partial | 2026年第2期（期次编号20262，2026-03-16） | no | 待定 | 最新 2026-2，目录正文空，疑似停更 |
| 广东药科大学学报 | fail | 无（站内无当期目录） | no | 不可写回 | https 与 http 各试1次均 NameResolutionError（阿里DNS 报 Non-existent domain）；www.gdpu.edu.cn 正常；“过刊 |
| 摩擦学学报 | fail | 未知 | no | 不可写回 | http/https、www/裸域合计3次均 NameResolutionError(11002)；www.tribology.org.cn、tribology.cas.cn 亦  |
| 政治大学哲学学报 | fail | 未知 | no | 不可写回 | https 与 http 各试1次均 ConnectTimeout；不绕网络限制、不换代理；需境外链路才能验证，暂不可写回 |
| 文化纵横 | fail |  | no | 不可写回 | http 80 ConnectTimeout 21.3s；https 443 同样 21.0s 超时；裸域 21bcr.com DNS 解析失败；三种直连组合全失败，排除代理因素（ |
| 文献 | partial |  | no | 待定 | 仅介绍页，无目录 |
| 新乡医学院学报 | fail |  | no | 不可写回 | https 与 http 均 SSLCertVerificationError（unable to get local issuer certificate），http 被强制跳  |
| 新疆社会科学 | partial |  | no | 待定 | 证书信任库问题解决，但官网无目次 |
| 暖通空调 | ok | 2026年第4期 | yes | 待定 | 恢复但最新 2026-4，站点滞后 |
| 机械设计 | ok | 2020年第37卷第11期（刊出2020-11-20） | yes | 待定 | 恢复但停 2020 年 |
| 标记免疫分析与临床 | fail |  | no | 不可写回 | 直连未恢复，原因从502变为备案拦截：http://www.chinabjmy.com/ 403/640B，标题 Non-compliance ICP Filing，正文 JS 跳 |
| 民国档案 | fail |  | no | 不可写回 | 官网200但无刊物栏目：http://www.shac.net.cn/ 200/15KB/0.12s，中国第二历史档案馆门户，全页仅26个链接（馆情/查档/民国旧影/视频/决算公告 |
| 流体机械 | ok | 2023年第51卷第8期（刊出2023-08-28） | yes | 待定 | 恢复但停 2023 年 |
| 清华中文学报 | ok(partial) | 第三十五期 Issue 35（2026.6） | partial | 无逐篇详情页 | 整期目录 /p/406-1401-310941,r3772.php | 待定 | 恢复但仅整期目录/PDF，无篇级链接 |
| 电网技术 | fail |  | no | 不可写回 | www.dwjs.com.cn 在本地 DNS(192.168.31.1) 与 AliDNS(223.5.5.5) 均 NXDOMAIN；裸域 dwjs.com.cn 无 A/AA |
| 石河子大学学报自然科学版 | ok(curl 恢复 / python 仍 TLS fail) | 第44卷第5期（2026-10-20） | yes | /CN/10.13880/j.cnki.65-1174/n.2026.21.014-018 等 | 待定 | curl 可读/urllib TLS 不兼容，需换 TLS 栈 |
| 石油学报(石油加工) | fail |  | no | 不可写回 | http 首页与 /CN/current 均 200 但仅 1334B，body 只有 <script src=/1ywuKELSO2ahQuWZ/js/app.49692bf2. |
| 神经解剖学杂志 | fail |  | no | 不可写回 | 直连未恢复：http://www.cjana.org、https://www.cjana.org、http://cjana.org、https://cjana.org 四次全部 N |
| 粮食与饲料工业 | fail |  | no | 不可写回 | 直连仍未恢复：http://www.lsyslgy.com/ 返回 200 但仅 59 字节 <script src=/_guard/html.js?js=easy_slider_ |
| 组合机床与自动化加工技术 | warn | 2026年第10期（页次1–241，共4栏目：设计与研究/控制与检测/工艺与装备/先进管理技术） | no | 待定 | 恢复但纯表格目录无文章链接 |
| 经济学（季刊） | fail |  | no | 不可写回 | 直连未恢复：https（及 http 301 后）均 SSLError CERTIFICATE_VERIFY_FAILED『Hostname mismatch, certifica |
| 美术学报 | fail |  | no | 不可写回 | 页面由上次 50x 恢复为 200（27KB，UTF-8），但仍只是『学报编辑部』机构介绍页（信息来源 2017.12.14，一句话职责说明），全页无当期目次、无文章、无期刊子站链 |
| 西北民族大学学报（藏文哲学社会科学版） | warn | 2024年第4期（发布 2024-12-16，站内最新；往期页仅 2024年1–3期） | no | 待定 | 直连恢复：入口 https://www.xbmu.edu.cn/qkbj/zxshkx_zwb_.htm 由上次 502 变为 200（5.6KB，UTF-8）；『本期目次』指向  |
| 西安电子科技大学学报自然科学版 | fail |  | no | 不可写回 | 直连未恢复：https 的 /zh/issue/2026/5/ 与 /zh/home/ 均 SSLError CERTIFICATE_VERIFY_FAILED，http 同址 3 |
| 财务与会计 | fail |  | no | 不可写回 | http 与 https 均 NameResolutionError（getaddrinfo failed，0.0–0.1s，已非 502） / 公网 DNS 复核：dns.ali |
| 近代史研究 | warn | 2025年第3期（发布2025-06-03） | no | 待定 | 最新 2025-3，正文空，停更 17 个月 |
| 造纸科学与技术 | warn | 站内当期标签『2017年 第卷 第1期』（异常，无法确认真实最新期） | yes | 待定 | 恢复但期次异常/陈旧，无法确认真实最新期 |
| 长江流域资源与环境 | warn | 2024年第33卷第7期 | yes | 待定 | 恢复但停 2024 年 33 卷 7 期 |
| 高校应用数学学报.A辑 | http_200_recovered | 第41卷A辑第3期（2026年 No.3） | partial（10条仅整篇PDF链接 253-261.pdf 等，无单篇页） | 待定 | 恢复但仍仅整期 PDF |
| 高电压技术 | fail_js_challenge | 未知（未取到目录） | no | 待定 | trust_env=False 直连；根路径与 /CN/1003-6520/home.shtml 均返回同一 560B 空壳（仅 <script src=/ob_k8D2mP7sV |

## 文件

- 写回清单：`journal_catalog/core/domestic-core-retry-applied-2026-11-26.csv`。
- 复测证据：本 CSV；逐组 md 在 `.local/domestic-core-retry/`。
