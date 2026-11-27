from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS_ORDER = {"ok_current_search": 0, "ok_current": 1, "blocked": 2, "fail": 3}
PUNCT = re.compile(r"[\s《》〈〉()（）\[\]【】·•*※\-—–_/\\.,，。:：;；!?！？'\"“”‘’]+")


def norm(value):
    return PUNCT.sub("", unicodedata.normalize("NFKC", str(value or "")).lower())


def platform_key(platform):
    text = str(platform or "").lower()
    if "magetech" in text or "magtech" in text or "玛格泰克" in text:
        return "magetech"
    if "cbpt" in text or "cnki" in text or "腾云" in text:
        return "cnki_cbpt"
    if "qinyun" in text or "勤云" in text:
        return "qinyun"
    if "rhzh" in text or "rhhz" in text or "仁和" in text:
        return "rhzh"
    if "founder" in text or "方正" in text:
        return "founder"
    if "paperonce" in text:
        return "paperonce"
    if "vsb" in text:
        return "vsb"
    if "hep" in text or "高教社" in text:
        return "hep"
    if "ajcass" in text:
        return "custom"
    return "custom"


PACKAGE_PLAN = {
    "magetech": "magetech_journals",
    "cnki_cbpt": "cnki_cbpt",
    "qinyun": "qinyun_journals",
    "rhzh": "rhzh_journals",
    "founder": "founder_journals",
    "paperonce": "paperonce_journals",
    "vsb": "vsb_journals",
    "hep": "hep_mirror/custom_toc 待确认",
    "custom": "custom_toc_journals（需适配确认）",
}


def load_results(input_dir: Path):
    results = []
    for path in sorted(input_dir.glob("batch-*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"skip {path.name}: {exc}")
            continue
        if isinstance(data, dict):
            data = data.get("results") or data.get("items") or []
        if not isinstance(data, list):
            print(f"skip {path.name}: not a list")
            continue
        for row in data:
            if isinstance(row, dict) and row.get("journal_name"):
                row["_batch"] = path.stem
                results.append(row)
    return results


def dedupe(results):
    chosen = {}
    for row in results:
        key = norm(row.get("journal_name"))
        old = chosen.get(key)
        if old is None or STATUS_ORDER.get(row.get("status"), 9) < STATUS_ORDER.get(old.get("status"), 9):
            chosen[key] = row
    return list(chosen.values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default=str(ROOT / ".local" / "core" / "probe-results"))
    parser.add_argument("--output-dir", default=str(ROOT / "journal_catalog" / "core"))
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--prefix", default="core-probe-results")
    args = parser.parse_args()

    rows = dedupe(load_results(Path(args.input_dir)))
    if not rows:
        print("No probe result JSON found")
        return 0

    for row in rows:
        row["platform_key"] = platform_key(row.get("platform"))
        row["package_plan"] = PACKAGE_PLAN.get(row["platform_key"], "待确认")
        row["search_supported"] = "yes" if row.get("search_supported") else "no"
    rows.sort(key=lambda row: (STATUS_ORDER.get(row.get("status"), 9), row["platform_key"], row["journal_name"]))

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{args.prefix}-{args.date}.csv"
    fields = ["journal_name", "core_levels", "categories", "status", "platform", "platform_key",
              "package_plan", "official_url", "current_url", "search_url", "search_supported",
              "current_items", "first_title", "block_reason", "note", "probe_urls", "_batch"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = {key: row.get(key, "") for key in fields}
            out["probe_urls"] = ";".join(row.get("probe_urls") or [])
            writer.writerow(out)

    status_counts = Counter(row.get("status") for row in rows)
    platform_counts = Counter((row["platform_key"], row.get("status")) for row in rows)
    category_counts = Counter()
    for row in rows:
        if row.get("status") in ("ok_current", "ok_current_search"):
            for category in (row.get("categories") or "未分类").split(";"):
                category_counts[category] += 1

    summary = {
        "date": args.date,
        "total": len(rows),
        "status": dict(status_counts),
        "by_platform": {platform: {status: count for (p, status), count in platform_counts.items() if p == platform}
                        for platform in sorted({p for p, _ in platform_counts})},
        "ok_by_category": dict(category_counts.most_common()),
        "csv": str(csv_path),
    }
    json_path = output_dir / f"{args.prefix}-{args.date}.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# 国内核心刊官网探测结果（{args.date}）",
        "",
        f"- 总记录：{len(rows)}",
        "- 状态：" + "，".join(f"{key} {value}" for key, value in status_counts.most_common()),
        "",
        "## 按平台/状态",
        "",
        "| 平台 | 可搜索 | 仅当期 | blocked | fail |",
        "|---|---:|---:|---:|---:|",
    ]
    for platform in sorted({p for p, _ in platform_counts}):
        lines.append(f"| {platform} | {platform_counts.get((platform, 'ok_current_search'), 0)} | "
                     f"{platform_counts.get((platform, 'ok_current'), 0)} | "
                     f"{platform_counts.get((platform, 'blocked'), 0)} | "
                     f"{platform_counts.get((platform, 'fail'), 0)} |")
    lines += ["", "## OK 期刊按学科（前 20）", "", "| 学科 | 数量 |", "|---|---:|"]
    for category, count in category_counts.most_common(20):
        lines.append(f"| {category} | {count} |")
    lines += ["", f"逐刊结果：[{csv_path.name}]({csv_path.name})"]
    md_path = output_dir / f"{args.prefix}-{args.date}.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n".join(lines))
    print(f"csv: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())