# 数据库 v5 工具包存储设计

> 历史过渡提案，已被 [全新系统技术规范](crawler-platform-technical-spec-v1.md) 替代。后续执行以新规范为准，不再按本文从旧 v4 迁移，新系统数据库版本独立从 1 开始。

状态：设计提案，2026-09-19。现有代码、sql/init.sql 和运行数据库仍采用 v4。本文不表示迁移已经执行。

## 已确认方向

平台负责导入工具包、验证协议、准备运行环境、定时启动、接收结果并提供查询 API。外部开发者负责爬虫逻辑。

每个逻辑工具包一张结果表。业务模块只是分类；同一个包可以采集多个站点，站点通过结果字段标识。相同包重复导入或升级不新增结果表。第一版一个包归属一个业务分类、声明一种输出结构。

## 固定管理表：建议 7 张

| 表 | 关键字段 | 用途 |
| --- | --- | --- |
| crawler_packages | id、package_key、name、module_name、package_version、protocol_version、schema_version、table_name、manifest_json、default_config_json、install_path、status、created_at、updated_at | 包注册、表定位和运行配置 |
| monitors | id、name、query_text、aliases_json、schedule_type、schedule_time、weekday、timezone、enabled、last_run_at、next_run_at、created_at、updated_at | 长期关键词任务，不再绑定单个模块 |
| monitor_packages | monitor_id、package_id、enabled、item_limit、config_json、cursor_json、last_success_at、last_error、updated_at | 任务选择包及任务级参数；复合主键 |
| monitor_runs | id、monitor_id、trigger_type、status、total_fetched、total_inserted、total_updated、started_at、finished_at、error_message | 一次任务运行汇总 |
| package_runs | id、run_id、package_id、attempt_no、package_version、schema_version、artifact_digest、request_snapshot_json、status、exit_code、fetched、inserted、updated、started_at、finished_at、log_path、error_message | 每包每次尝试的进程执行、版本和结果；唯一键(run_id, package_id, attempt_no) |
| monitor_resource_matches | monitor_id、package_id、resource_uid、first_package_run_id、last_package_run_id、first_matched_at、last_matched_at、match_count | 任务到包内资源的长期关联；复合主键(monitor_id, package_id, resource_uid) |
| schema_migrations | version、name、applied_at | 平台管理表结构版本 |

字段为设计级清单，正式迁移还需补充 SQL 类型、默认值、索引、外键删除策略和版本校验。包级 schema_version 与平台 schema_migrations 分开管理。

crawler_packages 的 package_key 和 table_name 各自唯一；monitor_packages 和 package_runs 对包建立真实外键。运行快照脱敏，凭证只保留引用。升级保留旧包文件及摘要，便于追溯历史执行。

## 动态结果表：N 张

平台分配例如 pkg_data_000001、pkg_data_000002 的安全表名，保存在 crawler_packages.table_name。外部包不能直接指定数据库表名或提供任意 SQL。

每张表由固定公共字段和包声明的业务字段组成。

公共字段：id、resource_uid、identity_hash、content_hash、first_package_run_id、last_package_run_id、first_seen_at、last_seen_at。resource_uid 和 identity_hash 各设唯一键；身份规则在包清单声明，必须独立于关键词、运行编号和正文更新。

业务字段示例：

- 百度百科包：title、url、summary、content、categories。
- 论文包：title、url、doi、authors、abstract、journal、publication_date。
- 专利包：title、publication_number、applicants、abstract、application_date。

包清单增加 output_schema、identity_fields 和字段到公共 API 的映射。第一版使用受限声明类型，如 string、text、integer、decimal、boolean、date、datetime、array、object；平台负责确定性映射到 MySQL 类型。只有 array/object 等嵌套值使用 JSON；标题、DOI、日期等直接建立列。禁止覆盖公共字段；限制列数、字段长度和可创建索引。

输出逐条校验，平台注入管理字段。适配器不获得数据库连接信息。身份字段缺失不能静默写入随机身份，否则重复运行无法去重。

## 关系及查询

monitors 与 crawler_packages 通过 monitor_packages 多对多关联。monitors 一对多 monitor_runs；monitor_runs 一对多 package_runs；crawler_packages 一对多 package_runs，并一对一定位自己的动态结果表。

monitor_resource_matches 的 package_id 是真实外键；resource_uid 指向动态表，是逻辑关联。平台通过注册表查出表名，再使用字段白名单与参数化条件查询。MySQL 普通外键不能根据 package_id 自动切换目标表。

跨包接口返回公共字段及包专有字段，使用包声明的字段映射，不要求所有包包含正文或摘要。第一版跨包结果可按包分组提供；全局排序和分页需单独定义，不得将各表各取一页简单拼接伪装为完整全局分页。

同一个包内同一资源被多个任务命中只保存一份，关联表多行。不同包采到同一文章允许分别保存，暂不承诺跨包实体合并。

## 导入与升级

导入目录 -> 校验清单和输出结构 -> 准备独立环境 -> 样本验证 -> 登记 installing -> 创建结果表 -> 检查字段和索引 -> 标记 ready。

导入流程按 package_key 加锁，并可重试。同包同版本重复导入应幂等；同版本不同文件摘要应拒绝覆盖。只有 ready 包可用于调度。

MySQL 建表和改表涉及隐式提交，不能把整个安装流程当作一个可整体回滚的事务。失败登记 install_failed，保留可诊断状态；恢复时检查真实表结构，禁止删除已经存在的数据来重试。

升级沿用原表。第一版支持经过检查的新增可空字段；删除字段、收窄类型、变更身份规则必须有显式迁移方案。运行绑定已安装版本和结构版本，避免执行中混用新旧包。

## 执行和保留策略

一页有效结果、任务资源关联、相应游标在同一 InnoDB 事务内提交；外部采集和进程运行不放进数据库事务。失败保留旧游标，可重抓后去重。来源故障独立记录，不阻断其他包。

停用或卸载包默认保留注册记录和结果表，以 retired 状态停止调度。删除历史数据和删表是独立明确操作。动态表始终通过平台目录可追溯。

## 从 v4 迁移的方案

1. 备份并建立独立迁移验证环境；先核对真实数据库版本与行数。
2. 按现有来源建立包映射，四个新闻来源分别封装为包。
3. 根据包字段声明创建各包表，将 news_resources 按 source_key 复制；保留 resource_uid 和时间信息。
4. sources 映射 crawler_packages；monitor_sources 映射 monitor_packages。现有配置和游标保留。
5. monitor_runs 保留运行编号；依据 source_results_json 转换 package_runs，无法从历史数据还原的退出码、版本和请求快照设为未知，不伪造。
6. 通过旧资源的 source_key 将任务资源关联映射到 package_id；检测重复或孤立 UID，输出迁移报告。
7. 对论文、专利现有数据按实际 source_key 检查和迁移，即使当前目录为空也不假设数据库为空。
8. 核对行数、身份、关联和采集更新结果，切换引擎与 API，再登记新版本。
9. 旧表保留为只读备份；切换前备份用于回退，切换后新写入数据的回迁方案应在上线前验证。禁止启动时自动删除旧表。

实施依赖：工具包协议、输出声明校验、动态表存储、包进程执行器和任务调度都需要配套调整。只修改建表脚本无法完成此次架构转换。
