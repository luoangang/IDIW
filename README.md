# 爬虫工具包管理与执行平台

当前建设主线是一个独立的爬虫工具包平台。第三方开发者按协议提交目录，平台负责验证、为每个包建立独立结果表、创建关键词任务、定时启动独立进程、去重入库并提供查询 API。新工具包不继承平台类，也不能直接连接数据库。

## 当前状态

- 已实现工具包清单、参数、结果和输出结构协议。
- 已实现七张管理表以及“每个工具包一张结果表”的自动建表机制。
- 已实现独立环境、进程执行、持久队列、任务关联、游标和结果查询。
- 已提供百度百科、Wikipedia、Google 新闻 RSS 三个标准工具包。
- 默认使用独立数据库 `crawler_platform` 和 API 端口 `8090`。

## 快速启动

```powershell
.\.venv\Scripts\python.exe -X utf8 platform_main.py init-db
.\.venv\Scripts\python.exe -X utf8 platform_main.py import crawler_packages\baidu_baike
.\.venv\Scripts\python.exe -X utf8 platform_main.py import crawler_packages\wikipedia
.\.venv\Scripts\python.exe -X utf8 platform_main.py import crawler_packages\google_news_rss
```

执行 `启动平台.bat` 后，API 地址为 `http://127.0.0.1:8090`。详细命令见 `docs/crawler-platform-quickstart.md`。

## 核心目录

- `crawler_platform`：全新平台的协议、存储、导入、执行、调度和 API。
- `crawler_packages`：三个可独立导入的示例工具包。
- `protocol/v1`：机器可读协议 Schema。
- `docs/crawler-platform-technical-spec-v1.md`：技术实施规范。
- `tests_platform`：新平台契约测试。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests_platform -v
```
