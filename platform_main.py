from __future__ import annotations

import argparse
import logging
import re
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from crawler_platform.api import create_app
from crawler_platform.config import SETTINGS
from crawler_platform.executor import Scheduler, Worker
from crawler_platform.importer import PackageImporter
from crawler_platform.storage import PlatformStore
from crawler_platform.categories import discover_packages
from crawler_platform.process_lock import AlreadyRunning, ProcessLock


def main() -> None:
    parser = argparse.ArgumentParser(description="爬虫工具包管理与执行平台")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="初始化全新平台数据库")
    sub.add_parser("migrate-package-layout", help="迁移现有安装路径和分类，保留旧文件供回退")
    install = sub.add_parser("import", help="导入工具包目录")
    install.add_argument("path")
    install.add_argument("--all", action="store_true", help="导入分类目录下的全部工具包")
    create = sub.add_parser("create-monitor", help="创建监控任务")
    create.add_argument("name")
    create.add_argument("query")
    create.add_argument("--packages", nargs="+")
    create.add_argument("--categories", nargs="*", default=[])
    create.add_argument("--daily-at", metavar="HH:MM", help="每天北京时间执行时刻")
    enqueue = sub.add_parser("run", help="将监控任务加入执行队列")
    enqueue.add_argument("monitor_id", type=int)
    worker = sub.add_parser("worker", help="运行 Worker")
    worker.add_argument("--once", action="store_true")
    worker.add_argument("--instance", default="default", help="Worker 实例名；同名实例不能重复启动")
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
    elif args.command == "migrate-package-layout":
        from crawler_platform.package_layout import migrate_package_layout
        print(migrate_package_layout(SETTINGS, store))
    elif args.command == "import":
        paths = discover_packages(Path(args.path)) if args.all else [Path(args.path)]
        if not paths:
            parser.error("no packages found")
        importer = PackageImporter(SETTINGS, store)
        for path in paths:
            print(importer.install(path))
    elif args.command == "create-monitor":
        print({"id": store.create_monitor(
            args.name, args.query, [], args.categories, args.packages,
            schedule_type="daily" if args.daily_at else "manual",
            schedule_time=args.daily_at,
        )})
    elif args.command == "run":
        print({"run_id": store.enqueue_monitor(args.monitor_id)})
    elif args.command == "worker":
        instance = Worker(SETTINGS, store)
        if args.once:
            print({"processed": instance.run_once()})
        else:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", args.instance):
                parser.error("worker instance must contain 1-40 letters, digits, underscores or hyphens")
            run_service(f"worker-{args.instance}", instance.run_forever)
    elif args.command == "scheduler":
        run_service("scheduler", Scheduler(SETTINGS, store).run_forever)
    elif args.command == "serve":
        run_service("serve", lambda: create_app(SETTINGS, store).run(host=SETTINGS.host, port=SETTINGS.port, threaded=True))
    elif args.command == "list":
        if args.kind == "packages":
            print(store.list_packages())
        elif args.kind == "monitors":
            print(store.list_monitors())
        elif args.id is None:
            parser.error("list run requires id")
        else:
            print(store.run(args.id))


def run_service(role, target):
    try:
        with ProcessLock(SETTINGS.runtime_dir / "locks" / f"{role}.lock"):
            log_dir = SETTINGS.runtime_dir / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(log_dir / f"{role}.log", maxBytes=5_000_000,
                                          backupCount=4, encoding="utf-8")
            formatter = logging.Formatter("%(asctime)s+08:00 %(levelname)s %(name)s %(message)s", "%Y-%m-%dT%H:%M:%S")
            formatter.converter = lambda timestamp: time.gmtime(timestamp + 8 * 3600)
            handler.setFormatter(formatter)
            logger = logging.getLogger()
            previous_level = logger.level
            logger.setLevel(min(previous_level, logging.INFO))
            logger.addHandler(handler)
            try:
                logging.getLogger(__name__).info("Starting service %s", role)
                target()
            except Exception:
                logging.getLogger(__name__).exception("Service %s stopped unexpectedly", role)
                raise
            finally:
                logging.getLogger(__name__).info("Service %s stopped", role)
                logger.removeHandler(handler)
                handler.close()
                logger.setLevel(previous_level)
    except AlreadyRunning as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
