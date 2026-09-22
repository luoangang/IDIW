# 新爬虫工具包平台快速开始

平台唯一入口是 `platform_main.py`，默认使用数据库 `crawler_platform` 和端口 8090。Windows 下可直接运行根目录的 `启动平台.bat`。

首次使用：

```powershell
$env:PATH='C:\ProgramData\Anaconda3\Library\bin;C:\ProgramData\Anaconda3\DLLs;'+$env:PATH
.\.venv\Scripts\python.exe -X utf8 platform_main.py init-db
.\.venv\Scripts\python.exe -X utf8 platform_main.py import crawler_packages\baidu_baike
.\.venv\Scripts\python.exe -X utf8 platform_main.py import crawler_packages\wikipedia
.\.venv\Scripts\python.exe -X utf8 platform_main.py import crawler_packages\google_news_rss
```

创建和运行一个监控任务：

```powershell
.\.venv\Scripts\python.exe -X utf8 platform_main.py create-monitor "人工智能监控" "人工智能" --packages baidu_baike wikipedia google_news_rss
.\.venv\Scripts\python.exe -X utf8 platform_main.py run 1
.\.venv\Scripts\python.exe -X utf8 platform_main.py worker --once
```

每个 `worker --once` 处理一个包；运行三次可处理示例任务的三个包。长期运行使用 `启动新平台.bat`，它启动 API、Worker 和 Scheduler。

主要 API：

- `GET /api/v1/packages`
- `POST /api/v1/packages/import`
- `POST /api/v1/monitors`
- `POST /api/v1/monitors/{id}/runs`
- `GET /api/v1/runs/{id}`
- `GET /api/v1/packages/{key}/records`
- `GET /api/v1/monitors/{id}/records`

完整协议与数据库规则见 `crawler-platform-technical-spec-v1.md`。工具包样例位于 `crawler_packages`，机器协议位于 `protocol/v1`。
