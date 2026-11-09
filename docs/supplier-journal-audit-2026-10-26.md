# 勤云、仁和汇智、西安三才逐刊测试（2026-10-26）

本轮从工作簿分类目录取出勤云 365 家、仁和汇智 261 家、西安三才 3 家，另加入已核实属于勤云模板的《软件学报》，共 **630 家候选**。每家均独立发起一次关键词检索（`研究`），记录期刊、URL、结果数、首条标题及错误。凡能返回文章者，再做三条记录复测和不可能命中的关键词 `zxqv908172nomatch` 反向测试；输出条目须通过平台协议校验。可复核的逐刊总表为 [`journal_catalog/supplier-journal-audit-2026-10-26.csv`](../journal_catalog/supplier-journal-audit-2026-10-26.csv)，原始 JSONL 日志保留在同目录。

| 包 | 候选 | 已验证并入包 | 测试词无结果 | 模板/网络失败 | 其他 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 勤云 | 366 | 104 | 3 | 259 | 0 |
| 仁和汇智 | 261 | 122 | 17 | 121 | 1 家忽略关键词 |
| 西安三才 | 3 | 1 | 0 | 1 | 1 家过滤复测遇 502 |
| 合计 | **630** | **227** | **20** | **381** | **2** |

## 验收边界

- `verified` 表示本轮取得真实文章，且反向检索未返回文章；它不是长期可用性保证。每个通过站点的记录已做协议字段校验，绝大多数复测返回 3 条。《工程科学学报》三条复测曾超时，但首轮和反向过滤均通过，另有一次单站 smoke 测试取得 3 条；总表保留该超时。
- `no_results_for_test_query` 表示接口回应正常但测试词没有文章，不能推断站点不可采。勤云的 3 家又用“人工智能”复测，仍无结果；仁和汇智的 17 家尚未完成第二关键词复测。
- `failed` 包括 316 家明确不匹配已实现模板、其他网络/解析错误。它们不进入可选目录，但不代表这些期刊没有其他可行采集方式。
- 仁和汇智《岩矿测试》对无关关键词仍返回文章，属于**检索词被忽略**，故剔除。西安三才《安徽师范大学学报（社会科学版）》正向及三条记录复测通过，但反向检索遇 HTTP 502，列为 `filter_unconfirmed`，暂不入包。
- 本轮只验证元数据检索、字段与结果计数，不下载全文；没有对每篇文章的 DOI、摘要等字段完整率作保证，也未持续监测多日稳定性。额外联网补测遇到执行权限额度限制，未将不确定站点冒充通过。

## 复现与交付

三个包位于 `crawler_packages/academic/qinyun_journals`、`rhzh_journals`、`sancai_journals`，均尚未导入平台。每包只保留本轮 `verified` 的期刊目录；同一供应商的多家期刊共用一个包和一张结果表，以 `journal_key` 区分。源工作簿分类目录、失败记录不会因缩减安装目录而删除。

```powershell
python scripts/audit_supplier_journals.py rhzh_journals --journal-key b11e9e7fdb08aa16 --query 研究 --records 3 --tag retest
python scripts/finalize_supplier_journal_audit.py
python scripts/build_supplier_journal_packages.py --verified-only
```

`audit_supplier_journals.py` 和 `verify_supplier_keyword_filtering.py` 均从原始候选目录读取，后续可单刊补测，不依赖已缩减的安装清单。`build_supplier_journal_packages.py` 不带 `--verified-only` 会生成全部候选目录，仅用于重新审计，不应作为交付包直接导入。
