# 剩余期刊站点抽样诊断（2026-11-21）

## 范围与方法

只做轻量抽样，不批量请求：每站 1–3 次首页/当期页/公开 JSON 接口请求，必要时用无头 Chrome 渲染一次。样本用于判断接入方式，不作为长期可用性验收。

## 结论先行

- **北大方正新平台与 PaperOnce 大多不是强反爬**，而是 Vue 单页应用 + 公开 JSON API；需要拆接口和站点 ID，不需要硬对抗验证码。
- **南京航空航天大学学报（jnuaa.nuaa.edu.cn）出现 HTTP 412 + 空 DOM**，带前置 Cookie 校验，属于强风控/前置校验，优先跳过或改用浏览器会话验证。
- **CBPT 的 500 站点仍是服务端故障**，例如潮学研究；不是模板问题，本期不修。
- **玛格泰克 403/分页停滞站点可用当期目次救回一部分**：中央音乐学院学报 11 条、中国临床护理 12 条、中国消毒学杂志 16 条；华南理工自然科学版和中国农业气象当期页可访问但暂无可解析文章。

## 样本明细

### 北大方正（founder）

| 样本 | 入口结果 | 证据 | 分类与建议 |
|---|---|---|---|
| 专门用途外语研究 | 首页 200，重定向到 hssonline.cn 的 Vue SPA | 无头渲染 DOM 323 KB；`/rc-pub/front/front-period/getFirstTwoPeriods?publicationIndexId=2180` 返回 200 和 2026 年第 3 期；`getArticlesByPeriodicalIdGroupByColumn/287518` 返回 200 空列表 | SPA + JSON API，无验证码；需要继续确认期次→文章列表接口，属模板/接口工作 |
| 航空制造技术 | `amte.publish.founderss.cn` 首页 200，同一套 Vue 资源 | `site/findBySld?sld=amte` 返回 200 站点配置 | 同一平台，模板可复用；优先做通用 founder API 适配 |
| 南京航空航天大学学报 | `jnuaa.nuaa.edu.cn` 返回 **HTTP 412**，Set-Cookie，无头渲染 DOM 为空 | 412 Precondition Failed | 强前置校验/风控；不要硬绕，改用浏览器会话或官方数据源，优先级最低 |
| 遥感学报 | `ygxb.ac.cn` 首页 200，Nuxt 渲染约 993 KB | 页面含 current/当期/目录链接和 `/api/` 请求 | 可访问的 SPA/API，属模板适配，不是真反爬 |

### PaperOnce

| 样本 | 入口结果 | 证据 | 分类与建议 |
|---|---|---|---|
| 东北林业大学学报 | `dlxb.nefu.edu.cn` 首页 200，Vue SPA | `api/api/Web/LastIssueList?PageSize=0&IssueId=0` 返回 200，JSON 约 33 KB，含当期文章 | 直接 JSON API；接入成本低 |
| 东南大学学报（自然科学版） | `journal.seu.edu.cn` 首页 200，Vue SPA | 同一接口返回 200，JSON 约 63 KB；错误路径 `/api/Web/...` 会落到 Safedog 404 页 | 正确前缀是 `/api/api/`；属路径/模板问题，不是 WAF |
| 中南林业科技大学学报 | `zkxb.csuft.edu.cn` 301 到 HTTPS | 跟随跳转后同一接口返回 200，JSON 约 143 KB | 属跳转/模板问题；可直接适配 |
| 搜索接口 | `api/api/Web/ArticleSearch` | 快速 POST 返回 500（请求体字段未对齐） | 是参数模板问题，不是反爬；接入时按前端请求体复刻 |

### 玛格泰克 / CBPT 失败站回收

| 样本 | 原问题 | 当期目次结果 | 结论 |
|---|---|---|---|
| 中央音乐学院学报 | 检索接口 403 | `/CN/current` 200，11 条 | 可用 `latest_issue` 模式救回 |
| 华南理工大学学报（自然科学版） | 检索接口 403 | `/CN/current` 200，0 条 | 页面可访问，但当期无可解析文章；需核查模板/期次 |
| 中国临床护理 | 分页停滞 | `/CN/current` 200，12 条 | 可用 `latest_issue` 模式救回 |
| 中国消毒学杂志 | 分页停滞 | `/CN/current` 200，16 条 | 可用 `latest_issue` 模式救回 |
| 中国农业气象 | 分页停滞 | `/CN/current` 200，0 条 | 当期页无可解析文章；需核查模板/期次 |
| 哈尔滨体育学院学报 | CBPT 检索报错 | `paper_list/type_benqi` 200，14 条 | 当期目次可救回 |
| 潮学研究 | CBPT HTTP 500 | 仍为 HTTP 500 | 服务端故障，跳过 |

## 接入优先级建议

1. **PaperOnce 通用 API 适配**：`/api/api/Web/LastIssueList` 已可直接取当期，先把 `dlxb`、`journal.seu`、`zkxb` 做成一个模板包。
2. **北大方正 rc-pub API 适配**：先做 `getPeriodTree` + 文章列表接口的映射，hssonline/amte 等可共用。
3. **已有中文包的 `latest_issue`**：玛格泰克、CBPT 已完成并导入；可按上面的回收清单逐步把验证通过的刊加回可选目录。
4. **明确止损**：412/验证码/登录墙（如 jnuaa）与 500 站点（潮学研究）不投入对抗式修复；改用浏览器会话或官方接口，或记录跳过。

## 合规边界

以上只访问公开首页、当期目录和公开 JSON 接口，不下载全文、不绕过登录/验证码、不关闭 TLS 校验。抽样结论不代表站点长期可用，正式接入前仍需按刊复测并保留失败告警。
