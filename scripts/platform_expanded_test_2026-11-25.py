from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler_platform.config import SETTINGS
from crawler_platform.storage import PlatformStore

ACADEMIC = ROOT / "crawler_packages" / "academic"
STATE = ROOT / ".local" / "platform-expanded-test-2026-11-25.json"
LARGE = ["cnki_cbpt", "custom_toc_journals", "magetech_journals", "qinyun_journals",
         "rhzh_journals", "founder_journals", "paperonce_journals"]
SMALL = ["oa_rss_journals", "vsb_journals", "hep_mirror_journals", "sancai_journals",
         "sciengine_journals"]
CURATED = {
    "cnki_cbpt": ["卫生研究", "征信", "林产工业", "自然辩证法研究", "临床骨科杂志"],
    "custom_toc_journals": ["粉煤灰综合利用", "机电工程", "中国地方志", "临床与实验病理学杂志",
                            "商业经济研究", "载人航天", "北京大学教育评论", "华东理工大学学报（社会科学版）"],
    "magetech_journals": ["中华临床医师杂志电子版", "耐火材料", "农学学报",
                          "中华介入放射学电子杂志", "中华关节外科杂志（电子版）"],
    "qinyun_journals": ["兵工自动化", "医用生物力学", "军事护理", "农业机械学报",
                        "南京信息工程大学学报自然科学版"],
    "rhzh_journals": ["临床心血管病杂志", "临床急诊杂志", "临床泌尿外科杂志",
                      "机械工程材料", "现代应用物理", "复合材料学报"],
    "founder_journals": ["四川大学学报. 自然科学版", "新疆石油地质", "测试技术学报",
                         "电焊机", "饲料研究"],
    "paperonce_journals": ["断块油气田", "现代检验医学杂志", "邮电设计技术"],
}
PAGINATION = {
    "cnki_cbpt": ["卫生研究", "临床骨科杂志"],
    "custom_toc_journals": ["粉煤灰综合利用", "机电工程"],
}


def load_journals(package_key: str) -> list[dict]:
    return json.loads((ACADEMIC / package_key / "journals.json").read_text(encoding="utf-8"))


def resolve(journals: list[dict], name: str) -> str:
    exact = [row["journal_key"] for row in journals if row.get("name") == name]
    if len(exact) == 1:
        return exact[0]
    hits = [row["journal_key"] for row in journals if name in (row.get("name") or "")]
    if len(hits) >= 1:
        return hits[0]
    raise ValueError(f"journal not found: {name}")


def select(package_key: str, target: int) -> list[tuple[str, str]]:
    journals = load_journals(package_key)
    chosen: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name in CURATED.get(package_key, []):
        key = resolve(journals, name)
        if key not in seen:
            seen.add(key)
            chosen.append((key, dict((row["journal_key"], row.get("name")) for row in journals)[key]))
    if target >= len(journals):
        for row in journals:
            key = row["journal_key"]
            if key not in seen:
                seen.add(key)
                chosen.append((key, row.get("name")))
        return chosen
    need = max(0, target - len(chosen))
    if need:
        pool = [row for row in journals if row["journal_key"] not in seen]
        step = len(pool) / need
        for index in range(need):
            row = pool[min(len(pool) - 1, int(index * step))]
            if row["journal_key"] not in seen:
                seen.add(row["journal_key"])
                chosen.append((row["journal_key"], row.get("name")))
    return chosen[:target]


def package_config(package_key: str, keys: list[str], *, per_journal: int,
                   enrich: bool, enrich_limit: int) -> tuple[dict, int]:
    manifest = json.loads((ACADEMIC / package_key / "manifest.json").read_text(encoding="utf-8"))
    properties = manifest["parameters_schema"]["properties"]
    config: dict = {"journal_keys": keys, "collect_mode": "latest_issue"}
    if "per_journal_limit" in properties:
        config["per_journal_limit"] = per_journal
    if "timeout_seconds" in properties:
        config["timeout_seconds"] = 15
    if "enrich_abstract" in properties:
        config["enrich_abstract"] = enrich
    if "abstract_enrich_limit" in properties:
        config["abstract_enrich_limit"] = enrich_limit
    if "request_delay_ms" in properties:
        config["request_delay_ms"] = 0
    if "follow_latest" in properties:
        config["follow_latest"] = True
    item_limit = min(10000, max(1, len(keys) * max(2, per_journal)))
    return {"package_key": package_key, "enabled": True, "item_limit": item_limit, "config": config}, item_limit


def main() -> None:
    store = PlatformStore(SETTINGS)
    existing = {row["name"] for row in store.list_monitors("all")}
    for name in ("翻页验收-2026-11-25", "扩大抽样-2026-11-25"):
        if name in existing:
            raise SystemExit(f"monitor already exists: {name}")

    pagination_settings = []
    for package_key, names in PAGINATION.items():
        journals = load_journals(package_key)
        keys = [resolve(journals, name) for name in names]
        setting, limit = package_config(package_key, keys, per_journal=50, enrich=False, enrich_limit=0)
        pagination_settings.append(setting)
        print(f"PAGINATION {package_key:24s} {len(keys)} 本  item_limit={limit}")
    pagination_id = store.create_monitor(
        name="翻页验收-2026-11-25", query="最新一期", aliases=[], categories=[],
        package_keys=[row["package_key"] for row in pagination_settings],
        schedule_type="manual", package_settings=pagination_settings,
    )
    pagination_run = store.enqueue_monitor(pagination_id)

    expanded_settings = []
    samples: dict[str, list[list[str]]] = {}
    for package_key in LARGE + SMALL:
        target = 20 if package_key in LARGE else len(load_journals(package_key))
        rows = select(package_key, target)
        keys = [key for key, _ in rows]
        samples[package_key] = [[key, name] for key, name in rows]
        setting, limit = package_config(package_key, keys, per_journal=2, enrich=True, enrich_limit=1)
        expanded_settings.append(setting)
        print(f"EXPANDED   {package_key:24s} {len(keys):3d} 本  item_limit={limit}")
    expanded_id = store.create_monitor(
        name="扩大抽样-2026-11-25", query="最新一期", aliases=[], categories=[],
        package_keys=[row["package_key"] for row in expanded_settings],
        schedule_type="manual", package_settings=expanded_settings,
    )

    state = {
        "pagination": {"monitor_id": pagination_id, "run_id": pagination_run},
        "expanded": {"monitor_id": expanded_id, "run_id": None, "samples": samples},
    }
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print("pagination monitor", pagination_id, "run", pagination_run)
    print("expanded monitor", expanded_id, "created (not enqueued)")
    print("state", STATE)


if __name__ == "__main__":
    main()
