# 新爬虫工具包平台快速开始

平台唯一入口是 `platform_main.py`，默认使用数据库 `crawler_platform` 和端口 8090。Windows 下可直接运行根目录的 `启动平台.bat`。

管理界面按工作流程分为四个页面：`/sources` 管理采集源、导入工具包和修改默认配置；`/monitors` 管理监控任务，新建任务和任务来源设置各有独立页面；`/runs` 查看近期运行，可按任务和状态筛选，并进入 `/runs/{id}` 查看各来源执行结果和失败原因；`/data` 分页预览已入库数据，支持任务、来源和标题组合筛选，点击标题查看详细字段及关联任务。根地址默认打开监控任务页面，各页面链接支持直接访问、刷新和浏览器前进后退。

首次使用：

```powershell
.\.venv\Scripts\python.exe -X utf8 platform_main.py init-db
.\.venv\Scripts\python.exe -X utf8 platform_main.py import crawler_packages\reference\baidu_baike
.\.venv\Scripts\python.exe -X utf8 platform_main.py import crawler_packages\reference\wikipedia
.\.venv\Scripts\python.exe -X utf8 platform_main.py import crawler_packages\news\google_news_rss
```

创建和运行一个监控任务：

```powershell
.\.venv\Scripts\python.exe -X utf8 platform_main.py create-monitor "人工智能监控" "人工智能" --packages baidu_baike wikipedia google_news_rss
.\.venv\Scripts\python.exe -X utf8 platform_main.py run 1
.\.venv\Scripts\python.exe -X utf8 platform_main.py worker --once
```

每个 `worker --once` 处理一个包；运行三次可处理示例任务的三个包。长期运行使用根目录的 `启动平台.bat`，它启动 API、Worker 和 Scheduler，确认网页服务就绪后才报告成功。启动失败时查看 `logs/api.log`、`logs/worker.log` 和 `logs/scheduler.log`。

主要 API：

- `GET /api/v1/packages`
- `POST /api/v1/packages/import`
- `POST /api/v1/monitors`
- `POST /api/v1/monitors/{id}/runs`
- `GET /api/v1/runs/{id}`
- `GET /api/v1/packages/{key}/records`
- `GET /api/v1/data?monitor={id}&source={key}&q={标题关键词}&page=1&limit=25`
- `GET /api/v1/packages/{key}/records/{resource_uid}`
- `GET /api/v1/monitors/{id}/records`

完整协议与数据库规则见 `crawler-platform-technical-spec-v1.md`。工具包样例位于 `crawler_packages`，机器协议位于 `protocol/v1`。
