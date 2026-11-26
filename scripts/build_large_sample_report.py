from __future__ import annotations

import csv
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler_platform.config import SETTINGS
from crawler_platform.storage import PlatformStore

BASE_CSV = ROOT / "journal_catalog" / "core" / "run-journals-17-2026-11-25.csv"
RESULT = ROOT / ".local" / "run-17-large-sample-result.json"
STATE = ROOT / ".local" / "platform-large-sample-2026-11-25.json"
OUT_CSV = ROOT / "journal_catalog" / "core" / "large-sample-402-2026-11-25.csv"
OUT_HTML = ROOT / "journal_catalog" / "core" / "large-sample-report-2026-11-25.html"


def abstract_counts(execution_id: str) -> tuple[dict[str, int], dict[str, int]]:
    path = ROOT / "crawler_platform_runtime" / "runs" / execution_id / "output" / "items.jsonl"
    counts: dict[str, int] = {}
    abstracts: dict[str, int] = {}
    if not path.exists():
        return counts, abstracts
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        key = item.get("journal_key") or ""
        counts[key] = counts.get(key, 0) + 1
        text = str(item.get("abstract") or "").strip()
        if text and text not in {"-", "无"}:
            abstracts[key] = abstracts.get(key, 0) + 1
    return counts, abstracts


def main() -> None:
    store = PlatformStore(SETTINGS)
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    state = json.loads(STATE.read_text(encoding="utf-8"))
    package_names = {row["package_key"]: row["name"] for row in store.list_packages()}
    rows: list[dict] = []
    package_summary: list[dict] = []
    for package in result["packages"]:
        package_key = package["package_key"]
        item_counts, abstract_map = abstract_counts(package["execution_id"])
        base_rows = [row for row in csv.DictReader(BASE_CSV.open(encoding="utf-8-sig"))
                     if row["package"] == package_key]
        summary = {"package_key": package_key, "package_name": package_names.get(package_key, package_key),
                   "status": package["status"], "journals": len(base_rows), "items": 0,
                   "abstracts": 0, "ok": 0, "zero": 0, "failed": 0}
        for row in base_rows:
            key = row["journal_key"]
            items = int(row["items"] or 0)
            abstracts = abstract_map.get(key, 0)
            status = row["status"]
            summary["items"] += items
            summary["abstracts"] += abstracts
            summary[status] = summary.get(status, 0) + 1
            rows.append({
                "package_key": package_key,
                "package_name": summary["package_name"],
                "journal_key": key,
                "journal_name": row["journal_name"],
                "items": items,
                "abstracts": abstracts,
                "abstract_rate": round(abstracts / items * 100, 1) if items else 0.0,
                "status": status,
                "error_category": row["error_category"],
                "error": row["error"],
                "target_source": row["target_source"],
            })
        package_summary.append(summary)

    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    total = {
        "journals": len(rows), "items": sum(r["items"] for r in rows),
        "abstracts": sum(r["abstracts"] for r in rows),
        "ok": sum(1 for r in rows if r["status"] == "ok"),
        "zero": sum(1 for r in rows if r["status"] == "zero"),
        "failed": sum(1 for r in rows if r["status"] == "failed"),
    }
    data_json = json.dumps(rows, ensure_ascii=False)
    package_json = json.dumps(package_summary, ensure_ascii=False)
    chart_rows = []
    for p in package_summary:
        total_p = max(1, p["journals"])
        chart_rows.append(
            f'<div class="bar-row"><div class="bar-label">{html.escape(p["package_name"])}</div>'
            f'<div class="bar-track"><span class="bar-ok" style="width:{p["ok"] / total_p * 100:.1f}%"></span>'
            f'<span class="bar-zero" style="width:{p["zero"] / total_p * 100:.1f}%"></span>'
            f'<span class="bar-fail" style="width:{p["failed"] / total_p * 100:.1f}%"></span></div>'
            f'<div class="bar-value">{p["ok"]}/{p["zero"]}/{p["failed"]} · {p["items"]} 条 · 摘要 {p["abstracts"]}</div></div>'
        )
    page = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>IDIW 国内大样本报告 2026-11-25</title>
<style>
body{{font-family:"Microsoft YaHei",system-ui,sans-serif;margin:0;background:#f5f7f8;color:#17212b}}
main{{max-width:1280px;margin:0 auto;padding:28px 24px 48px}}
h1{{font-size:24px;margin:0 0 6px}}h2{{font-size:17px;margin:28px 0 12px}}
.muted{{color:#75818d;font-size:12px;line-height:1.7}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:18px 0}}
.card{{background:#fff;border:1px solid #dce2e5;border-radius:6px;padding:14px}}
.card b{{display:block;font-size:22px;margin-top:4px}}
.ok{{color:#096443}}.fail{{color:#9a2d28}}.warn{{color:#805400}}
.bar-row{{display:grid;grid-template-columns:210px 1fr 180px;gap:10px;align-items:center;margin:7px 0;font-size:12px}}
.bar-label{{color:#435160;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.bar-track{{display:flex;height:14px;background:#eef1f3;border-radius:3px;overflow:hidden}}
.bar-track span{{display:block;height:100%}}
.bar-ok{{background:#2f9e6e}}.bar-zero{{background:#aab4bd}}.bar-fail{{background:#d0675f}}
.bar-value{{color:#75818d;text-align:right}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #d4dbe2}}
th,td{{padding:8px 10px;border-bottom:1px solid #e1e6eb;text-align:left;font-size:12px;vertical-align:top}}
th{{background:#e9edf1;position:sticky;top:0;z-index:1}}
.toolbar{{display:flex;gap:10px;align-items:center;margin:12px 0}}
.toolbar input{{width:280px;min-height:34px;border:1px solid #b8c2cc;border-radius:5px;padding:6px 9px}}
.toolbar select{{min-height:34px;border:1px solid #b8c2cc;border-radius:5px;padding:6px 9px}}
.pill{{display:inline-block;padding:2px 7px;border-radius:9px;font-size:11px;font-weight:600}}
.pill.ok{{background:#dff3e9;color:#096443}}.pill.zero{{background:#eef1f3;color:#536170}}.pill.failed{{background:#f9dfdd;color:#9a2d28}}
.notice{{background:#fff8e6;border:1px solid #f0d48a;padding:12px 14px;border-radius:6px;font-size:12px;line-height:1.8}}
a{{color:#176b5b}}
</style></head><body><main>
<h1>IDIW 国内大样本报告 · 2026-11-25</h1>
<div class="muted">run #17 · 监控 #34「大样本-2026-11-25」· 12 个国内包 · {total["journals"]} 本期刊</div>
<div class="notice" style="margin-top:16px">这是 <b>{total["journals"]}/3113（12.9%）抽样</b>，不是全量逐本验证；每刊最多 10 条、每刊最多补 1 条摘要。页脚有 CSV 下载。</div>
<div class="cards">
<div class="card">抽样期刊<b>{total["journals"]}</b></div>
<div class="card">抓到文章<b>{total["items"]}</b></div>
<div class="card">正常刊<b class="ok">{total["ok"]}</b></div>
<div class="card">0 条<b class="warn">{total["zero"]}</b></div>
<div class="card">失败<b class="fail">{total["failed"]}</b></div>
<div class="card">有摘要<b>{total["abstracts"]}</b></div>
</div>
<h2>各包逐刊结果</h2>
<div class="muted">每行：正常 / 0 条 / 失败 · 抓取条数 · 有摘要条数。绿=正常，灰=0 条，红=失败。</div>
{''.join(chart_rows)}
<h2>固定对照：翻页与摘要</h2>
<div class="cards">
<div class="card">翻页深检<b>112 条</b><div class="muted">卫生研究 25、临床骨科 43、粉煤灰 24、机电工程 20</div></div>
<div class="card">摘要对照（同批 48 本）<b>95.8%</b><div class="muted">修复前 55/92（59.8%）→ 修复后 91/95</div></div>
<div class="card">平台测试<b>164 + 81</b><div class="muted">包内单测 237 passed</div></div>
</div>
<h2>逐刊明细（{total["journals"]} 行）</h2>
<div class="toolbar"><input id="search" placeholder="搜索期刊名 / key / 包"><select id="status"><option value="">全部状态</option><option value="ok">正常</option><option value="zero">0 条</option><option value="failed">失败</option></select><span class="muted" id="count"></span></div>
<div style="max-height:620px;overflow:auto"><table><thead><tr><th>包</th><th>期刊</th><th>key</th><th>条数</th><th>有摘要</th><th>摘要率</th><th>状态</th><th>错误</th></tr></thead><tbody id="rows"></tbody></table></div>
<p class="muted" style="margin-top:20px">CSV：<a href="large-sample-402-2026-11-25.csv">large-sample-402-2026-11-25.csv</a> · 逐刊报告：<a href="run-journals-17-2026-11-25.md">run-journals-17-2026-11-25.md</a></p>
<script>
const data={data_json};
const rows=document.getElementById('rows'),search=document.getElementById('search'),status=document.getElementById('status'),count=document.getElementById('count');
function render(){{
 const q=search.value.trim().toLowerCase(),s=status.value;
 const list=data.filter(r=>(!s||r.status===s)&&(!q||[r.journal_name,r.journal_key,r.package_key,r.package_name].join(' ').toLowerCase().includes(q)));
 count.textContent=`显示 ${{list.length}} / ${{data.length}} 行`;
 rows.innerHTML=list.map(r=>`<tr><td>${{esc(r.package_name)}}</td><td>${{esc(r.journal_name)}}</td><td>${{esc(r.journal_key)}}</td><td>${{r.items}}</td><td>${{r.abstracts}}</td><td>${{r.abstract_rate}}%</td><td><span class="pill ${{r.status}}">${{r.status==='ok'?'正常':r.status==='zero'?'0 条':'失败'}}</span></td><td>${{esc(r.error||'')}}</td></tr>`).join('');
}}
function esc(v){{return String(v??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]))}}
search.addEventListener('input',render);status.addEventListener('change',render);render();
</script>
</main></body></html>"""
    OUT_HTML.write_text(page, encoding="utf-8")
    print("csv", OUT_CSV, "rows", len(rows))
    print("html", OUT_HTML)
    print("summary", total)


if __name__ == "__main__":
    main()
