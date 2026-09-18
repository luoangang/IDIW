# 模块化情报采集器

这是一个面向新闻、论文和专利的可扩展采集平台。系统将业务模块、来源插件、执行任务、物理存储和统一索引分开，新增来源不需要修改采集引擎。

## 当前状态

- `news`：已接入百度百科、维基百科、Google 新闻 RSS、DDGS。
- `paper`：模块和物理目录已经建立，等待接入中文论文平台适配器。
- `patent`：模块和物理目录已经建立，等待接入专利来源。
- 数据库模式版本：`4`，共 9 张物理表（8 张业务表和 1 张版本表）。

## 启动

```powershell
.\.venv\Scripts\python.exe -X utf8 main.py --init-db
.\.venv\Scripts\python.exe -X utf8 main.py --panel
```

管理面板默认地址为 `http://127.0.0.1:8080`。数据库连接参数从 `.env` 或环境变量读取。

命令行采集示例：

```powershell
.\.venv\Scripts\python.exe -X utf8 main.py "人工智能" --module news --mode search
```

## 核心目录

- `collector/modules`：业务模块注册信息和能力声明。
- `collector/sources/<module>`：按业务模块物理隔离的来源入口。
- `collector/sources/base.py`：统一请求、资源记录和来源插件协议。
- `collector/engine.py`：与具体来源无关的任务编排。
- `collector/storage.py`：来源目录同步、模块资源表和监控运行记录。
- `sql/init.sql`：幂等数据库结构。
- `docs/architecture.md`：架构与数据库边界。
- `docs/database-v4.md`：当前精简数据库结构与迁移说明。
- `docs/source-plugin-standard.md`：新增来源必须遵循的标准。

## 数据原则

1. 每个业务模块拥有一张物理资源表：新闻、论文、专利彼此隔离。
2. 同一模块内通过 `source_key` 区分来源，来源数量不会增加物理表数量。
3. 新闻使用公共字段和扩展元数据；论文与专利在模块表中保留专业字段。
4. 资源身份与搜索词无关；一个资源可以被多个监控主题发现。
5. 搜索和增量同步使用同一执行协议，任务来源游标保存在 `monitor_sources`。
6. JSON 只保存来源配置、游标、运行摘要和来源特有元数据；实体关系使用关系表。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
