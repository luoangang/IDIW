"""Read-only deployment checks plus assistant previews; never create or execute tasks."""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler_platform.config import SETTINGS


def main():
    base = f"http://127.0.0.1:{SETTINGS.port}"
    headers = {"Authorization": f"Bearer {SETTINGS.token}"} if SETTINGS.token else {}

    def request(path, body=None, as_json=True):
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        req = Request(base + path, data=payload, headers={**headers, "Content-Type": "application/json"})
        with urlopen(req, timeout=20) as response:
            raw = response.read(8_000_001)
            assert response.status == 200 and len(raw) <= 8_000_000, path
        return json.loads(raw) if as_json else raw

    checks = []
    for path in ("/health/live", "/health/ready"):
        request(path)
        checks.append(path)
    for path in ("/assistant", "/system", "/sources", "/monitors", "/runs", "/data", "/reports",
                 "/assets/task-assistant.js", "/assets/assistant.css", "/assets/vendor/lucide/icons.js",
                 "/assets/vendor/lucide/createElement.js", "/assets/vendor/lucide/defaultAttributes.js",
                 "/assets/vendor/lucide/icons/bot.js"):
        assert request(path, as_json=False), path
        checks.append(path)
    snapshot = request("/api/v1/system/status")
    assert snapshot["database"]["state"] == "ready"
    for origin in ("https://untrusted.example", "null"):
        req = Request(base + "/api/v1/assistant/preview", data=b"{}", headers={
            **headers, "Content-Type": "application/json", "Origin": origin})
        try:
            with urlopen(req, timeout=20):
                raise AssertionError("cross-origin management request was accepted")
        except HTTPError as exc:
            assert exc.code == 403 and json.loads(exc.read())["error"] == "cross_origin_request"
    checks.append("cross-origin management writes rejected")
    sources = request("/api/v1/assistant/catalog")["sources"]
    news = next(source for source in sources if source["package_key"] == "google_news_rss")
    draft = {"name": "只读部署验收-" + uuid.uuid4().hex[:12], "query": "人工智能", "aliases": ["artificial intelligence"],
             "schedule_type": "manual", "timezone": "Asia/Shanghai", "journal_scope": "selected",
             "packages": [{"package_key": news["package_key"], "item_limit": 10, "config": {}}]}
    preview = request("/api/v1/assistant/preview", {"draft": draft})
    assert preview["ready"], preview["errors"]
    journals = [source for source in sources if source["supported"] and source["category"] == "academic"
                and "zh" in source["profile"].get("languages", [])
                and source["parameters_schema"].get("properties", {}).get("journal_keys")]
    scope = None
    if journals:
        draft["journal_scope"] = "all_chinese"
        draft["packages"] = [{"package_key": source["package_key"], "item_limit": 100, "config": {}} for source in journals]
        scope = request("/api/v1/assistant/preview", {"draft": draft})
        assert len(scope["coverage"]) == len(journals), "journal coverage is missing installed catalogs"
        if any(row["selected"] < row["total"] for row in scope["coverage"]):
            assert not scope["ready"] and "confirmation_token" not in scope
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d-%H%M%S")
    report = {"checked_at_beijing": stamp, "status": "passed", "checks": checks,
              "processes": [{"role": row["role"], "state": row["state"]} for row in snapshot["processes"]],
              "collection": {key: snapshot["collection"][key] for key in ("queued", "running", "overdue_monitors")},
              "valid_draft_preview": preview["ready"], "all_journal_scope_ready": scope["ready"] if scope else None,
              "coverage": scope["coverage"] if scope else [], "created_monitors": 0, "model_calls": 0}
    output = ROOT / "reports" / f"platform-smoke-{stamp}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(output)


if __name__ == "__main__":
    main()
