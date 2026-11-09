# CBPT 期刊门户采集包

按关键词查询目录内的 `*.cbpt.cnki.net` 站点，获取标题、作者、摘要、期次和文章链接。使用网站公开搜索页面的 `listContent` 接口，不下载全文。

`journals.json` 仅列出逐刊实测取得文章且通过字段校验的 509 家期刊；原工作簿中的其他候选和失败记录保留在审计目录，不在平台选择器中显示。`journal_keys` 为需要采集的期刊键数组，默认选择三家已完成实测的站点。建议每批不超过 30 家，并分别监测失败告警。历史验收不保证站点长期可用。

参数：`journal_keys`、`per_journal_limit`、`timeout_seconds`。平台请求的 `limit` 是整包上限，会尽量平均分给所选期刊；`per_journal_limit` 是每家期刊上限。运行结束时可查看 `warnings` 了解部分站点失败情况。
