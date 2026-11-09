"""Seven live, sequential assistant trials; created monitors are disabled and archived."""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from crawler_platform.config import SETTINGS
from crawler_platform.storage import PlatformStore


ROOT = Path(__file__).resolve().parent.parent
CN = {"magetech_journals", "cnki_cbpt", "qinyun_journals", "rhzh_journals", "sancai_journals"}
BEIJING = timezone(timedelta(hours=8))


class Client:
    def __init__(self):
        self.opener = build_opener(ProxyHandler({}))
        self.base = f"http://{SETTINGS.host}:{SETTINGS.port}"

    def call(self, path, body=None, method=None):
        headers = {"Content-Type": "application/json"}
        if SETTINGS.token:
            headers["Authorization"] = "Bearer " + SETTINGS.token
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        request = Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=80) as response:
                return json.load(response)
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {error.code}: {detail[:1000]}") from error


def scenarios(stamp):
    def case(key, level, title, prompt, sources, limits, schedule, params, followup=None):
        name = f"AI验收-{stamp}-{key}-{title}"
        return {"id": key, "level": level, "title": title, "name": name,
                "messages": [f"任务名称必须为：{name}。{prompt}"] + ([followup] if followup else []),
                "sources": sources, "limits": limits, "schedule": schedule, "params": params}
    return [
        case("M1", "中等", "科学智能全部中文期刊",
             "我想监控 AI 在科学研究中的应用。主关键词用人工智能，别名加入科学智能、AI for science、AI4S。"
             "覆盖目前已接入的所有中文期刊，是所有期刊，不只是所有采集包或默认几本；不选新闻、百科和外文。"
             "每天北京时间08:30，每个中文期刊包单次上限200，只要元数据和摘要，不要全文。请说明覆盖范围。",
             CN, {key: 200 for key in CN}, ("daily", "08:30", None), "all_cn"),
        case("M2", "中等", "中文论文周监测",
             "监控关键词大语言模型，只用玛格泰克和CBPT中文期刊包，各包期刊范围沿用现有默认选择。"
             "每周一北京时间09:10执行，每包最多140条；玛格泰克每刊最多翻5页，CBPT每刊最多70条。不要新闻和外文。",
             {"magetech_journals", "cnki_cbpt"}, {"magetech_journals": 140, "cnki_cbpt": 140},
             ("weekly", "09:10", 1), "cn_params"),
        case("M3", "中等", "四大期刊科学发现",
             "主题为大语言模型辅助科学发现，英文检索短语用large language models for scientific discovery。"
             "只选外文重点期刊包中的Nature、Science、PNAS、Cell，回看最近7天。"
             "仅保留有摘要的记录，每刊最多25条、整个包最多100条；每天北京时间08:45执行。",
             {"flagship_journals"}, {"flagship_journals": 100}, ("daily", "08:45", None), "english"),
        case("M4", "中等", "军事智能体新闻",
             "监控军事智能体相关新闻，只选Google新闻RSS和通用RSS多源包。"
             "补充准确英文别名，RSS按关键词匹配而非全部收入，RSS回看7天、每个feed最多40条，feed地址沿用现有配置。"
             "Google单次上限80，通用RSS单次上限150，每天北京时间09:20执行。",
             {"google_news_rss", "rss_multi_feed"}, {"google_news_rss": 80, "rss_multi_feed": 150},
             ("daily", "09:20", None), "rss"),
        case("M5", "中等", "六件专利编号查询",
             "仅按这六个已知专利号查基础元数据：US 7,835,543；US 8,471,950；US 7,139,533；"
             "US 10,349,030；US 6,612,488；US 10,244,284。只选美国专利号查询包，单次最多6条。"
             "手动任务，不定时，不做普通关键词专利搜索，也不要立即执行。",
             {"uspto_number_lookup"}, {"uspto_number_lookup": 6}, ("manual", None, None), "patents"),
        case("C1", "较复杂", "多模块两轮调整",
             "监控具身智能，英文别名embodied AI。选Google新闻RSS、通用RSS、玛格泰克、勤云、外文重点期刊五个包；"
             "中文期刊沿用默认选择，外文先用四刊。两个新闻包各100条，两个中文包各70条，外文包60条、每刊15条。"
             "RSS回看7天，外文回看30天，每天北京时间09:00。",
             {"rss_multi_feed", "magetech_journals", "qinyun_journals", "flagship_journals"},
             {"rss_multi_feed": 120, "magetech_journals": 70, "qinyun_journals": 70, "flagship_journals": 40},
             ("daily", "08:10", None), "revision",
             "在刚才草案基础上：去掉Google新闻RSS，其他来源保留。外文只保留Nature和Science，外文每刊20条、整个包40条；"
             "通用RSS整个包上限改120。时间改每天北京时间08:10。中文包上限、已选期刊、两个回看天数和别名都保持不变。"),
        case("C2", "较复杂", "越界需求澄清回退",
             "我要监控科学智能，覆盖所有中文期刊和WoS、Scopus，每15分钟执行，每源最多50000条，保证每条都有摘要。"
             "先判断平台能否完成，有限制必须说清楚，不要把不支持的周期或来源默默替换。",
             CN, {key: 300 for key in CN}, ("weekly", "08:40", 3), "boundary",
             "接受当前平台能力：不接WoS/Scopus，放弃15分钟和每源50000条。改为每周三北京时间08:40，"
             "只用目前已安装的五个中文期刊包，每包最多300条。期刊范围明确改成各包现有默认选择；"
             "不要求摘要一定存在，缺失就保留其他元数据，不加日期过滤。关键词仍为科学智能，任务名保持不变。"),
    ]


def redact(value):
    if isinstance(value, dict):
        return {key: ("[omitted]" if key == "confirmation_token" else
                      f"[omitted {len(item)} URLs]" if key.endswith("urls") and isinstance(item, list) else redact(item))
                for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def judge(case, turns, preview, baseline, journals, persisted):
    checks = []
    def check(label, condition, weight, details="", critical=False):
        checks.append({"label": label, "pass": bool(condition), "weight": weight,
                       "details": details, "critical": critical})
    draft = preview.get("draft") or {}
    packages = {row["package_key"]: row for row in draft.get("packages", []) if isinstance(row, dict) and row.get("enabled", True)}
    config = lambda key: packages.get(key, {}).get("config", {})
    query = str(draft.get("query", ""))
    check("草案有效且任务名称准确", preview.get("ready") and draft.get("name") == case["name"], 5, critical=True)
    topic = {"M1": "人工智能", "M2": "大语言模型", "M3": "大语言模型", "M4": "军事智能体",
             "M5": "US", "C1": "具身智能", "C2": "科学智能"}[case["id"]]
    topic_text = (query + " ".join(draft.get("aliases") or [])).casefold()
    topic_ok = topic.casefold() in topic_text or case["id"] == "M3" and "large language models" in topic_text and "scientific discovery" in topic_text
    check("关键词保留主题（允许等义英文）", topic_ok, 5)
    check("来源选择准确", set(packages) == set(case["sources"]), 20,
          f"expected={sorted(case['sources'])}; actual={sorted(packages)}", critical=True)
    schedule = (draft.get("schedule_type"), draft.get("schedule_time"), draft.get("weekday"))
    check("北京时间计划准确", schedule == case["schedule"] and draft.get("timezone") == "Asia/Shanghai", 15,
          f"expected={case['schedule']}; actual={schedule}", critical=True)
    check("各包上限准确", {key: row.get("item_limit") for key, row in packages.items()} == case["limits"], 15, critical=True)
    mode = case["params"]
    if mode == "all_cn":
        coverage = {key: {"selected": len(set(config(key).get("journal_keys", []))), "catalog": len(journals[key])}
                    for key in CN}
        all_selected = all(set(config(key).get("journal_keys", [])) >= {row["journal_key"] for row in journals[key]} for key in CN)
        check("所有目录期刊均被选择，不是默认少数", all_selected, 25, json.dumps(coverage, ensure_ascii=False), critical=True)
        aliases = " ".join(draft.get("aliases") or []).casefold()
        check("科研同义检索词得到保留", "ai for science" in aliases and "科学智能" in aliases, 5)
    elif mode == "cn_params":
        check("玛格泰克每刊5页", config("magetech_journals").get("max_pages_per_journal") == 5, 15, critical=True)
        check("CBPT每刊70条", config("cnki_cbpt").get("per_journal_limit") == 70, 15, critical=True)
    elif mode == "english":
        cfg = config("flagship_journals")
        check("四刊齐全", set(cfg.get("journal_keys", [])) == {"nature", "science", "pnas", "cell"}, 10, critical=True)
        check("回看7天", cfg.get("lookback_days") == 7, 5)
        check("每刊25条", cfg.get("per_journal_limit") == 25, 5)
        check("要求摘要", cfg.get("require_abstract") is True, 10, critical=True)
    elif mode == "rss":
        cfg = config("rss_multi_feed")
        check("RSS主题匹配", cfg.get("match_mode") == "keywords", 5, critical=True)
        check("RSS回看7天", cfg.get("lookback_days") == 7, 5)
        check("每feed40条", cfg.get("per_feed_limit") == 40, 5)
        check("保留原有订阅地址", cfg.get("feed_urls") == baseline["rss_multi_feed"]["config"].get("feed_urls"), 5)
        expanded = [*(draft.get("aliases") or []), *[term for group in cfg.get("keyword_groups", []) for term in group]]
        broad = [term for term in expanded if term.casefold() in {"autonomous weapons", "intelligent unmanned systems"}]
        check("英文别名未把相关大类当同义词", any(re.search(r"[A-Za-z]{3}", term) for term in expanded) and not broad,
              10, f"broad_terms={sorted(set(broad))}", critical=True)
    elif mode == "patents":
        digits = re.sub(r"[,\s]", "", query)
        check("六个编号均保留", all(number in digits for number in ("7835543", "8471950", "7139533", "10349030", "6612488", "10244284")), 20, critical=True)
        check("没有自动执行时刻", draft.get("schedule_type") == "manual" and preview.get("next_run_at") is None, 10)
    elif mode == "revision":
        check("跨轮保留RSS7天和外文30天", config("rss_multi_feed").get("lookback_days") == 7 and config("flagship_journals").get("lookback_days") == 30, 10, critical=True)
        check("外文仅Nature、Science", set(config("flagship_journals").get("journal_keys", [])) == {"nature", "science"}, 10, critical=True)
        check("外文每刊20条", config("flagship_journals").get("per_journal_limit") == 20, 5)
        check("英文别名保留", "embodied ai" in " ".join(draft.get("aliases") or []).casefold(), 5)
    elif mode == "boundary":
        first = turns[0].get("response", {})
        reply = first.get("reply", "")
        aware = not (first.get("preview") or {}).get("ready") and re.search(r"WoS|Scopus", reply, re.I) and re.search(r"15|分钟", reply)
        check("首轮明确拒绝越界来源和周期", aware, 15, reply, critical=True)
        check("回退后保留五包默认期刊", all(config(key).get("journal_keys") == baseline[key]["config"].get("journal_keys") for key in CN), 10)
        check("不编造中文日期过滤参数", all("lookback_days" not in config(key) for key in CN), 5)
    check("真实建库与参数回读一致，已停用且未运行", persisted.get("verified"), 10,
          json.dumps({key: persisted.get(key) for key in ("id", "verified", "archived", "run_count")}), critical=True)
    score = sum(row["weight"] for row in checks if row["pass"])
    passed = score >= 85 and all(row["pass"] for row in checks if row["critical"])
    return {"score": score, "verdict": "通过" if passed else "部分通过" if persisted.get("id") else "未建成",
            "checks": checks}


def archive_test(client, monitor_id, draft, expected_name):
    rows = client.call("/api/v1/monitors?status=all")
    monitor = next(row for row in rows if row["id"] == monitor_id)
    if monitor["name"] != expected_name or not expected_name.startswith("AI验收-"):
        raise RuntimeError("refuse to change a monitor not owned by this evaluation")
    schedule = {key: draft.get(key) for key in ("schedule_type", "schedule_time", "weekday")}
    if schedule["schedule_time"] is not None:
        schedule["schedule_time"] = str(schedule["schedule_time"])[:5]
    try:
        client.call(f"/api/v1/monitors/{monitor_id}/schedule", schedule | {"enabled": False}, "PATCH")
    except Exception:
        PlatformStore(SETTINGS).update_monitor_schedule(monitor_id, enabled=False, **schedule)
    client.call(f"/api/v1/monitors/{monitor_id}/archive", {}, "POST")


def save_report(path, result):
    path.write_text(json.dumps(redact(result), ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 大模型辅助真实任务创建验收", "", f"测试时间：{result['started_at']}（北京时间）", "",
             "使用正式 API 和真实 DeepSeek；模型输出未人工修正。测试任务创建后立即停用并归档，不执行爬虫。",
             "评分是配置验收，不代表实际采集质量、文章相关性或数据源可用性。目录条目未跨包去重。", "",
             "## 当前中文期刊范围", "", "|包|目录条目|默认选中|单次选择上限|", "|---|---:|---:|---:|"]
    for key, row in result["journal_snapshot"].items():
        lines.append(f"|{key}|{row['catalog_count']}|{row['default_count']}|{row['max_items']}|")
    lines.extend(["", "## 结果", "", "|用例|复杂度|评分|判定|创建ID|已归档|", "|---|---|---:|---|---:|---|"])
    for case in result["cases"]:
        grade, created = case.get("grade", {}), case.get("created", {})
        lines.append(f"|{case['id']} {case['title']}|{case['level']}|{grade.get('score','-')}|{grade.get('verdict','异常')}|{created.get('id','—')}|{created.get('archived',False)}|")
    if result.get("judge_summary"):
        lines.extend(["", "## 裁判结论", ""])
        lines.extend("- " + note for note in result["judge_summary"])
    for case in result["cases"]:
        lines.extend(["", f"## {case['id']} {case['title']}", ""])
        for turn in case.get("turns", []):
            lines.extend([f"### 第 {turn['number']} 轮", "", "用户：" + turn["prompt"], "",
                          "助手：" + turn.get("response", {}).get("reply", turn.get("error", "")), ""])
        for check in case.get("grade", {}).get("checks", []):
            lines.append(f"- {'通过' if check['pass'] else '未通过'}：{check['label']}（{check['weight']}分）" + ("；" + check["details"] if check["details"] else ""))
        if case.get("review_notes"):
            lines.extend(["", "### 人工裁判复核", ""])
            lines.extend("- " + note for note in case["review_notes"])
        if case.get("error"):
            lines.extend(["", "异常：" + case["error"]])
    path.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def rescore(path):
    result = json.loads(path.read_text(encoding="utf-8"))
    for case in result["cases"]:
        checks = case["grade"]["checks"]
        for item in checks:
            if item["label"].startswith("真实建库"):
                item["weight"] = 10
                item["details"] = json.dumps({key: case["created"].get(key) for key in ("id", "verified", "archived", "run_count")})
            if case["id"] == "M3" and item["label"] == "关键词保留主题":
                query = case["created"].get("monitor", {}).get("query_text", "").casefold()
                item.update(label="关键词保留主题（允许等义英文）", **{"pass": "large language models" in query and "scientific discovery" in query})
            if case["id"] == "M4" and item["label"] == "RSS主题匹配":
                item["weight"] = 5
            if case["id"] == "M4" and item["label"] == "英文检索别名":
                aliases = case["created"].get("monitor", {}).get("aliases", [])
                config = case["created"].get("packages", {}).get("rss_multi_feed", {}).get("config", {})
                terms = aliases + [term for group in config.get("keyword_groups", []) for term in group]
                broad = sorted({term for term in terms if term.casefold() in {"autonomous weapons", "intelligent unmanned systems"}})
                item.update(label="英文别名未把相关大类当同义词", weight=10, critical=True,
                            details="独立匹配的宽泛相关词：" + ", ".join(broad))
                item["pass"] = bool(terms) and not broad
        if sum(item["weight"] for item in checks) != 100:
            raise ValueError("rubric weights must sum to 100")
        score = sum(item["weight"] for item in checks if item["pass"])
        passed = score >= 85 and all(item["pass"] for item in checks if item["critical"])
        case["grade"].update(score=score, verdict="通过" if passed else "部分通过" if case["created"].get("id") else "未建成")
        case["created"]["snapshot_phase"] = "disabled_before_archive"
        case["review_notes"] = {
            "M1": ["实际选中5个包、合计9个默认期刊条目，仅占目录834条目的约1.1%，没有覆盖全部期刊。",
                   "回复称4个包且journal_keys留空，但实际为5个包且合并了默认选择；解释与落库配置不一致。",
                   "模型承认看不到完整目录，但草案仍ready=true，确认接口允许创建。应以未解决的覆盖要求阻止确认。",
                   "单包选刊上限与单草案结构限制了全量覆盖，当前助手也没有自动拆分多任务的能力。"],
            "M3": ["使用用户明确提供的等义英文短语作为主查询是合理的，不因缺少中文字面字符串扣分。"],
            "M4": ["autonomous weapons（自主武器）和intelligent unmanned systems（智能无人系统）不是军事智能体的等义表达。",
                   "这些词出现在全局aliases及RSS独立关键词组中，会扩大匹配范围；本次未实际采集，不能据此给出误收率。"],
            "C1": ["两轮后来源删减、不同包上限、双回看窗口和英文别名均正确保留。"],
            "C2": ["正确拒绝未接入来源和15分钟周期，并在用户明确接受能力边界后建成任务。",
                   "首轮对单包上限与每刊上限的说明混用了参数层级；回退后的实际参数正确。"],
        }.get(case["id"], ["需求配置与数据库回读一致，未发现本轮配置问题。"])
    result["review_method"] = "同一轮原始结果人工语义复核；权重归一为100；未重试模型或修改任务配置"
    result["judge_summary"] = [
        "本轮7个场景共9次真实DeepSeek调用，均通过确认接口实际创建任务并回读数据库。模型生成任务期间未人工修改草案。",
        "5个场景完整通过，2个部分通过；每个场景仅测试一次，不能视为长期成功率或统计可靠性结论。",
        "最关键缺陷：全中文期刊需求只配置了5包默认的9个期刊目录项，而不是834个候选目录项（未跨包去重），覆盖约1.1%。",
        "M1的助手说明中还存在4个包/实际5个包、journal_keys留空/实际默认选中的不一致，且未解决覆盖要求仍允许确认。",
        "第二项缺陷：军事智能体被扩成自主武器、智能无人系统等相关大类，形成独立OR匹配，可能增加误收；本轮没有实际采集，无法给出误收比例。",
        "跨轮参数保留、不同来源条数、北京时间每日/每周计划和专利号查询在本轮通过；越界需求经用户明确收缩后可正确创建。",
        "优先改进：由平台把all/按标签等期刊范围解析为精确目录；超出单包上限则阻止确认或规划分批，不能静默退回默认期刊。",
        "优先改进：将等义翻译/同义词与相关概念分开，相关概念默认不启用；预览固定显示实际选中来源数、选刊数和未覆盖数。",
        "所有测试任务#14–#20已经停用并归档；另用MySQL只读查询复核7项均未运行，monitor_runs中对应记录为0。未更改既有任务。",
        "本轮仅验收对话建任务及配置落库，不验收实际爬取数量、来源连通性、摘要获取率或文章相关性。",
    ]
    save_report(path, result)
    print(json.dumps({case["id"]: case["grade"] | {"checks": None} for case in result["cases"]}, ensure_ascii=False))


def main():
    stamp = datetime.now(BEIJING).strftime("%Y%m%d-%H%M%S")
    output = ROOT / "reports" / f"assistant-evaluation-{stamp}.json"
    output.parent.mkdir(exist_ok=True)
    client = Client()
    catalog_response = client.call("/api/v1/assistant/catalog")
    if not catalog_response.get("configured"):
        raise RuntimeError("DeepSeek not configured")
    baseline = {row["package_key"]: row for row in catalog_response["sources"]}
    journals = {key: client.call(f"/api/v1/packages/{key}/journals") for key in sorted(CN)}
    result = {"started_at": datetime.now(BEIJING).isoformat(), "model": catalog_response["model"], "cases": [],
              "journal_snapshot": {key: {"catalog_count": len(journals[key]),
                                          "default_count": len(baseline[key]["config"].get("journal_keys", [])),
                                          "max_items": baseline[key]["parameters_schema"]["properties"]["journal_keys"].get("maxItems")}
                                   for key in sorted(CN)}}
    print(f"REPORT {output}", flush=True)
    for case in scenarios(stamp):
        record = {key: value for key, value in case.items() if key not in {"sources", "limits", "schedule", "params"}}
        record["turns"] = []
        record["created"] = {}
        history, draft, preview = [], None, {}
        result["cases"].append(record)
        try:
            for number, prompt in enumerate(case["messages"], 1):
                started = time.monotonic()
                response = client.call("/api/v1/assistant/chat", {"messages": [*history, {"role": "user", "content": prompt}], "draft": draft})
                record["turns"].append({"number": number, "prompt": prompt, "elapsed_seconds": round(time.monotonic()-started, 2), "response": response})
                history.extend([{"role": "user", "content": prompt}, {"role": "assistant", "content": response["reply"]}])
                preview = response.get("preview") or {}
                draft = preview.get("draft") or response.get("draft") or draft
                save_report(output, result)
            if preview.get("ready") and draft.get("name") == case["name"]:
                next_run = preview.get("next_run_at")
                if next_run and datetime.fromisoformat(next_run.replace("Z", "+00:00")) <= datetime.now(timezone.utc) + timedelta(minutes=2):
                    raise RuntimeError("test schedule is too close; refuse to enable")
                created = client.call("/api/v1/assistant/monitors", {"draft": draft, "confirmation_token": preview["confirmation_token"], "confirmed": True})
                monitor_id = created["id"]
                record["created"]["id"] = monitor_id
                try:
                    client.call(f"/api/v1/monitors/{monitor_id}/schedule", {"schedule_type": draft["schedule_type"], "schedule_time": draft.get("schedule_time"),
                                "weekday": draft.get("weekday"), "enabled": False}, "PATCH")
                    rows = client.call("/api/v1/monitors?status=all")
                    monitor = next(row for row in rows if row["id"] == monitor_id)
                    packages = client.call(f"/api/v1/monitors/{monitor_id}/packages")
                    actual = {row["package_key"]: {"item_limit": row["item_limit"], "config": row["config"]} for row in packages if row["attached"] and row["enabled"]}
                    expected = {row["package_key"]: {"item_limit": row["item_limit"], "config": row["config"]} for row in draft["packages"]}
                    runs = [row for row in client.call("/api/v1/runs?limit=200") if row["monitor_id"] == monitor_id]
                    verified = (not monitor["enabled"] and monitor["name"] == draft["name"] and monitor["query_text"] == draft["query"]
                                and monitor["aliases"] == draft["aliases"] and monitor["schedule_type"] == draft["schedule_type"]
                                and (str(monitor.get("schedule_time") or "")[:5] or None) == draft.get("schedule_time")
                                and monitor.get("weekday") == draft.get("weekday") and actual == expected and not runs)
                    record["created"].update(verified=verified, monitor=monitor, packages=actual, run_count=len(runs))
                finally:
                    archive_test(client, monitor_id, draft, case["name"])
                    archived = next(row for row in client.call("/api/v1/monitors?status=archived") if row["id"] == monitor_id)
                    record["created"]["archived"] = bool(archived["archived_at"]) and not archived["enabled"]
            record["grade"] = judge(case, record["turns"], preview, baseline, journals, record["created"])
        except Exception as error:
            record["error"] = f"{type(error).__name__}: {error}"
            record["grade"] = judge(case, record["turns"], preview, baseline, journals, record["created"])
        # Recover even when creation committed but its HTTP response was lost.
        try:
            owned = [row for row in client.call("/api/v1/monitors?status=all")
                     if row["name"] == case["name"] and row["archived_at"] is None]
            for monitor in owned:
                archive_test(client, monitor["id"], monitor, case["name"])
                record["created"].update(id=monitor["id"], archived=True)
        except Exception as cleanup_error:
            record["cleanup_error"] = str(cleanup_error)
            save_report(output, result)
            raise RuntimeError("test cleanup failed; stop evaluation") from cleanup_error
        save_report(output, result)
        print(json.dumps({"case": case["id"], "score": record["grade"]["score"], "verdict": record["grade"]["verdict"],
                          "created_id": record["created"].get("id"), "archived": record["created"].get("archived"), "error": record.get("error")}, ensure_ascii=True), flush=True)
    result["finished_at"] = datetime.now(BEIJING).isoformat()
    result["total_tokens"] = sum(turn.get("response", {}).get("usage", {}).get("total_tokens", 0) for case in result["cases"] for turn in case["turns"])
    save_report(output, result)
    print(f"TOTAL_TOKENS {result['total_tokens']}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--rescore":
        rescore(Path(sys.argv[2]).resolve())
    else:
        main()
