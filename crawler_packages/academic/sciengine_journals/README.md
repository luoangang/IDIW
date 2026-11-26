# SciEngine 当期期刊包

读取 SciEngine 公开 JSON API（`selectArticlesInJournalOfVolumeAndIssue`）获取 14 本国内期刊的当期文章元数据。期刊入口来自 WorkBuddy `c2a-sciengine-rescue-2026-11-24` 的验收结果，按 `current_url` 去重后保留 14 本（`新型炭材料`、`燃料化学学报` 的新旧名同刊同入口已合并，旧名保留在 `name_aliases`）。

## 来源与边界

- 数据来自 SciEngine 官网公开 API，不是页面爬取；`source_api=sciengine`。
- 只采集文章元数据：标题、作者、摘要、DOI、年/卷/期/页码，以及 `pdf_url` 链接。
- **不下载 PDF**，只保存 `https://www.sciengine.com< pdfPath>` 链接。
- 不绕过登录、验证码或付费墙。
- `journals.json` 的 `json_api` 是 2026-11-24 核验过的当期（current issue）；新一期上线后需要更新对应 `json_api` / `current_url`，不是自动追新。
- 列表 API 的 `intro` 字段作为摘要；`固体电子学研究与进展` 的列表接口无摘要，`abstract` 为空。
- 目录页中的卷首语、序言、编者按等非文章条目会被过滤。

## 参数

- `journal_keys`：默认全部 14 本。
- `collect_mode`：仅支持 `latest_issue`（读取已核验的当期目次）。
- `per_journal_limit`：每刊最多条数，默认 50。
- `timeout_seconds`：单次 API 超时，默认 20 秒。
- 平台请求的 `limit` 是单次总上限，会按所选刊数均分；需要整期全量时请提高 `limit` 或减少选刊。

## 测试

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest crawler_packages/academic/sciengine_journals/tests -q
```
