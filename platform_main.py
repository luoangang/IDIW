from __future__ import annotations

import argparse
from pathlib import Path

from crawler_platform.api import create_app
from crawler_platform.config import SETTINGS
from crawler_platform.executor import Scheduler, Worker
from crawler_platform.importer import PackageImporter
from crawler_platform.storage import PlatformStore


def main() -> None:
    parser = argparse.ArgumentParser(description="爬虫工具包管理与执行平台")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="初始化全新平台数据库")
    install = sub.add_parser("import", help="导入工具包目录")
    install.add_argument("path")
    create = sub.add_parser("create-monitor", help="创建监控任务")
    create.add_argument("name")
    create.add_argument("query")
    create.add_argument("--packages", nargs="+")
    create.add_argument("--categories", nargs="*", default=[])
    enqueue = sub.add_parser("run", help="将监控任务加入执行队列")
    enqueue.add_argument("monitor_id", type=int)
    worker = sub.add_parser("worker", help="运行 Worker")
    worker.add_argument("--once", action="store_true")
    sub.add_parser("scheduler", help="运行定时调度器")
    sub.add_parser("serve", help="启动管理 API")
    list_parser = sub.add_parser("list", help="查看包、任务或运行")
    list_parser.add_argument("kind", choices=("packages", "monitors", "run"))
    list_parser.add_argument("id", nargs="?", type=int)
    args = parser.parse_args()

    store = PlatformStore(SETTINGS)
    if args.command == "init-db":
        store.initialize()
        print(f"数据库 {SETTINGS.mysql_database} 初始化完成")
    elif args.command == "import":
        print(PackageImporter(SETTINGS, store).install(Path(args.path)))
    elif args.command == "create-monitor":
        print({"id": store.create_monitor(args.name, args.query, [], args.categories, args.packages)})
    elif args.command == "run":
        print({"run_id": store.enqueue_monitor(args.monitor_id)})
    elif args.command == "worker":
        instance = Worker(SETTINGS, store)
        if args.once:
            print({"processed": instance.run_once()})
        else:
            instance.run_forever()
    elif args.command == "scheduler":
        Scheduler(SETTINGS, store).run_forever()
    elif args.command == "serve":
        create_app(SETTINGS, store).run(host=SETTINGS.host, port=SETTINGS.port, threaded=True)
    elif args.command == "list":
        if args.kind == "packages":
            print(store.list_packages())
        elif args.kind == "monitors":
            print(store.list_monitors())
        elif args.id is None:
            parser.error("list run requires id")
        else:
            print(store.run(args.id))


if __name__ == "__main__":
    main()
