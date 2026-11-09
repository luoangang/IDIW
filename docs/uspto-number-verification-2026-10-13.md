# USPTO 六个真实专利号验收

## 2026-10-14 实时复测

用同一组六个号码重新运行 `uspto_number_lookup` 1.0.2，USPTO 官方查询返回 `completed`、6 条、`error=null`。六条均有标题、原始摘要、申请日期和受让人；7835543、7139533、6612488 的 Applicant 仍为空，插件报告 `FIELDS_MISSING`。本次六条的标题、摘要、申请人、受让人、申请日期及授权日期与独立表 `pkg_data_000008` 的六条现存记录一致。

本次原始输出保存在 `crawler_platform_runtime/verification/uspto-six-20261014-live/`。初次在受限网络环境中复测得到 `NETWORK_ERROR`；放通正常网络后，**同一请求**成功。本次仅复测插件实时获取并核对数据库，没有再次执行平台入库。

验收日期：2026-10-13。仅推进专利查询；此前 RSS 扩充、导入、重复采集与相关性检查成果继续保留。

## 实际结果

从 USPTO Patent Public Search 的官方检索及 HTML 详情接口直接查询，最终单批 completed、6 条、error=null。标题、摘要、Filed 申请日期、授权日期、申请号及受让人均取得。前三轮观察到 HTTP 429，本包以 5 秒请求间隔及有限退避重试处理；失败时不伪装成空结果。

| 授权号 | 标题 | 申请日期 | 授权日期 |
| --- | --- | --- | --- |
| US 7,835,543 | Object detection method | 2007-04-25 | 2010-11-16 |
| US 8,471,950 | Signal processor for adjusting image quality of an input picture signal | 2009-11-18 | 2013-06-25 |
| US 7,139,533 | Mobile communication terminal | 2003-08-15 | 2006-11-21 |
| US 10,349,030 | Video recording and reproducing method, and video reproducing apparatus and method including thumbnails for moving pictures and still pictures | 2016-08-30 | 2019-07-09 |
| US 6,612,488 | Method and system to prevent fraudulent payment in credit/debit card transactions, and terminals therefor | 2001-10-31 | 2003-09-02 |
| US 10,244,284 | Display apparatus and video processing apparatus | 2018-02-07 | 2019-03-26 |

7835543、7139533、6612488 的官方详情未列 Applicant；保留 null 和 FIELDS_MISSING 警告。Assignee 独立保存，不能当作 Applicant。其他三个号码取得官方 Applicant。所有日期区分申请与授权，不用授权日期替代申请日期。

## 平台验证

包键 uspto_number_lookup，分类 patents，包 ID 8，独立表 pkg_data_000008。验收任务 ID 9。对已实时获取的同一批真实输出，通过平台执行结果校验、字段校验和正式入库流程重放两次：运行 26 新增 6 条；运行 27 新增 0 条、未变 6 条。无拒收、无更新。这个重放验证数据库去重，不代表两次独立实时查询。

原始查询输出：crawler_platform_runtime/verification/uspto-six-20261013-final/items.jsonl 和 result.json；入库统计：同目录 platform_ingestion.json。包 tests 下保存六条真实样例。

离线测试通过：号码规范化与去重、日期语义、申请人与受让人分离、部分失败保留成功记录且不提交游标。

官方页面会话通知从 2026-11-07 起要求登录 USPTO 账户。当前匿名查询实测成功，但这一公开网页接口不是稳定 API 承诺，需在访问要求生效时适配。401/403 返回 AUTH_REQUIRED，不绕过登录。

官方说明：https://www.uspto.gov/patents/search/patent-public-search/ 。实际数据详情在 https://ppubs.uspto.gov/basic/ 查询号码后查看 Text。
