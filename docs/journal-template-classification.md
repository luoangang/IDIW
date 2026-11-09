# 期刊模板分类与采集包状态

原始文件：`期刊名_URL_供应商_含统计.xlsx` 的 `表1`，共 10,105 条数据行。筛选规则：期刊名、URL、供应商均非空；URL 为 HTTP(S)；剔除供应商标记为“独立/其他官网（供应商未知）”和“网页过期/停刊或无法访问”的行。保留 2,377 条，舍弃 7,728 条。`表2` 的预汇总数字与逐行筛选条件不同，以可复现的 `scripts/build_journal_catalog.py` 为准。

输出：`journal_catalog/journals.json` 保留原始行号、期刊名、URL、供应商、模板组、证据级别与稳定期刊键；`summary.json` 记录数量；`journal_catalog/groups/` 按模板组拆成独立清单，供后续逐组制作采集包。`url_signature` 表示 URL 域名呈现已知平台特征，`supplier_label_only` 仅说明表格标注了供应商，**不证明该站点沿用同一检索接口**。

| 模板组 | 条数 | 当前处理 |
| --- | ---: | --- |
| 同方知网 CBPT 域名 | 731 | 已建 `cnki_cbpt` 独立包；731 家均已逐站测试，509 家返回文章并通过字段校验；见 [验收报告](journal-audit-2026-10-23.md) |
| 同方知网其他域名 | 313 | 保留目录；接口差异待细分，不混进 CBPT 包 |
| 勤云 | 365 | 新旧模板已覆盖部分站点；另加《软件学报》共 366 家逐刊测试，104 家通过并进入 `qinyun_journals`，见 [本轮报告](supplier-journal-audit-2026-10-26.md) |
| 玛格泰克 | 350 | 已全部并入同一个 `magetech_journals` 包的可选目录；187 家本轮返回文章，32 家无测试词结果，131 家失败，详见 [验收报告](journal-audit-2026-10-23.md) |
| 仁和汇智 | 261 | 逐刊测试后 122 家进入 `rhzh_journals`；一个站点被发现忽略检索词，见 [本轮报告](supplier-journal-audit-2026-10-26.md) |
| 北大方正 | 157 | 保留目录；检索接口通常还需站点级 ID，待提取 |
| PaperOnce | 75 | 保留目录；待验收 |
| VSB | 28 | 保留目录；待验收 |
| 中华医学会 | 14 | 保留目录；待验收 |
| 其他明确标记的供应商 | 83 | 按原供应商单独分组，数量较少，待模板核验 |

每个真正统一的模板使用一个包、一张该包的结果表；期刊身份留在结果字段 `journal_key` 和 `journal_name` 中。不要按期刊建表。安装包只会创建该包的结果表，不会为目录内每条期刊创建表。`cnki_cbpt` 默认只选已实测的三个期刊；添加其他 `journal_key` 前可查验收报告中的逐站结果。

工作簿中另有西安三才 3 家候选，本轮仅 1 家完成正反向检索验证并进入 `sancai_journals`。详细测试状态见 [逐刊报告](supplier-journal-audit-2026-10-26.md)。

重新整理目录：

```powershell
python -m pip install openpyxl
python scripts/build_journal_catalog.py "C:\Users\123\Desktop\期刊名_URL_供应商_含统计.xlsx" --output journal_catalog --cbpt-package-dir crawler_packages/academic/cnki_cbpt
```
