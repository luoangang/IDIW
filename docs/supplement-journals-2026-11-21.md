# 补充期刊包与 2377 待适配清单（2026-11-21）

> 2026-11-22 更新：`pending_journals.json` 当前 **promoted 958、blocked 519、pending_adapter 3**（2377 目录覆盖 1855）。下文的 1307 本及供应商分布表是 2026-11-21 快照，不再作为当前口径；最新进度见 [current-progress.md](current-progress.md)。

## 结构

- 包：`supplement_journals` `1.0.2`，显示名“补充期刊包”。可运行 66 本；pending 初始 1480 本，2026-11-21 已回迁 173 本（玛格泰克 60、仁和 18、西安三才 1、PaperOnce 69、北大方正 20、勤云 5），剩余 1307 本；PaperOnce 另建独立包 `paperonce_journals`。
- `journals.json`：66 本可运行期刊，全部来自 2377 目录外文出版商组；每行带 `catalog_source=2377_catalog`、`data_source=openalex_crossref`、`status=verified`，UI 标签为 `采集:OpenAlex/Crossref` + `非官网` + `目录:2377`。**文章元数据来自 OpenAlex/Crossref API，不是期刊官网页面。**
- `pending_journals.json`：初始 1480 本 2377 未适配期刊（已回迁 79 本，剩余 1401 本）；每行保留目录原始键、刊名、官网 URL、供应商、模板组、来源文件，并标注 `catalog_source=2377_catalog`、`data_source=pending`、`planned_data_source=official_site`、`status=pending_adapter`，UI 标签为 `采集:待适配` + `官网候选` + `目录:2377`；详细的 `source_group` 保留在 JSON 字段。
- `pending_journals.json` 不参与调度，也不进入选刊界面；后续按模板组补适配器、复测通过后再移入 `journals.json`。

## 待适配来源分布

| 来源组 | 初始待适配 | 已回迁 | 剩余 |
| --- | ---: | ---: | ---: |
| 知网其他域名 `cnki` | 313 | 0 | 313 |
| 勤云 `qinyun` | 262 | 5 | 257 |
| 玛格泰克 `magetech` | 254 | 60 | 194 |
| 知网 CBPT `cnki_cbpt` | 222 | 0 | 222 |
| 北大方正 `founder` | 157 | 20 | 137 |
| 仁和汇智 `rhzh` | 139 | 18 | 121 |
| PaperOnce `paperonce` | 75 | 69 | 6 |
| VSB `vsb` | 28 | 0 | 28 |
| 中华医学会 `yiigle` | 14 | 0 | 14 |
| 西安三才 | 2 | 1 | 1 |
| 其他供应商/目录遗留 | 14 | 0 | 14 |
| 合计 | 1480 | 173 | 1307 |

## 本次回迁（2026-11-21）

- 两批当期探测 + PaperOnce 探测共回迁 148 本：玛格泰克 60、仁和汇智 18、西安三才 1、PaperOnce 69、北大方正 20、勤云 5。
- 新补期刊归入 `magetech_journals` 1.1.4、`rhzh_journals` 1.0.4、`sancai_journals` 1.0.3；逐刊清单见 [promoted-2026-11-21.csv](../journal_catalog/promoted-2026-11-21.csv)。
- CBPT 本批 80 本全部 HTTP 500，暂不硬加。
- 2377 目录内覆盖 1070 本，剩余 1307 本。

## 本次清理

- 原 `openalex_journals` 源码包删除；66 本已迁入补充包。
- 用户任务 #4“人工智能”迁到补充包，原有旗舰刊和补充刊配置保留。
- 旧演示任务 #3 及其运行记录删除；旧结果表 `pkg_data_000010` 删除。
- 删除前数据库备份：`.local/backups/crawler_platform-before-openalex-delete-20261121.sql`。

## 下一步适配顺序

1. 勤云已完成全量 262 本探测，5 本回迁、257 本失败/无当期页；详见 `journal_catalog/qinyun-audit-2026-11-21.csv`。
2. 玛格泰克剩余 194、CBPT 222、仁和剩 121：继续按当期模式复测。
3. 北大方正 157、PaperOnce 75：按已发现的 JSON API 做通用适配器。
4. 知网其他 313、VSB 28、中华医学会 14：模板碎片化，最后做或明确止损。

所有迁移必须保留来源、模板、URL 证据和验收状态，不预打“低空”标签；低空相关性由后续 Agent 按文章内容判断。
