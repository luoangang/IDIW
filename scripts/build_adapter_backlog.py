from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "journal_catalog" / "core"
LOCAL = ROOT / ".local" / "core"

PROBE_DIRS = [path for path in sorted(LOCAL.glob("probe-results*")) if path.is_dir()]
PROBE_FILES = [LOCAL / "probe-results-review.json"]
VERIFY_FILES = sorted(LOCAL.glob("probe-verify-*.csv")) + [LOCAL / "review-verify-2026-11-22.csv"]
SUPPORTED_PARSERS = {"cnki_cbpt", "magetech", "custom_toc", "qinyun", "rhzh"}
OK_STATUSES = {"ok_current", "ok_current_search"}
STATUS_RANK = {"ok_current_search": 0, "ok_current": 1, "blocked": 2, "fail": 3}

PUNCT = re.compile(r"[\s《》〈〉()（）\[\]【】·•*※\-—–_/\\.,，。:：;；!?！？'\"“”‘’]+")
TRANSIENT = re.compile(
    r"502|503|504|429|timeout|timed out|SSL|CERTIFICATE|Proxy|Connection reset|"
    r"URLError|HTTP Error 5\d\d|RemoteDisconnected|IncompleteRead|getaddrinfo|"
    r"Connection refused|Tunnel connection failed|Name or service not known",
    re.I,
)
BLOCKED = re.compile(
    r"403|412|429|WAF|验证码|validate|cloudflare|安全狗|robot|access denied|forbidden|"
    r"拦截|反爬|CAS|登录|login|滑块|安全验证",
    re.I,
)
PDF_ONLY = re.compile(r"PDF|pdf|图片|jpg|jpeg|png|整期|扫描|无篇级|篇级.*PDF|目录.*图", re.I)
SPA = re.compile(
    r"SPA|Vue|React|前端|单页|空壳|壳页|异步|渲染|JavaScript|js\b|动态|接口|JSON|api",
    re.I,
)
NO_SITE = re.compile(
    r"无官网|无独立官网|仅.*代理|仅.*聚合|仅.*中介|仅.*第三方|投稿站|采编|没有官网|无公开|停更|不更新",
    re.I,
)

CLASS_ACTION = {
    "G-已验证需扩包": "已验证 items>0，但当前 apply 只写 5 个包；扩展现有 apply/专用包即可",
    "A-优先适配": "agent 已读到当期，现有 parser 未吃下；custom_toc 加 adapter 或写专用 parser",
    "B-可重试": "网络/代理临时故障，过几天重抓即可，不写代码",
    "C-需SPA适配": "前端渲染/接口不明；有公开 API 或稳定数据接口时再适配，否则暂缓",
    "D-仅PDF/图片": "只有整期 PDF/图片目录，按当前边界跳过",
    "E-登录/验证码/WAF": "需要登录/验证码/WAF，按当前边界跳过",
    "F-无官网/仅代理": "没有独立官网或只有代理/聚合站，跳过",
    "F-其他失败": "探测未找到可用的公开当期目录，跳过",
    "H-未复核": "agent 标记可读但缺少 live verify，补一次复核",
}


def norm(value):
    return PUNCT.sub("", unicodedata.normalize("NFKC", str(value or "")).lower())


def status_of(row):
    return str(row.get("status") or "").strip()


def intval(value):
    try:
        return int(float(str(value or 0)))
    except (TypeError, ValueError):
        return 0


def host_of(url):
    try:
        host = (urlsplit(str(url or "")).hostname or "").lower()
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


MULTI_LABEL_SUFFIXES = {
    "com.cn", "net.cn", "org.cn", "edu.cn", "gov.cn", "ac.cn",
    "com.hk", "org.hk", "edu.hk", "com.tw", "org.tw", "edu.tw",
    "co.uk", "ac.uk",
}


def site_cluster(host):
    if not host:
        return ""
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in MULTI_LABEL_SUFFIXES:
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def load_json_list(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, dict):
        data = data.get("results") or data.get("items") or []
    return [row for row in data if isinstance(row, dict) and row.get("journal_name")]


def add_attempt(store, row, source):
    name = str(row.get("journal_name") or "").strip()
    if not name:
        return
    item = store.setdefault(norm(name), {"name": name, "attempts": []})
    item["attempts"].append({"row": row, "source": str(source)})


def best_attempt(item):
    attempts = item["attempts"]
    ok = [attempt for attempt in attempts if status_of(attempt["row"]) in OK_STATUSES]
    if ok:
        return max(
            ok,
            key=lambda attempt: (
                intval(attempt["row"].get("current_items")),
                len(str(attempt["row"].get("note") or "")),
                attempt["source"],
            ),
        )
    return max(
        attempts,
        key=lambda attempt: (
            len(str(attempt["row"].get("block_reason") or ""))
            + len(str(attempt["row"].get("note") or "")),
            attempt["source"],
        ),
    )


def load_probes():
    store = {}
    for directory in PROBE_DIRS:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("batch-*.json")):
            for row in load_json_list(path):
                add_attempt(store, row, path)
    for path in PROBE_FILES:
        if path.exists():
            for row in load_json_list(path):
                add_attempt(store, row, path)
    return store


def load_verify():
    store = {}
    for path in VERIFY_FILES:
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                key = norm(row.get("journal_name"))
                if not key:
                    continue
                items = intval(row.get("items"))
                old = store.get(key)
                old_items = intval(old["row"].get("items")) if old else -1
                old_parser = str(old["row"].get("parser") or "") if old else ""
                parser = str(row.get("parser") or "")
                if (
                    old is None
                    or items > old_items
                    or (
                        items == old_items
                        and parser in SUPPORTED_PARSERS
                        and old_parser not in SUPPORTED_PARSERS
                    )
                ):
                    store[key] = {"row": row, "source": str(path)}
    return store


def load_applied():
    names = set()
    for path in sorted(CORE.glob("*applied*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("journal_name"):
                    names.add(norm(row["journal_name"]))
    return names


def load_coverage():
    paths = sorted(CORE.glob("core-coverage-*.csv"))
    if not paths:
        return {}
    with paths[-1].open(encoding="utf-8-sig", newline="") as handle:
        return {norm(row["journal_name"]): row for row in csv.DictReader(handle)}


def classify(probe_row, verify_item):
    agent_status = status_of(probe_row)
    verify_row = verify_item["row"] if verify_item else None
    verify_items = intval(verify_row.get("items")) if verify_row else 0
    verify_parser = str(verify_row.get("parser") or "") if verify_row else ""
    agent_text = " ".join(
        str(probe_row.get(key) or "") for key in ("block_reason", "note", "platform")
    )
    verify_text = " ".join(
        str(verify_row.get(key) or "") for key in ("warnings", "platform")
    ) if verify_row else ""
    text = f"{agent_text} {verify_text}"

    if verify_row and verify_items > 0:
        if verify_parser not in SUPPORTED_PARSERS:
            return "G-已验证需扩包", "P1"
        return "G-已验证需扩包", "P1"

    has_host = bool(host_of(probe_row.get("official_url") or probe_row.get("current_url")))

    if verify_row:
        if TRANSIENT.search(verify_text):
            return "B-可重试", "P3"
        if PDF_ONLY.search(text):
            return "D-仅PDF/图片", "P5"
        if BLOCKED.search(text):
            return "E-登录/验证码/WAF", "P5"
        if SPA.search(text):
            return "C-需SPA适配", "P4"
        if agent_status in OK_STATUSES:
            return "A-优先适配", "P2"
        return "F-其他失败", "P5"

    if agent_status in OK_STATUSES:
        return "H-未复核", "P3"
    if agent_status == "blocked":
        return "E-登录/验证码/WAF", "P5"
    if PDF_ONLY.search(text):
        return "D-仅PDF/图片", "P5"
    if BLOCKED.search(text):
        return "E-登录/验证码/WAF", "P5"
    if NO_SITE.search(text) and not has_host:
        return "F-无官网/仅代理", "P5"
    if SPA.search(text):
        return "C-需SPA适配", "P4"
    if TRANSIENT.search(text) and has_host:
        return "B-可重试", "P3"
    if NO_SITE.search(text):
        return "F-无官网/仅代理", "P5"
    return "F-其他失败", "P5"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

    probes = load_probes()
    verifies = load_verify()
    applied = load_applied()
    coverage = load_coverage()

    covered = set(applied)
    for key, row in coverage.items():
        if row.get("status") == "package_covered":
            covered.add(key)

    rows = []
    for key, item in probes.items():
        if key in covered:
            continue
        best = best_attempt(item)
        probe_row = best["row"]
        verify_item = verifies.get(key)
        verify_row = verify_item["row"] if verify_item else {}
        cov_row = coverage.get(key, {})
        class_name, priority = classify(probe_row, verify_item)
        official = (
            probe_row.get("official_url")
            or verify_row.get("official_url")
            or probe_row.get("current_url")
            or verify_row.get("current_url")
            or ""
        )
        current = (
            probe_row.get("current_url")
            or verify_row.get("current_url")
            or ""
        )
        host = host_of(current or official)
        rows.append({
            "priority": priority,
            "class": class_name,
            "journal_name": probe_row.get("journal_name") or item["name"],
            "core_levels": cov_row.get("core_levels") or probe_row.get("core_levels") or "",
            "categories": cov_row.get("categories") or probe_row.get("categories") or "",
            "language": cov_row.get("language", ""),
            "queue": cov_row.get("priority", ""),
            "platform": probe_row.get("platform") or verify_row.get("platform") or "",
            "host": host,
            "site_cluster": site_cluster(host),
            "host_cluster_easy": 0,
            "site_cluster_easy": 0,
            "agent_status": status_of(probe_row),
            "agent_items": intval(probe_row.get("current_items")),
            "verify_parser": verify_row.get("parser", ""),
            "verify_items": intval(verify_row.get("items")),
            "official_url": official,
            "current_url": current,
            "first_title": verify_row.get("first_title") or probe_row.get("first_title") or "",
            "failure_reason": (
                verify_row.get("warnings")
                or probe_row.get("block_reason")
                or probe_row.get("note")
                or ""
            ),
            "note": probe_row.get("note") or "",
            "suggested_action": CLASS_ACTION.get(class_name, ""),
            "source_probe": best["source"],
            "source_verify": verify_item["source"] if verify_item else "",
            "coverage_status": cov_row.get("status", ""),
        })

    easy_hosts = Counter(row["host"] for row in rows if row["class"].startswith("A-") and row["host"])
    easy_sites = Counter(row["site_cluster"] for row in rows if row["class"].startswith("A-") and row["site_cluster"])
    for row in rows:
        if row["class"].startswith("A-"):
            row["host_cluster_easy"] = easy_hosts.get(row["host"], 0)
            row["site_cluster_easy"] = easy_sites.get(row["site_cluster"], 0)

    priority_order = {"P1": 1, "P2": 2, "P3": 3, "P4": 4, "P5": 5}
    rows.sort(key=lambda row: (
        priority_order.get(row["priority"], 9),
        row["class"],
        -row["site_cluster_easy"],
        row["journal_name"],
    ))

    csv_path = CORE / f"core-adapter-backlog-{args.date}.csv"
    fieldnames = [
        "priority", "class", "journal_name", "core_levels", "categories", "language", "queue",
        "platform", "host", "site_cluster", "host_cluster_easy", "site_cluster_easy",
        "agent_status", "agent_items", "verify_parser", "verify_items", "official_url",
        "current_url", "first_title", "failure_reason", "note", "suggested_action",
        "source_probe", "source_verify", "coverage_status",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    counts = Counter(row["class"] for row in rows)
    priority_counts = Counter(row["priority"] for row in rows)
    platform_counts = Counter(
        (row["platform"] or "未知", row["class"]) for row in rows
    )
    lines = [
        f"# 核心刊适配 backlog（{args.date}）",
        "",
        f"- 已探测未入包：**{len(rows)}** 本（已排除已入包/已覆盖刊）",
        "- 分类：" + "；".join(f"{name} {count}" for name, count in counts.most_common()),
        "- 优先级：" + "；".join(f"{name} {priority_counts[name]}" for name in sorted(priority_counts)),
        "",
        "## 优先处理",
        "",
        "### P1 已验证 items>0，只需扩包/扩 apply",
        "",
    ]
    p1 = [row for row in rows if row["priority"] == "P1"]
    if p1:
        lines += ["| 期刊 | 平台 | 条数 | 当前入口 |", "|---|---|---:|---|"]
        for row in p1:
            lines.append(
                f"| {row['journal_name']} | {row['platform']} | {row['verify_items']} | "
                f"{row['current_url'] or row['official_url']} |"
            )
    else:
        lines.append("无。")

    lines += ["", "### P2 优先适配（agent 能读、现有 parser 未吃下）", ""]
    p2 = [row for row in rows if row["priority"] == "P2"]
    if p2:
        lines += [
            "| 期刊 | 核心级别 | 平台 | 站点集群 | 集群内可适配数 | 可读条数 | parser 失败原因 | 当前入口 |",
            "|---|---|---|---|---:|---:|---|---|",
        ]
        for row in p2:
            reason = str(row["failure_reason"] or "").replace("|", "/")[:120]
            lines.append(
                f"| {row['journal_name']} | {row['core_levels']} | {row['platform']} | "
                f"{row['site_cluster']} | {row['site_cluster_easy']} | {row['agent_items']} | "
                f"{reason} | {row['current_url'] or row['official_url']} |"
            )
    else:
        lines.append("无。")

    lines += ["", "### A 按站点集群（优先批量适配）", ""]
    cluster_reps = defaultdict(list)
    for row in p2:
        if row["site_cluster"]:
            cluster_reps[row["site_cluster"]].append(row["journal_name"])
    if cluster_reps:
        lines += ["| 站点集群 | 可适配刊数 | 代表期刊 |", "|---|---:|---|"]
        for cluster, names in sorted(cluster_reps.items(), key=lambda item: (-len(item[1]), item[0]))[:25]:
            lines.append(f"| {cluster} | {len(names)} | {'、'.join(names[:6])} |")
    else:
        lines.append("无。")

    lines += ["", "### P3 可重试 / 待补复核", ""]
    p3 = [row for row in rows if row["priority"] == "P3"]
    lines.append(f"共 {len(p3)} 本；按 `B-可重试` 和 `H-未复核` 处理，不写代码。")

    lines += ["", "## 暂缓/跳过", ""]
    for class_name in sorted(name for name in counts if name.startswith(("C-", "D-", "E-", "F-"))):
        lines.append(f"- {class_name}：{counts[class_name]} 本——{CLASS_ACTION.get(class_name, '')}")
    lines += [
        "",
        "## 按平台观察（全部 backlog）",
        "",
        "| 平台 | 数量 |",
        "|---|---:|",
    ]
    for platform, count in Counter(row["platform"] or "未知" for row in rows).most_common():
        lines.append(f"| {platform} | {count} |")
    lines += [
        "",
        f"逐刊清单：[{csv_path.name}]({csv_path.name})",
        "",
        "> 说明：本表只收录“已探测但未入包”的刊；尚未探测的候选不在此表，后续每批探测后重跑本脚本追加。"
        " `A/B` 是后续可处理项，`C/D/E/F` 默认暂缓或跳过；`G` 是已验证只差扩包的最优先项。",
        f"> 重新生成：`python scripts/build_adapter_backlog.py --date {args.date}`。",
    ]
    md_path = CORE / f"core-adapter-backlog-{args.date}.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"backlog {len(rows)}")
    print("classes", dict(counts))
    print("priorities", dict(priority_counts))
    print("csv", csv_path)
    print("md", md_path)


if __name__ == "__main__":
    raise SystemExit(main())
