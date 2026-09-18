"""Collection orchestration independent from individual source implementations."""
from __future__ import annotations

from typing import Callable

from collector.sources.base import CollectionRequest, SourcePlugin
from collector.storage import MySQLStore


LogCallback = Callable[[str], None]


def collect_query(query: str, plugins: dict[str, SourcePlugin], store: MySQLStore,
                  log: LogCallback = print, module_name: str = "news",
                  mode: str = "search", options: dict | None = None) -> dict:
    settings = store.list_settings()
    module_plugins = {
        name: plugin for name, plugin in plugins.items()
        if plugin.module == module_name and mode in plugin.supported_modes
    }
    if not module_plugins:
        raise ValueError(f"模块 {module_name} 没有支持 {mode} 模式的采集源")
    run_id = store.create_run(query, module_name, mode=mode, options=options or {})
    total_fetched = 0
    total_inserted = 0
    total_updated = 0
    failures: list[str] = []
    source_stats: dict[str, dict] = {}
    log(f"开始采集：{query or '增量同步'}，模块 {module_name}，模式 {mode}，任务 #{run_id}")

    for plugin in module_plugins.values():
        setting = settings.get(plugin.name, {})
        if not setting.get("enabled", True):
            log(f"跳过 {plugin.label}：已停用")
            continue
        limit = max(1, min(int(setting.get("item_limit", plugin.default_limit)), 500))
        config = setting.get("config", {})
        store.start_source(run_id, plugin.name, plugin.module)
        log(f"正在采集 {plugin.label}，上限 {limit}")
        try:
            request = CollectionRequest(
                module=module_name,
                query=query,
                limit=limit,
                config=config,
                mode=mode,
                options=options or {},
            )
            items = plugin.collect(request)
            write_stats = store.write_items(plugin, run_id, query, items)
            fetched = len(items)
            total_fetched += fetched
            total_inserted += write_stats["inserted"]
            total_updated += write_stats["updated"]
            source_stats[plugin.name] = {"fetched": fetched, **write_stats}
            store.finish_source(run_id, plugin.name, "completed", fetched, **write_stats)
            log(f"{plugin.label} 完成：获取 {fetched}，新增 {write_stats['inserted']}，更新 {write_stats['updated']}")
        except Exception as exc:
            message = str(exc)[:2000]
            failures.append(f"{plugin.label}: {message}")
            source_stats[plugin.name] = {"fetched": 0, "inserted": 0, "updated": 0, "error": message}
            store.finish_source(run_id, plugin.name, "failed", error=message)
            log(f"{plugin.label} 失败：{message}")

    status = "partial" if failures and total_fetched else "failed" if failures else "completed"
    store.finish_run(
        run_id, status, total_fetched, total_inserted,
        "\n".join(failures), updated=total_updated,
    )
    log(
        f"任务 #{run_id} 结束：获取 {total_fetched}，新增 {total_inserted}，"
        f"更新 {total_updated}，状态 {status}"
    )
    return {
        "run_id": run_id,
        "module": module_name,
        "status": status,
        "total_fetched": total_fetched,
        "total_inserted": total_inserted,
        "total_updated": total_updated,
        "sources": source_stats,
    }
