# 外文重点期刊元数据包

按检索词采集 Nature、Science、PNAS、Cell 的公开论文元数据；使用 OpenAlex 检索。缺失摘要时，Nature 论文先尝试文章页公开的 Abstract 区块，再尝试 Crossref；其他期刊尝试 Crossref。不会下载全文或 PDF，也不保证每条记录都有摘要。仅保留 DOI、期刊 ISSN 和标题有效的结果；Nature 的 `d41586` 新闻记录以及明显的勘误/撤稿标题默认排除。

## 导入与配置

将整个目录作为插件包导入平台，Python 运行时为 3.14，依赖仅为标准库。包本身不会自动导入。可选密钥 `OPENALEX_API_KEY` 对应平台提供的 `CRAWLER_SECRET_OPENALEX_API_KEY`；建议长期定时运行时配置 OpenAlex 免费 API 密钥。

参数：`journal_keys` 选择四刊；`search_terms` 用英文检索词补充任务关键词和别名；`lookback_days` 默认 30 天，设为 0 表示不限时间；`per_journal_limit` 默认每刊最多检查 100 条候选；`timeout_seconds` 默认 20 秒；`require_abstract` 默认 false。`request.time_range` 的起止日期优先于回看天数。任务关键词为中文时，请在任务别名或 `search_terms` 中明确提供英文检索词，例如“具身智能”对应 `embodied AI`；插件不自动翻译。

每次运行重新检索时间窗，按 DOI 去重；平台的包结果表负责跨次运行识别已有记录。本包不提供增量游标。结果中的摘要可能为空，Nature 页面和 Crossref 补充也不保证成功。每次运行最多补查 20 条缺摘要记录。API 返回数量超过配置上限或某刊失败时，会在运行警告中说明；部分期刊失败但其余期刊成功时返回 `partial`。

公开接口：[OpenAlex API](https://docs.openalex.org/how-to-use-the-api/get-lists-of-entities/search-entities)、[Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)；Nature 摘要仅取其公开文章页的 Abstract 区块。采集结果不能等同于出版社完整馆藏或全文授权。
