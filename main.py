"""Command line entry point."""
from __future__ import annotations

import argparse

from collector.engine import collect_query
from collector.modules.discovery import discover_modules
from collector.server import start_server
from collector.sources.discovery import discover_plugins
from collector.storage import MySQLStore


def main() -> None:
    parser = argparse.ArgumentParser(description="可插拔情报采集器")
    parser.add_argument("query", nargs="?", help="要采集的装备或主题")
    parser.add_argument("--panel", action="store_true", help="启动管理面板")
    parser.add_argument("--init-db", action="store_true", help="初始化数据库后退出")
    parser.add_argument("--module", default="news", help="采集模块，默认为 news")
    parser.add_argument(
        "--mode", choices=("search", "sync"), default="search",
        help="采集模式：按关键词搜索或增量同步",
    )
    args = parser.parse_args()

    if args.panel:
        start_server()
        return

    store = MySQLStore()
    module_discovery = discover_modules()
    discovery = discover_plugins()
    store.initialize()
    store.sync_catalog(module_discovery.modules, discovery.plugins)
    if args.init_db:
        print(
            f"数据库初始化完成，已注册 {len(module_discovery.modules)} 个模块、"
            f"{len(discovery.plugins)} 个来源"
        )
        return
    if args.mode == "search" and not args.query:
        parser.error("请提供采集主题，或使用 --panel")
    if args.module not in module_discovery.modules:
        parser.error(f"未知模块：{args.module}")
    if args.mode not in module_discovery.modules[args.module].supported_modes:
        parser.error(f"模块 {args.module} 不支持 {args.mode} 模式")
    result = collect_query(
        (args.query or "").strip(), discovery.plugins, store,
        module_name=args.module, mode=args.mode,
    )
    print(result)


if __name__ == "__main__":
    main()
