import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SPEC = importlib.util.spec_from_file_location("vsb_journals_crawler", ROOT / "crawler.py")
crawler = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = crawler
SPEC.loader.exec_module(crawler)


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


PAGE = """<html><body>
<a href="/">首页</a>
<a href="../info/1171/7235.htm"><span>马克思对黑格尔共同体思想的批判与扬弃</span></a>
<a href="../info/1171/7236.htm">2026年第5期目录</a>
<a href="../info/1171/7238.htm">《示例期刊》2026年第4期目录 2026-11-10</a>
<a href="https://m.chaoxing.com/mqk/read/share_ABC123">生成式人工智能如何影响企业关键核心技术突破</a>
<a href="../info/1171/7237.htm">PDF下载</a>
<a href="https://kns.cnki.net/kcms2/article/abstract?v=TOKEN123"><h4>[自] 知网链接文章</h4><p>摘要内容</p></a>
</body></html>"""


class CrawlerTests(unittest.TestCase):
    def test_manifest_matches_item_fields(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        fields = {field["name"] for field in manifest["output_schema"]["fields"]}
        item = crawler.parse_toc(PAGE, {
            "journal_key": "a" * 16,
            "name": "示例期刊",
            "url": "https://example.cn",
            "current_url": "https://example.cn/zxqk/dqml.htm",
        })[0]
        self.assertEqual(fields, set(item))

    def test_catalog_is_stable(self):
        rows = json.loads((ROOT / "journals.json").read_text(encoding="utf-8"))
        self.assertEqual(14, len(rows))
        self.assertEqual(len(rows), len({row["journal_key"] for row in rows}))
        self.assertTrue(all(len(row["journal_key"]) == 16 for row in rows))
        self.assertTrue(all(row.get("data_source") == "official_toc" for row in rows))
        self.assertTrue(all("采集:官网当期目次" in row.get("tags", []) for row in rows))
        manage = next(row for row in rows if row["name"] == "管理科学")
        self.assertEqual("a03529025b270e3b", manage["journal_key"])
        self.assertEqual("http://glkx.hit.edu.cn/dqml.htm", manage["current_url"])
        self.assertEqual("http://glkx.hit.edu.cn/", manage["link_base"])
        self.assertEqual("1672-0334", manage["issn"])
        self.assertEqual("23-1510/C", manage["cn"])
        self.assertEqual(12, manage["probe_items"])
        self.assertEqual("生态法治与环境信息披露——来自准自然实验的证据", manage["probe_first_title"])
        self.assertEqual(r"^https?://glkx\.hit\.edu\.cn/info/\d+/\d+\.htm$", manage["article_link_regex"])

    def test_parse_toc_filters_nav_and_directory_and_resolves_links(self):
        items = crawler.parse_toc(PAGE, {
            "journal_key": "a" * 16,
            "name": "示例期刊",
            "url": "https://example.cn",
            "current_url": "https://example.cn/zxqk/dqml.htm",
        })
        self.assertEqual(3, len(items))
        self.assertEqual("7235", items[0]["external_id"])
        self.assertEqual("https://example.cn/info/1171/7235.htm", items[0]["url"])
        self.assertEqual("ABC123", items[1]["external_id"])
        self.assertEqual("https://m.chaoxing.com/mqk/read/share_ABC123", items[1]["url"])
        self.assertEqual("知网链接文章", items[2]["title"])
        self.assertEqual("TOKEN123", items[2]["external_id"])
        self.assertEqual("official_toc", items[0]["source_api"])

    def test_parse_toc_respects_journal_regex_and_section_bounds(self):
        page = """<html><body>
<div class="article-list article-list-table">
<a href="/info/1020/2500.htm">生态法治与环境信息披露——来自准自然实验的证据</a>
<a href="/info/1020/2500.htm">生态法治与环境信息披露——来自准自然实验的证据</a>
</div>
<div class="main-right">
<a href="/info/1016/1091.htm">管理科学杂志-正文模板</a>
<a href="/info/1017/1097.htm">“经济新常态下发挥经济学期刊引领作用研讨会”综述</a>
</div>
</body></html>"""
        journal = {
            "journal_key": "a" * 16,
            "name": "管理科学",
            "url": "http://glkx.hit.edu.cn",
            "current_url": "http://glkx.hit.edu.cn/dqml.htm",
            "article_link_regex": r"^https?://glkx\.hit\.edu\.cn/info/\d+/\d+\.htm$",
            "section_start_regex": 'class="article-list article-list-table"',
            "section_end_regex": 'class="main-right',
        }
        items = crawler.parse_toc(page, journal)
        self.assertEqual(1, len(items))
        self.assertEqual("2500", items[0]["external_id"])
        self.assertEqual("生态法治与环境信息披露——来自准自然实验的证据", items[0]["title"])

        journal.pop("section_start_regex")
        journal.pop("section_end_regex")
        self.assertEqual(3, len(crawler.parse_toc(page, journal)))

    def test_parse_toc_without_journal_regex_keeps_default_behavior(self):
        journal = {
            "journal_key": "a" * 16,
            "name": "示例期刊",
            "url": "https://example.cn",
            "current_url": "https://example.cn/zxqk/dqml.htm",
        }
        self.assertEqual(3, len(crawler.parse_toc(PAGE, journal)))

    def test_collect_latest_issue(self):
        key = "a" * 16
        journals = {key: {
            "journal_key": key,
            "name": "示例期刊",
            "url": "https://example.cn",
            "current_url": "https://example.cn/zxqk/dqml.htm",
        }}
        request = {
            "query": "不会匹配",
            "limit": 2,
            "parameters": {"journal_keys": [key], "collect_mode": "latest_issue", "per_journal_limit": 2,
                           "enrich_abstract": False},
        }
        with patch.object(crawler, "read_page", return_value=PAGE):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(2, len(items))
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)

    def test_keyword_filter_matches_current_issue(self):
        key = "a" * 16
        journals = {key: {"journal_key": key, "name": "示例期刊", "url": "https://example.cn",
                          "current_url": "https://example.cn/zxqk/dqml.htm"}}
        request = {"query": "人工智能", "limit": 5,
                   "parameters": {"journal_keys": [key], "collect_mode": "keywords", "per_journal_limit": 5}}
        with patch.object(crawler, "read_page", return_value=PAGE):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(1, len(items))
        self.assertIn("人工智能", items[0]["title"])
        self.assertEqual([], warnings)

    def test_extract_abstract_from_meta(self):
        abstract = crawler.extract_detail_abstract(fixture("detail_meta.html"))
        self.assertIn("喀斯特", abstract)
        self.assertGreater(len(abstract), crawler.META_MIN_LENGTH)

    def test_extract_abstract_prefers_container_when_meta_is_short(self):
        page = fixture("detail_container.html")
        self.assertEqual("学报简介", crawler.meta_description(page))
        abstract = crawler.extract_detail_abstract(page)
        self.assertIn("跨区域协同机制", abstract)
        self.assertNotIn("关键词", abstract)

    def test_extract_abstract_from_bracket_tag_and_inline(self):
        tag = crawler.extract_detail_abstract(fixture("detail_tag.html"))
        self.assertIn("数字孪生", tag)
        self.assertNotIn("关键词", tag)
        inline = crawler.extract_detail_abstract(fixture("detail_inline.html"))
        self.assertIn("职业本科教育", inline)
        self.assertNotIn("参考文献", inline)

    def test_extract_abstract_strips_author_prefix_from_meta(self):
        abstract = crawler.extract_detail_abstract(fixture("detail_meta_author.html"))
        self.assertTrue(abstract.startswith("《古汉语反训集释》"))
        self.assertNotIn("【作者】", abstract)

    def test_extract_abstract_strips_fullwidth_abstract_marker(self):
        page = '<html><head><meta name="description" content="［摘 要］目的 观察某药物对模型小鼠的影响，并探讨其可能的作用机制。方法 采用高脂饮食联合链脲佐菌素建立模型，分组给药后检测相关指标，并对数据作统计学分析。结果 给药组指标明显改善。结论 该药物具有潜在的保护作用。"></head></html>'
        abstract = crawler.extract_detail_abstract(page)
        self.assertTrue(abstract.startswith("目的"))
        self.assertNotIn("摘 要", abstract)

    def test_extract_abstract_rejects_site_blurb_meta(self):
        page = '<html><head><meta name="description" content="《示例期刊》杂志于1986年创刊，由某市社科联主管、主办的社科类综合性学术期刊。目前为中文核心期刊、来源期刊，欢迎投稿。"></head><body></body></html>'
        self.assertIsNone(crawler.extract_detail_abstract(page))

    def test_pdf_only_page_is_detected(self):
        self.assertTrue(crawler.looks_pdf_only(fixture("detail_pdf.html")))
        self.assertIsNone(crawler.extract_detail_abstract(fixture("detail_pdf.html")))

    def test_enrich_skips_cnki_and_pdf_and_keeps_existing(self):
        items = [
            {"url": "https://kns.cnki.net/kcms2/article/abstract?v=TOKEN", "title": "知网", "abstract": None},
            {"url": "https://example.cn/upload/paper.pdf", "title": "PDF", "abstract": None},
            {"url": "https://example.cn/info/1/2.htm", "title": "已有", "abstract": "已有摘要，不覆盖"},
            {"url": "https://example.cn/info/1/3.htm", "title": "空摘要", "abstract": None},
        ]
        warnings = []
        with patch.object(crawler, "fetch_detail", return_value=fixture("detail_meta.html")) as fetch, \
                patch.object(crawler.time, "sleep"):
            attempts = crawler.enrich_abstracts(items, 10, 5, warnings, "示例期刊")
        self.assertEqual(1, attempts)
        self.assertEqual(1, fetch.call_count)
        self.assertEqual("已有摘要，不覆盖", items[2]["abstract"])
        self.assertIsNotNone(items[3]["abstract"])
        self.assertEqual([], warnings)

    def test_enrich_skips_pdf_only_page_with_warning(self):
        items = [{"url": "https://example.cn/info/1/2.htm", "title": "仅PDF", "abstract": None},
                 {"url": "https://example.cn/info/1/3.htm", "title": "正常", "abstract": None}]
        pages = {"https://example.cn/info/1/2.htm": fixture("detail_pdf.html"),
                 "https://example.cn/info/1/3.htm": fixture("detail_meta.html")}
        warnings = []
        with patch.object(crawler, "fetch_detail", side_effect=lambda url, timeout: pages[url]), \
                patch.object(crawler.time, "sleep"):
            crawler.enrich_abstracts(items, 10, 5, warnings, "示例期刊")
        self.assertIsNone(items[0]["abstract"])
        self.assertIsNotNone(items[1]["abstract"])
        self.assertEqual(1, len(warnings))
        self.assertIn("仅 PDF", warnings[0])

    def test_enrich_failure_is_non_fatal(self):
        items = [{"url": "https://example.cn/info/1/2.htm", "title": "失败", "abstract": None},
                 {"url": "https://example.cn/info/1/3.htm", "title": "成功", "abstract": None}]
        pages = {"https://example.cn/info/1/2.htm": TimeoutError("timeout"),
                 "https://example.cn/info/1/3.htm": fixture("detail_meta.html")}

        def fake_fetch(url, timeout):
            value = pages[url]
            if isinstance(value, Exception):
                raise value
            return value

        warnings = []
        with patch.object(crawler, "fetch_detail", side_effect=fake_fetch), \
                patch.object(crawler.time, "sleep") as sleep:
            attempts = crawler.enrich_abstracts(items, 10, 5, warnings, "示例期刊")
        self.assertEqual(2, attempts)
        self.assertIsNone(items[0]["abstract"])
        self.assertIsNotNone(items[1]["abstract"])
        self.assertEqual(1, len(warnings))
        self.assertIn("摘要补采失败", warnings[0])
        self.assertEqual(2, sleep.call_count)

    def test_enrich_respects_limit_and_switch(self):
        items = [{"url": f"https://example.cn/info/1/{index}.htm", "title": "文章", "abstract": None}
                 for index in range(4)]
        warnings = []
        with patch.object(crawler, "fetch_detail", return_value=fixture("detail_meta.html")), \
                patch.object(crawler.time, "sleep"):
            attempts = crawler.enrich_abstracts(items, 10, 2, warnings, "示例期刊")
        self.assertEqual(2, attempts)
        self.assertIsNotNone(items[0]["abstract"])
        self.assertIsNotNone(items[1]["abstract"])
        self.assertIsNone(items[2]["abstract"])

    def test_collect_enriches_latest_issue(self):
        key = "a" * 16
        journals = {key: {"journal_key": key, "name": "示例期刊", "url": "https://example.cn",
                          "current_url": "https://example.cn/zxqk/dqml.htm"}}
        request = {"query": "不会匹配", "limit": 3,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue",
                                  "per_journal_limit": 3, "abstract_enrich_limit": 2}}
        with patch.object(crawler, "read_page", return_value=PAGE), \
                patch.object(crawler, "fetch_detail", return_value=fixture("detail_meta.html")), \
                patch.object(crawler.time, "sleep"):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(3, len(items))
        self.assertEqual(1, successful)
        filled = [item for item in items if item["abstract"]]
        self.assertEqual(2, len(filled))
        self.assertEqual([], warnings)


if __name__ == "__main__":
    unittest.main()
