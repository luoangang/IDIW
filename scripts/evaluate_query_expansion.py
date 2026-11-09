"""Compare reviewed DeepSeek terms against the same live RSS feed snapshot."""

from __future__ import annotations

import json
import site
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from crawler_platform.config import SETTINGS
from crawler_platform.query_planner import enabled_aliases, generate_terms
from crawler_platform.storage import PlatformStore


environment = SETTINGS.environments_dir / "rss_multi_feed" / "1.0.0"
site_packages = (environment / "Lib" / "site-packages" if sys.platform == "win32"
                 else environment / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages")
if not site_packages.is_dir():
    raise RuntimeError("installed RSS package environment is unavailable")
site.addsitedir(str(site_packages))

from crawler_packages.news.rss_multi_feed.crawler import collect, fetch_feed


APPROVED = {
    7: ("具身人工智能", "具身AI", "具身智能体", "embodied AI",
        "embodied intelligence", "embodied artificial intelligence", "embodied agents"),
    8: ("军用智能体", "军事人工智能体", "军事AI智能体", "军用自主智能体",
        "military AI agent", "military intelligent agent", "military autonomous agent",
        "military agentic AI", "defense AI agent"),
}


def main() -> None:
    store = PlatformStore(SETTINGS)
    monitors = {row["id"]: row for row in store.list_monitors() if row["id"] in APPROVED}
    if set(monitors) != set(APPROVED):
        raise RuntimeError("the two evaluation monitors were not found")
    configs = {}
    for monitor_id in APPROVED:
        rows = [row for row in store.monitor_package_settings(monitor_id)
                if row["package_key"] == "rss_multi_feed" and row["enabled"]]
        if len(rows) != 1:
            raise RuntimeError(f"RSS is not enabled for monitor {monitor_id}")
        configs[monitor_id] = rows[0]
    urls = list(dict.fromkeys(url for row in configs.values() for url in row["config"]["feed_urls"]))
    snapshots = {}
    errors = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_feed, url, 20, 5242880): url for url in urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                snapshots[url] = future.result()
            except Exception as exc:
                errors[url] = f"{type(exc).__name__}: {str(exc)[:200]}"
    print(json.dumps({"feeds_requested": len(urls), "feeds_loaded": len(snapshots),
                      "feed_failures": errors}, ensure_ascii=False), flush=True)
    if not snapshots:
        raise RuntimeError("no feeds were accessible; cannot compare search terms")

    def cached_fetch(url, *_args):
        return snapshots[url]

    for monitor_id, monitor in monitors.items():
        config = dict(configs[monitor_id]["config"])
        config["feed_urls"] = [url for url in config["feed_urls"] if url in snapshots]
        base = {"query": monitor["query_text"], "aliases": monitor["aliases"],
                "limit": configs[monitor_id]["item_limit"], "parameters": config,
                "time_range": {"from": None, "to": None}}
        baseline, _ = collect(base, cached_fetch)
        generated = generate_terms(monitor["query_text"])
        aliases = enabled_aliases(generated["terms"], monitor["query_text"],
                                  monitor["aliases"], APPROVED[monitor_id])
        expanded, _ = collect({**base, "aliases": aliases}, cached_fetch)
        baseline_urls = {item["url"] for item in baseline}
        added = [item for item in expanded if item["url"] not in baseline_urls]
        print(json.dumps({
            "monitor_id": monitor_id,
            "query": monitor["query_text"],
            "model": generated["model"],
            "usage": generated["usage"],
            "candidate_terms": generated["terms"],
            "approved_aliases": aliases,
            "baseline_count": len(baseline),
            "expanded_count": len(expanded),
            "new_count": len(added),
            "new_items": [{"title": item["title"], "url": item["url"],
                           "language": item["language"]} for item in added[:25]],
        }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
