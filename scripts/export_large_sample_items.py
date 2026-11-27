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

RESULT = ROOT / ".local" / "run-17-large-sample-result.json"
STATE = ROOT / ".local" / "platform-large-sample-2026-11-25.json"
OUT_CSV = ROOT / "journal_catalog" / "core" / "large-sample-402-items-2026-11-25.csv"
OUT_ABSTRACT_CSV = ROOT / "journal_catalog" / "core" / "large-sample-402-abstracts-2026-11-25.csv"
OUT_HTML = ROOT / "journal_catalog" / "core" / "large-sample-items-report-2026-11-25.html"


def text_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item) for item in value if item is not None)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def main() -> None:
    store = PlatformStore(SETTINGS)
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    state = json.loads(STATE.read_text(encoding="utf-8"))
    package_names = {row["package_key"]: row["name"] for row in store.list_packages()}
    journal_names = {
        (package_key, key): name
        for package_key, rows in state["samples"].items()
        for key, name in rows
    }
    rows: list[dict] = []
    for package in result["packages"]:
        package_key = package["package_key"]
        path = ROOT / "crawler_platform_runtime" / "runs" / package["execution_id"] / "output" / "items.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            abstract = text_value(item.get("abstract") or item.get("summary"))
            key = str(item.get("journal_key") or "")
            rows.append({
                "package_key": package_key,
                "package_name": package_names.get(package_key, package_key),
                "journal_key": key,
                "journal_name": text_value(item.get("journal_name")) or journal_names.get((package_key, key), ""),
                "title": text_value(item.get("title")),
                "abstract": abstract,
                "has_abstract": "是" if abstract.strip() else "否",
                "abstract_length": len(abstract.strip()),
                "authors": text_value(item.get("authors") or item.get("author")),
                "doi": text_value(item.get("doi")),
                "url": text_value(item.get("url") or item.get("article_url")),
                "pdf_url": text_value(item.get("pdf_url")),
                "published_at": text_value(item.get("published_at")),
                "year": text_value(item.get("year")),
                "volume": text_value(item.get("volume")),
                "issue": text_value(item.get("issue")),
                "pages": text_value(item.get("pages")),
                "external_id": text_value(item.get("external_id")),
            })
    rows.sort(key=lambda row: (row["package_key"], row["journal_name"], row["title"]))
    fields = list(rows[0])
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with OUT_ABSTRACT_CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows([row for row in rows if row["has_abstract"] == "是"])

    with_abstract = sum(1 for row in rows if row["has_abstract"] == "是")
    packages = []
    for package_key in dict.fromkeys(row["package_key"] for row in rows):
        subset = [row for row in rows if row["package_key"] == package_key]
        packages.append({
            "key": package_key,
            "name": package_names.get(package_key, package_key),
            "total": len(subset),
            "abstracts": sum(1 for row in subset if row["has_abstract"] == "是"),
        })
    embedded = [{k: row[k] for k in ("package_name", "journal_name", "title", "abstract",
                                     "authors", "doi", "url", "published_at", "has_abstract")} for row in rows]
    data_json = json.dumps(embedded, ensure_ascii=False).replace("</", "<\\/")
    package_options = "".join(
        f'<option value="{html.escape(item["key"])}">{html.escape(item["name"])}</option>' for item in packages
    )
    cards = "".join(
        f'<div class="card">{html.escape(item["name"])}<b>{item["total"]}</b><span class="muted">有摘要 {item["abstracts"]}</span></div>'
        for item in packages
    )
    page = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>IDIW 大样本文章明细</title>
<style>
body{{font-family:"Microsoft YaHei",system-ui,sans-serif;margin:0;background:#f5f7f8;color:#17212b;min-width:1180px}}
main{{max-width:1520px;margin:0 auto;padding:26px 22px 48px}}
h1{{font-size:23px;margin:0 0 6px}}h2{{font-size:16px;margin:24px 0 10px}}
.muted{{color:#75818d;font-size:12px;line-height:1.7}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:16px 0}}
.card{{background:#fff;border:1px solid #dce2e5;border-radius:6px;padding:12px;font-size:12px;color:#536170}}
.card b{{display:block;font-size:20px;color:#17212b;margin:4px 0 0}}
.toolbar{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:14px 0}}
.toolbar input{{width:300px;min-height:34px;border:1px solid #b8c2cc;border-radius:5px;padding:6px 9px}}
.toolbar select{{min-height:34px;border:1px solid #b8c2cc;border-radius:5px;padding:6px 9px}}
.toolbar label{{font-size:12px;color:#536170;display:flex;gap:5px;align-items:center}}
table{{width:100%;min-width:1100px;border-collapse:collapse;background:#fff;border:1px solid #d4dbe2;table-layout:fixed}}
th,td{{padding:8px 10px;border-bottom:1px solid #e1e6eb;text-align:left;font-size:12px;vertical-align:top}}
th:nth-child(1){{width:210px}}th:nth-child(2){{width:330px}}th:nth-child(4){{width:76px}}
th{{background:#e9edf1;position:sticky;top:0;z-index:1}}
td.title{{color:#176b5b;cursor:pointer;overflow-wrap:anywhere}}
td.abstract{{color:#435160;line-height:1.7;white-space:pre-wrap;overflow-wrap:anywhere}}
.pill{{display:inline-block;padding:2px 7px;border-radius:9px;font-size:11px;font-weight:600;background:#dff3e9;color:#096443}}
.pill.no{{background:#eef1f3;color:#536170}}
.pagination{{display:flex;gap:8px;align-items:center;justify-content:flex-end;margin-top:12px;font-size:12px}}
.pagination button{{min-height:30px;border:1px solid #b8c2cc;background:#fff;color:#365d7d;border-radius:4px;padding:4px 10px;cursor:pointer}}
dialog{{width:820px;max-width:calc(100vw - 30px);max-height:86vh;overflow:auto;border:1px solid #b8c2cc;border-radius:6px;padding:22px;color:#17212b}}
dialog::backdrop{{background:rgba(23,33,43,.45)}}
.modal-title{{font-size:17px;font-weight:700;line-height:1.6;margin:0 0 8px}}
.modal-meta{{font-size:12px;color:#75818d;line-height:1.8;margin-bottom:14px;overflow-wrap:anywhere}}
.modal-abstract{{white-space:pre-wrap;line-height:1.9;font-size:13px;background:#f7f9fa;border:1px solid #e1e6eb;border-radius:5px;padding:14px}}
a{{color:#176b5b}}
</style></head><body><main>
<h1>IDIW 大样本文章明细 · 2026-11-25</h1>
<div class="muted">run #17 · 402 本抽样 · {len(rows)} 篇文章 · 有摘要 {with_abstract} 篇 · 摘要为空白的不代表解析失败，可能站点本身无摘要或本轮只补 1 条/刊</div>
<div class="cards">{cards}</div>
<div class="toolbar">
<input id="q" placeholder="搜索标题 / 摘要 / 期刊 / 作者 / DOI">
<select id="package"><option value="">全部包</option>{package_options}</select>
<label><input type="checkbox" id="onlyAbstract"> 只看有摘要</label>
<span class="muted" id="count"></span>
</div>
<div style="overflow:auto"><table><thead><tr><th style="width:150px">包 / 期刊</th><th style="width:25%">标题</th><th>摘要（前 220 字，点击标题看全文）</th><th style="width:72px">摘要</th></tr></thead><tbody id="rows"></tbody></table></div>
<div class="pagination"><span id="pageInfo"></span><button id="prev">上一页</button><button id="next">下一页</button></div>
<p class="muted" style="margin-top:20px">CSV：<a href="large-sample-402-items-2026-11-25.csv">全部文章（含摘要列）</a> · <a href="large-sample-402-abstracts-2026-11-25.csv">仅有摘要</a> · 逐刊汇总：<a href="large-sample-report-2026-11-25.html">402 本报告</a></p>
<dialog id="detail"><button id="close" style="float:right">关闭</button><h2 class="modal-title" id="mTitle"></h2><div class="modal-meta" id="mMeta"></div><div class="modal-abstract" id="mAbstract"></div><p class="muted" id="mLink"></p></dialog>
<script>
const data={data_json};
let page=1,pageSize=50,filtered=data;
const $=id=>document.getElementById(id);
function esc(v){{return String(v??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]))}}
function apply(){{
 const q=$('q').value.trim().toLowerCase(),pkg=$('package').value,only=$('onlyAbstract').checked;
 filtered=data.filter(r=>{{if(pkg&&r.package_name!==pkg&&!r.package_name.includes(pkg))return false;if(only&&r.has_abstract!=='是')return false;if(!q)return true;return [r.title,r.abstract,r.journal_name,r.authors,r.doi].join(' ').toLowerCase().includes(q)}});
 page=1;render();
}}
function render(){{
 const pages=Math.max(1,Math.ceil(filtered.length/pageSize));page=Math.min(page,pages);
 $('count').textContent=`共 ${{filtered.length}} 篇`;
 $('pageInfo').textContent=`第 ${{page}} / ${{pages}} 页`;
 $('prev').disabled=page<=1;$('next').disabled=page>=pages;
 const slice=filtered.slice((page-1)*pageSize,page*pageSize);
 $('rows').innerHTML=slice.map((r,i)=>{{
   const idx=(page-1)*pageSize+i;
   const preview=(r.abstract||'').replace(/\\s+/g,' ').slice(0,220);
   return `<tr><td>${{esc(r.package_name)}}<div class="muted">${{esc(r.journal_name)}}</div></td><td class="title" data-i="${{idx}}">${{esc(r.title)}}</td><td class="abstract">${{esc(preview)}}${{r.abstract&&r.abstract.length>220?'…':''}}</td><td><span class="pill ${{r.has_abstract==='是'?'':'no'}}">${{r.has_abstract==='是'?'有':'无'}}</span></td></tr>`
 }}).join('')||'<tr><td colspan="4" class="muted">没有匹配文章</td></tr>';
}}
$('rows').addEventListener('click',e=>{{
 const cell=e.target.closest('[data-i]');if(!cell)return;const r=filtered[Number(cell.dataset.i)];if(!r)return;
 $('mTitle').textContent=r.title||'（无标题）';
 $('mMeta').textContent=[r.package_name,r.journal_name,r.authors,r.published_at,r.doi].filter(Boolean).join(' · ');
 $('mAbstract').textContent=r.abstract||'（本条没有摘要）';
 $('mLink').innerHTML=r.url?`<a href="${{esc(r.url)}}" target="_blank" rel="noopener noreferrer">打开原文</a>`:'';
 $('detail').showModal();
}});
$('close').addEventListener('click',()=>$('detail').close());
$('q').addEventListener('input',apply);$('package').addEventListener('change',apply);$('onlyAbstract').addEventListener('change',apply);
$('prev').addEventListener('click',()=>{{if(page>1){{page--;render()}}}});$('next').addEventListener('click',()=>{{if(page<Math.ceil(filtered.length/pageSize)){{page++;render()}}}});
render();
</script>
</main></body></html>"""
    OUT_HTML.write_text(page, encoding="utf-8")
    print("csv", OUT_CSV, "rows", len(rows))
    print("abstract csv", OUT_ABSTRACT_CSV, "rows", with_abstract)
    print("html", OUT_HTML)
    print("with abstract", with_abstract, "of", len(rows))


if __name__ == "__main__":
    main()
