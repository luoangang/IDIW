import importlib.util
import gzip
import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("rhzh_journals_crawler", ROOT / "crawler.py")
crawler = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = crawler
SPEC.loader.exec_module(crawler)


CURRENT_HTML = '''
<div class="article-list clearfix" id="abc123">
  <div class="article-list-title"><a target="_blank" href="//example.cn/cn/article/doi/10.1/test" class="">当期文章</a></div>
  <div class="article-list-author"><a onclick='searchLike("authorNameCn","张三");'>张三</a></div>
  <div class="article-list-time"><font>2026, 40(3): 1-10.</font><font>doi: <a>10.1/test</a></font></div>
  <div class="article-list-zy"><span class="search-abstract hidden_line_show">当期摘要</span></div>
</div>
'''

CURRENT_DATA = {
    "data": {
        "articles": [{
            "id": "3ecc5385-bc2e-46a6-bbb8-1fd528a18ea7",
            "titleCn": "当期数据文章",
            "abstractinfoCn": "<p>这是来自 current-data 的真实摘要。</p>",
            "doi": "10.1/test",
            "viewUrl": "https://example.cn/",
            "year": 2026,
        }, {
            "id": "toc-entry",
            "titleCn": "目录",
            "doi": "",
            "viewUrl": "https://example.cn/",
            "year": 2026,
        }]
    }
}


class CrawlerTests(unittest.TestCase):
    def test_manifest_matches_fixture_fields(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        item = json.loads((ROOT / "tests" / "items.jsonl").read_text(encoding="utf-8"))
        fields = {field["name"] for field in manifest["output_schema"]["fields"]}
        self.assertEqual(fields, set(item))

    def test_parse_current_issue_markup(self):
        row = {"journal_key": "a" * 16, "name": "示例期刊", "url": "https://example.cn"}
        items = crawler.parse_html_records(CURRENT_HTML, row)
        self.assertEqual(1, len(items))
        self.assertEqual("当期文章", items[0]["title"])
        self.assertEqual("10.1/test", items[0]["doi"])
        self.assertEqual("当期摘要", items[0]["abstract"])

    def test_parse_current_issue_accepts_relative_article_links(self):
        row = {"journal_key": "a" * 16, "name": "示例期刊", "url": "https://example.cn"}
        document = CURRENT_HTML.replace(
            'href="//example.cn/cn/article/doi/10.1/test"', 'href="article/id/abc123"'
        )
        items = crawler.parse_html_records(document, row)
        self.assertEqual(1, len(items))
        self.assertEqual("https://example.cn/article/id/abc123", items[0]["url"])

    def test_parse_resname_template(self):
        row = {"journal_key": "a" * 16, "name": "示例期刊", "url": "https://example.cn"}
        document = (
            '<h3 title="示例文章" class="resName" data-v-1><a '
            'href="https://example.cn/zh/article/doi/10.1/test/" '
            'onclick=\'toDetails({id:175210779,siteId:591})\'>示例文章</a></h3>'
            '<span class="authors clearfix"><em title="张三, 李四" '
            'class="authors-text">张三, 李四</em></span>'
            '<span class="yearIssue"><span>2026, 58(6): 1-14. DOI: 10.1/test</span></span>'
            '<div class="describe"><em class="em-summary">摘要：这是一段示例摘要。</em></div>'
        )
        items = crawler.parse_resname_records(document, row)
        self.assertEqual(1, len(items))
        self.assertEqual("示例文章", items[0]["title"])
        self.assertEqual("10.1/test", items[0]["doi"])
        self.assertEqual("张三, 李四", items[0]["authors"])
        self.assertEqual("这是一段示例摘要。", items[0]["abstract"])
        self.assertEqual("https://example.cn/zh/article/doi/10.1/test/", items[0]["url"])

    def test_read_response_decodes_gzip(self):
        class Response:
            headers = {"Content-Encoding": "gzip"}

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

            def read(self, size):
                return gzip.compress("<html>压缩页面</html>".encode("utf-8"))

        class Opener:
            def open(self, request, timeout):
                return Response()

        self.assertEqual("<html>压缩页面</html>", crawler.read_response(Opener(), None, 5))

    def test_placeholder_listing_abstract_is_rejected(self):
        row = {"journal_key": "a" * 16, "name": "示例期刊", "url": "https://example.cn"}
        document = CURRENT_HTML.replace(
            "当期摘要", '{{@ convertAbstractHtml(article.abstractinfoCn, "cn")}}'
        )
        items = crawler.parse_html_records(document, row)
        self.assertEqual(1, len(items))
        self.assertIsNone(items[0]["abstract"])

    def test_toc_entries_are_excluded(self):
        row = {"journal_key": "a" * 16, "name": "示例期刊", "url": "https://example.cn"}
        document = CURRENT_HTML.replace("当期文章", "2026 年 3 期目次")
        with self.assertRaisesRegex(ValueError, "only placeholder"):
            crawler.parse_html_records(document, row)

    def test_current_issue_items_tries_current_path(self):
        row = {"journal_key": "a" * 16, "name": "示例期刊", "url": "https://example.cn"}
        with patch.object(crawler, "read_response", return_value=CURRENT_HTML) as mocked:
            items = crawler.current_issue_items(None, row, 20)
        self.assertEqual(1, len(items))
        self.assertIn("/cn/article/current", mocked.call_args.args[1].full_url)

    def test_collect_latest_issue_ignores_query(self):
        key = "a" * 16
        journals = {key: {"journal_key": key, "name": "示例期刊", "url": "https://example.cn"}}
        record = {"journal_key": key, "journal_name": "示例期刊", "journal_url": "https://example.cn",
                  "external_id": "abc123", "title": "当期文章", "url": "https://example.cn/1",
                  "authors": "张三", "abstract": "摘要", "doi": "10.1/test", "year": 2026}
        request = {"query": "不会匹配", "limit": 1,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue", "per_journal_limit": 1}}
        with patch.object(crawler, "current_issue_items", return_value=[record]):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(1, len(items))
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)

    def test_enrich_abstract_from_article_page(self):
        item = {"journal_key": "a" * 16, "title": "示例文章", "url": "https://example.cn/article/doi/10.1/test", "abstract": None}
        page = '<div class="article-abstract"><b>摘要:</b> 本文研究了示例问题，并给出结论。</div>'
        with patch.object(crawler, "read_response", return_value=page):
            crawler.enrich_abstract(None, item, 5)
        self.assertEqual("本文研究了示例问题，并给出结论。", item["abstract"])

    def test_enrich_abstract_rejects_placeholder(self):
        item = {"journal_key": "a" * 16, "title": "示例文章", "url": "https://example.cn/article/id/1", "abstract": None}
        page = '<div class="article-abstract">{{@ convertAbstractHtml(article.abstractinfoCn, "cn")}}</div>'
        with patch.object(crawler, "read_response", return_value=page):
            crawler.enrich_abstract(None, item, 5)
        self.assertIsNone(item["abstract"])

    def test_extract_detail_abstract_keeps_nested_paragraphs(self):
        page = ('<li id="abstract"><div class="abstract-cn"><div class="article-abstract">'
                '<b>摘要:</b><div>第一段内容。</div><div>第二段内容。</div></div></div><!-- template -->'
                '<div class="article-abstract {{if dic.abstractContentShowType}}">{{@ convertAbstractHtml(article.abstractinfoCn, "cn")}}</div></li>')
        self.assertEqual("第一段内容。 第二段内容。", crawler.extract_detail_abstract(page))

    def test_extract_detail_abstract_ignores_only_template(self):
        page = ('<div class="article-abstract {{if dic.abstractContentShowType}}">'
                '{{@ convertAbstractHtml(article.abstractinfoCn, "cn")}}</div>')
        self.assertIsNone(crawler.extract_detail_abstract(page))

    def test_parse_current_data_reads_abstractinfo_and_article_url(self):
        row = {"journal_key": "a" * 16, "name": "示例期刊", "url": "https://example.cn"}
        items = crawler.parse_current_data(json.dumps(CURRENT_DATA, ensure_ascii=False), row)
        self.assertEqual(1, len(items))
        self.assertEqual("这是来自 current-data 的真实摘要。", items[0]["abstract"])
        self.assertEqual("https://example.cn/article/doi/10.1/test", items[0]["url"])

    def test_parse_current_data_rejects_placeholder_abstract(self):
        row = {"journal_key": "a" * 16, "name": "示例期刊", "url": "https://example.cn"}
        payload = json.loads(json.dumps(CURRENT_DATA))
        payload["data"]["articles"][0]["abstractinfoCn"] = '{{@ convertAbstractHtml(article.abstractinfoCn, "cn")}}'
        items = crawler.parse_current_data(json.dumps(payload, ensure_ascii=False), row)
        self.assertEqual(1, len(items))
        self.assertIsNone(items[0]["abstract"])

    def test_enrich_abstract_failure_is_non_fatal(self):
        item = {"journal_key": "a" * 16, "title": "示例文章", "url": "https://example.cn/article/id/1", "abstract": None}
        with patch.object(crawler, "read_response", side_effect=OSError("blocked")):
            result = crawler.enrich_abstract(None, item, 5)
        self.assertIs(result, item)
        self.assertIsNone(item["abstract"])

    def test_enrich_abstracts_respects_limit(self):
        rows = [{"title": f"文章{n}", "url": f"https://example.cn/article/id/{n}", "abstract": None} for n in range(5)]
        page = '<div class="article-abstract">真实摘要内容。</div>'
        with patch.object(crawler, "read_response", return_value=page) as mocked:
            crawler.enrich_abstracts(None, rows, 5, 2)
        self.assertEqual(2, mocked.call_count)
        self.assertEqual(2, sum(1 for row in rows if row["abstract"]))
        self.assertEqual(3, sum(1 for row in rows if not row["abstract"]))

    def test_collect_latest_issue_can_disable_enrichment(self):
        key = "a" * 16
        journals = {key: {"journal_key": key, "name": "示例期刊", "url": "https://example.cn"}}
        record = {"journal_key": key, "journal_name": "示例期刊", "journal_url": "https://example.cn",
                  "external_id": "abc123", "title": "当期文章", "url": "https://example.cn/1",
                  "authors": "张三", "abstract": None, "doi": "10.1/test", "year": 2026}
        request = {"query": "不会匹配", "limit": 1,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue",
                                  "per_journal_limit": 1, "enrich_abstract": False}}
        with patch.object(crawler, "current_issue_items", return_value=[record]), \
                patch.object(crawler, "enrich_abstracts") as enrich_mocked:
            items, _, _ = crawler.collect(request, journals)
        enrich_mocked.assert_not_called()
        self.assertIsNone(items[0]["abstract"])

    def test_manifest_exposes_abstract_options(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        properties = manifest["parameters_schema"]["properties"]
        self.assertEqual("1.3.7", manifest["package_version"])
        self.assertIs(True, properties["enrich_abstract"]["default"])
        self.assertEqual(5, properties["abstract_enrich_limit"]["default"])
        self.assertEqual(0, properties["abstract_enrich_limit"]["minimum"])

    def test_manifest_exposes_collect_mode(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        mode = manifest["parameters_schema"]["properties"]["collect_mode"]
        self.assertEqual(["keywords", "latest_issue"], mode["enum"])
        self.assertEqual("keywords", mode["default"])

    def test_manifest_version_bumped_for_issue_filter(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual("1.3.7", manifest["package_version"])

    def test_agricultural_modernization_journal_registered(self):
        rows = json.loads((ROOT / "journals.json").read_text(encoding="utf-8"))
        entry = next(row for row in rows if row["journal_key"] == "00796374865b63f7")
        self.assertEqual("农业现代化研究", entry["name"])
        self.assertEqual("1000-0275", entry["issn"])
        self.assertEqual("43-1132/S", entry["cn"])
        self.assertEqual("https://nyxdhyj.isa.ac.cn/cn/article/current", entry["current_url"])
        self.assertEqual(26, entry["probe_items"])
        pattern = re.compile(entry["article_link_regex"])
        self.assertTrue(pattern.match("https://nyxdhyj.isa.ac.cn/article/doi/10.13872/j.1000-0275.2026.0001"))
        self.assertFalse(pattern.match("https://nyxdhyj.isa.ac.cn/cn/article/current"))

    def test_manifest_capacity_and_default_match_catalog(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        rows = json.loads((ROOT / "journals.json").read_text(encoding="utf-8"))
        properties = manifest["parameters_schema"]["properties"]
        self.assertEqual(len(rows), properties["journal_keys"]["maxItems"])
        self.assertIn("00796374865b63f7", properties["journal_keys"]["default"])


ISSUE_ROW = {"journal_key": "a" * 16, "name": "示例期刊", "url": "https://example.cn"}


def html_entry(article_id, title, citation="", href=None):
    time_block = f'<div class="article-list-time"><font>{citation}</font></div>' if citation else '<div class="article-list-time"><font></font></div>'
    return (
        f'<div class="article-list " id="{article_id}">'
        f'<div class="article-list-title clearfix"><a href="{href or "/article/id/" + article_id}">{title}</a></div>'
        f'{time_block}</div>'
    )


class IssueScopeTests(unittest.TestCase):
    def test_cross_issue_keeps_latest_only(self):
        page = (
            html_entry("old", "上一期文章", "2026, 43(10): 1-10.")
            + html_entry("new", "最新期文章", "2026, 43(11): 11-20.")
        )
        warnings = []
        items = crawler.parse_html_records(page, ISSUE_ROW, warnings)
        self.assertEqual(["最新期文章"], [item["title"] for item in items])
        self.assertEqual(1, len(warnings))
        self.assertIn("过滤 1 条非最新期次", warnings[0])

    def test_advance_entries_dropped_when_current_issue_exists(self):
        page = (
            '<div id="onlineFirst">'
            + html_entry("advance", "网络首发文章")
            + '</div><div id="current">'
            + html_entry("current", "当期文章", "2026, 43(11): 11-20.")
            + "</div>"
        )
        warnings = []
        items = crawler.parse_html_records(page, ISSUE_ROW, warnings)
        self.assertEqual(["当期文章"], [item["title"] for item in items])
        self.assertEqual(1, len(warnings))
        self.assertIn("最新录用/网络首发", warnings[0])

    def test_unknown_issue_kept_with_warning(self):
        page = html_entry("unknown", "无期次标识文章")
        warnings = []
        items = crawler.parse_html_records(page, ISSUE_ROW, warnings)
        self.assertEqual(1, len(items))
        self.assertEqual(1, len(warnings))
        self.assertIn("无法判定期次", warnings[0])

    def test_advance_entries_kept_when_no_current_issue(self):
        page = '<div id="onlineFirst">' + html_entry("advance", "网络首发文章") + "</div>"
        warnings = []
        items = crawler.parse_html_records(page, ISSUE_ROW, warnings)
        self.assertEqual(1, len(items))
        self.assertIn("无法判定期次", warnings[0])

    def test_current_data_filters_stale_issue(self):
        payload = {"data": {"articles": [
            {"id": "old", "titleCn": "旧期文章", "year": 2026, "issue": "10"},
            {"id": "new", "titleCn": "新期文章", "year": 2026, "issue": "11"},
        ]}}
        warnings = []
        items = crawler.parse_current_data(json.dumps(payload, ensure_ascii=False), ISSUE_ROW, warnings)
        self.assertEqual(["new"], [item["external_id"] for item in items])
        self.assertIn("过滤 1 条非最新期次", warnings[0])

    def test_current_data_without_issue_is_kept_with_warning(self):
        payload = {"data": {"articles": [{"id": "a", "titleCn": "无期次文章"}]}}
        warnings = []
        items = crawler.parse_current_data(json.dumps(payload, ensure_ascii=False), ISSUE_ROW, warnings)
        self.assertEqual(1, len(items))
        self.assertIn("无法判定期次", warnings[0])


class AbstractEnrichmentTests(unittest.TestCase):
    def test_meta_dc_description_preferred_over_article_abstract(self):
        page = (
            '<meta name="dc.description" content="&lt;p&gt;中文摘要内容，来自 dc.description。&lt;/p&gt;">'
            '<div class="article-abstract"><b>Abstract:</b> English abstract text.</div>'
        )
        self.assertEqual("中文摘要内容，来自 dc.description。", crawler.extract_detail_abstract(page))

    def test_meta_dc_description_unescapes_numeric_entities(self):
        page = '<meta name="dc.description" content="&lt;p&gt;&#20013;&#25991;&#25688;&#35201;&lt;/p&gt;">'
        self.assertEqual("中文摘要", crawler.extract_detail_abstract(page))

    def test_article_abstract_still_used_as_fallback(self):
        page = '<div class="article-abstract"><b>摘要:</b> 文章容器摘要。</div>'
        self.assertEqual("文章容器摘要。", crawler.extract_detail_abstract(page))

    def test_enrichment_keeps_existing_abstract(self):
        item = {"title": "示例", "url": "https://example.cn/article/id/1", "abstract": "已有摘要"}
        with patch.object(crawler, "read_response") as mocked:
            crawler.enrich_abstracts(None, [item], 5, 1, delay=12.0)
        mocked.assert_not_called()
        self.assertEqual("已有摘要", item["abstract"])

    def test_enrichment_waits_interval_and_backs_off_after_security_page(self):
        item = {"title": "示例", "url": "https://example.cn/article/id/1", "abstract": None}
        security = "<html><body>安全验证，请稍后再试</body></html>"
        detail = '<meta name="dc.description" content="&lt;p&gt;重试后取到的中文摘要。&lt;/p&gt;">'
        with patch.object(crawler, "read_response", side_effect=[security, detail]), \
                patch.object(crawler.time, "sleep") as sleep:
            crawler.enrich_abstracts(None, [item], 5, 1, referer="https://example.cn", delay=12.0, retries=1)
        self.assertEqual([12.0, 18.0], [call.args[0] for call in sleep.call_args_list])
        self.assertEqual("重试后取到的中文摘要。", item["abstract"])

    def test_enrichment_skips_retry_for_plain_empty_page(self):
        item = {"title": "示例", "url": "https://example.cn/article/id/1", "abstract": None}
        with patch.object(crawler, "read_response", return_value="<html><body>no abstract</body></html>") as mocked, \
                patch.object(crawler.time, "sleep"):
            crawler.enrich_abstracts(None, [item], 5, 1, delay=12.0, retries=1)
        self.assertEqual(1, mocked.call_count)
        self.assertIsNone(item["abstract"])


if __name__ == "__main__":
    unittest.main()
