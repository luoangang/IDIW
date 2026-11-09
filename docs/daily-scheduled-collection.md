# 每日定时采集部署

任务的执行时间按北京时间（Asia/Shanghai，UTC+08:00）设置。平台将下一次执行时刻存为 UTC，MySQL 会话也固定为 UTC；服务器操作系统使用其他时区不会改变执行时刻。网页“新建任务”默认每天 09:00，已有任务可在“监控任务 > 执行计划”改为每天、选择时刻、启用或暂停。

命令行也可创建每日任务，例如 `python platform_main.py create-monitor "AI 监控" "人工智能" --packages rss_multi_feed --daily-at 09:00`。现有手动任务通过网页或 `PATCH /api/v1/monitors/{id}/schedule` 设置，JSON 内容为 `{"schedule_type":"daily","schedule_time":"09:00","enabled":true}`。

后台需要同时运行三个长期进程：API、Scheduler、Worker。Windows 的 `启动平台.bat` 已启动这三个进程；仅运行 `platform_main.py serve` 只会提供网页，不会触发自动采集。

Linux 服务器可用 systemd 分别守护三个进程。下面的路径和用户按实际部署位置替换；三个服务均使用同一个项目目录、虚拟环境和 `.env`。MySQL 应先启动，首次部署先执行 `python platform_main.py init-db`。API 使用 WSGI 服务器，例如先在该虚拟环境安装 `gunicorn`；不要将 Flask 内置开发服务器直接暴露为生产服务。

```ini
# /etc/systemd/system/crawler-api.service
[Unit]
Description=Crawler platform API
After=network-online.target mysql.service
[Service]
Type=simple
User=crawler
WorkingDirectory=/srv/crawler-platform
ExecStart=/srv/crawler-platform/.venv/bin/gunicorn -w 2 -b 127.0.0.1:8090 platform_wsgi:app
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
```

Worker 和 Scheduler 各建一个同样的 service 文件，分别将 `Description` 与 `ExecStart` 改为 `Crawler platform Worker` / `/srv/crawler-platform/.venv/bin/python platform_main.py worker`、`Crawler platform Scheduler` / `/srv/crawler-platform/.venv/bin/python platform_main.py scheduler`。启动后用 `systemctl status crawler-api crawler-worker crawler-scheduler` 和各自的 `journalctl -u ...` 查看状态及日志。Worker 和 Scheduler 须独立常驻。

调度器每 30 秒检查到点任务；即使同时运行两个调度器，同一个计划时刻也只会创建一条任务。停机时已到点的任务会在服务恢复后补执行一次，然后安排下一个未来时刻，不逐日补建大量历史任务。若任务还在执行，到点计划会等待其结束后入队。Worker 每 30 秒续租；Worker 中断、插件超时或插件明确报告可重试错误时，同一页最多尝试三次，依次延迟 30、60 秒；协议错误不会自动重试。失败历史保留在运行记录里。插件返回 `has_more=true` 时会在同一轮自动继续采集，最多 100 页；成功结束后游标归零，次日重新从第一页读取，数据库按来源身份去重。对于只保留短列表的 RSS，服务停机超过源站保留期时仍可能漏掉条目，平台无法从已经消失的列表中恢复它们。

监控运行可从网页“运行记录”查看，或调用 `GET /api/v1/runs/{id}`。采集包进程日志在 `crawler_platform_runtime/runs/<execution_id>/process.log`。
