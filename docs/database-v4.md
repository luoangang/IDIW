# 数据库版本 4

版本 4 在“每个业务模块一张资源表”的基础上精简运行和配置表。数据库共 9 张物理表，其中 `schema_migrations` 只用于内部版本管理。

## 表结构

### 配置与监控

- `sources`：所有新闻、论文和专利来源的注册信息、启停状态、默认上限和来源配置。
- `monitors`：用户创建的每日或每周关键词监控任务。
- `monitor_sources`：任务选择的来源、任务级上限、来源配置、增量游标和最后成功时间。

### 执行记录

- `monitor_runs`：一次手动或定时执行及其聚合数量；`source_results_json` 保存各来源的运行摘要。

### 模块数据

- `news_resources`：百科、RSS、搜索结果等新闻与开放网络资源。
- `paper_resources`：全部论文及 DOI、作者、期刊、卷期等专业字段。
- `patent_resources`：全部专利及申请号、发明人、分类、法律状态等专业字段。
- `monitor_resource_matches`：监控任务与资源的多对多关系。

### 技术管理

- `schema_migrations`：数据库模式版本。

## JSON 边界

JSON 只用于结构随来源变化、无需外键约束的数据：

- 来源配置和支持模式；
- 监控别名与增量游标；
- 一次运行的来源结果摘要；
- 来源特有元数据和论文作者等列表字段。

来源、监控任务和资源之间的关系不放入 JSON。

## 数据身份

- `resource_uid`：跨运行稳定的资源编号，用于监控匹配。
- `identity_hash`：来源内部稳定身份，用于避免不同关键词重复插入。
- `canonical_hash`：发现不同来源可能指向同一内容，但不强制合并。

## 从版本 3 迁移

迁移过程会先把 `run_source_results` 汇总到 `monitor_runs.source_results_json`，把可识别的任务游标合入 `monitor_sources`，然后删除旧运行事件、期刊目录、独立游标以及更早版本的只读备份表。论文期刊现在作为 `paper` 模块来源统一注册到 `sources`。
