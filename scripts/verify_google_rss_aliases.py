"""Live Google RSS alias verification without creating a monitor or storing articles."""

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "crawler_packages" / "news" / "google_news_rss"
spec = importlib.util.spec_from_file_location("google_rss_alias_check", PACKAGE / "crawler.py")
crawler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crawler)


def main():
    observations = []

    def fetch(term, config, timeout):
        observation = {"query": term}
        observations.append(observation)
        try:
            root = crawler.fetch_feed(term, config, timeout)
            rows = crawler.parse_items(root, config)
            observation.update(count=len(rows), ids=[row["external_id"] for row in rows], titles=[row["title"] for row in rows[:3]])
            return root
        except Exception as error:
            observation["error"] = f"{type(error).__name__}: {error}"
            raise

    request = {"query": "科学智能", "aliases": ["AI for science", "AI4S"], "limit": 12,
               "parameters": {"language": "zh-CN", "country": "CN"},
               "deadline_at": (datetime.now(timezone.utc) + timedelta(seconds=80)).isoformat()}
    result = crawler.collect(request, fetch)
    primary_ids = set(observations[0].get("ids", []))
    unique_alias = set().union(*(set(row.get("ids", [])) for row in observations[1:])) - primary_ids
    output_ids = {row["external_id"] for row in result["items"]}
    report = {
        "tested_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "package_version": json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))["package_version"],
        "request": request, "queries": observations, "status": result["status"],
        "merged_count": len(result["items"]), "limit_respected": len(result["items"]) <= request["limit"],
        "unique_alias_candidates": len(unique_alias), "returned_alias_only_count": len(output_ids & unique_alias),
        "warnings": result["warnings"], "error": result["error"],
        "sample_items": result["items"], "database_written": False,
    }
    path = ROOT / "reports" / ("google-news-rss-aliases-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("package_version", "status", "merged_count", "limit_respected",
                                                  "unique_alias_candidates", "returned_alias_only_count", "error")}, ensure_ascii=False))
    print("queries", [(row["query"], row.get("count"), row.get("error")) for row in observations])
    print("report", path)


if __name__ == "__main__":
    main()
