# 补充期刊包

这是 2377 期刊目录的暂存/补充包，由原 `openalex_journals` 包合并而来。

## 当前结构

- `journals.json`：**66 本可运行期刊**，全部来自 2377 目录中的外文出版商组；沿用 OpenAlex/Crossref 适配器，支持 `keywords` 和 `latest_issue`。文章元数据来自 API，**不是从期刊官网页面爬取**；UI 标签为 `采集:OpenAlex/Crossref` + `非官网` + `目录:2377`。
- `pending_journals.json`：**初始 1480 本 2377 未适配期刊；截至 2026-11-21 已回迁 173 本，剩余 1307 本**，保留目录原始 `journal_key`、刊名、官网 URL、供应商、模板组、目录来源文件，并标注 `source_system=2377_catalog`、`status=pending_adapter`、`data_source=pending`、`planned_data_source=official_site`；UI 标签为 `采集:待适配` + `官网候选` + `目录:2377`，详细的 `source_group` 保留在 JSON 字段。文件保留全部 1480 行，`status=promoted` 的记录标注回迁去向，`status=pending_adapter` 的才是剩余待办；该文件不参与调度，也不会出现在选刊界面。

待适配数量按来源组：

| 来源组 | 数量 |
| --- | ---: |
| 知网其他域名 `cnki` | 313 |
| 勤云 `qinyun` | 262 |
| 玛格泰克 `magetech` | 254 |
| 知网 CBPT `cnki_cbpt` | 222 |
| 北大方正 `founder` | 157 |
| 仁和汇智 `rhzh` | 139 |
| PaperOnce `paperonce` | 75 |
| VSB `vsb` | 28 |
| 中华医学会 `yiigle` | 14 |
| 西安三才 | 2 |
| 其他供应商/目录外遗留 | 14 |

## 来源标注说明

- `采集:OpenAlex/Crossref` + `非官网`：文章元数据实际来自 OpenAlex/Crossref API，不是期刊官网页面。
- `采集:待适配` + `官网候选`：官网 URL 已知，但还没有对应采集适配器。
- `目录:2377`：期刊记录/URL 来自 2377 目录；具体来源组保留在 JSON 的 `source_group`/`source_file` 字段。
- 后续官网适配通过的刊会改为 `采集:官网`/`采集:官网当期目次`，并保留官方 URL 证据。
- 平台选刊标签最多保留 4 个、每个最多 24 字，因此详细来源写在 JSON 字段和补充包报告中。

## 使用与边界

- 当前只有 `journals.json` 的 66 本可建任务，且它们是 API 来源；`pending_journals.json` 是分类工作的输入，不是可运行名单。
- 目录不预打“低空”标签；是否低空相关由后续 Agent 按文章内容判断。
- 每本刊都保留来源字段，后续分类时按 `source_group`、模板、URL 证据和验收结果迁移，不再手工凭印象挑选。
- 包版本 `1.0.2`，功能与结果字段沿用原 OpenAlex/Crossref 包。

## 测试

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s crawler_packages/academic/supplement_journals/tests -v
```
