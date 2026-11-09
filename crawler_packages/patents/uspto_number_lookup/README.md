# USPTO 授权专利号码查询

按官方 Patent Public Search Basic 页面使用的公开会话、号码查询和 HTML 详情流程取得美国授权专利元数据。仅用 Python 标准库。

query 中输入授权号，用分号或换行分隔。例如 `US 7,835,543; US 8,471,950`。支持 B1/B2 输入，但查询按授权数字号码进行，由官方返回实际 kind code；不支持申请号和申请公开号。

申请日期来自 `Filed` 或 `Filed (or PCT Filed)`，后者可能是 PCT 申请日而非美国国家阶段进入日；授权日期来自 `datePublished`，申请号来自 `Appl. No.`。Applicant 与 Assignee 分别保存，不能用受让人替代申请人；旧专利缺少 Applicant 时返回 null 并警告。摘要原文保留，不生成摘要。

本包分页游标仅表示这批输入号码的处理位置。部分失败保留成功数据但不推进游标，平台重跑通过稳定文献 ID 去重。

2026-10-13 官方匿名会话可用；官方页面通知从 2026-11-07 起需登录 USPTO 账户。届时如返回 401/403，本包报告 AUTH_REQUIRED，需改接授权接口或登录流程。

正式平台导入：`python platform_main.py import crawler_packages/patents/uspto_number_lookup`。
