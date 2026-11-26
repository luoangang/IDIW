import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("custom_toc_crawler", ROOT / "crawler.py")
crawler = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = crawler
SPEC.loader.exec_module(crawler)


PAGE = """<html><body>
<a href="/display_son.aspx?Vid=-1&Nid=1&DWid=1">首页</a>
<a href="/display_son.aspx?Vid=-1&Nid=34354&DWid=141">《乐府新声》2026年第3期目录</a>
<a href="/display_son.aspx?Vid=-1&Nid=34353&DWid=141">郭鸣交响乐创作技法研究——以《竹海聆风》为例</a>
<a href="/display_son.aspx?Vid=-1&Nid=34352&DWid=141">宿英的民族器乐创作逻辑与作品特征</a>
</body></html>"""


class CrawlerTests(unittest.TestCase):
    def test_manifest_matches_fixture_fields(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        fields = {field["name"] for field in manifest["output_schema"]["fields"]}
        item = json.loads((ROOT / "tests" / "items.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(fields, set(item))

    def test_catalog_is_stable(self):
        rows = json.loads((ROOT / "journals.json").read_text(encoding="utf-8"))
        self.assertEqual(849, len(rows))
        self.assertEqual(len(rows), len({row["journal_key"] for row in rows}))
        self.assertTrue(all(row.get("data_source") in {"official_site", "official_api", "public_platform"} for row in rows))

    def test_manifest_version(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual("3.10.7", manifest["package_version"])

    def test_decode_html_uses_meta_charset(self):
        raw = '<meta charset="gb2312"><title>中文标题</title>'.encode("gb2312")
        self.assertIn("中文标题", crawler.decode_html(raw, None))

    def test_decode_html_prefers_utf8_bom(self):
        raw = '\ufeff<meta charset="gb2312"><title>中文标题</title>'.encode("utf-8")
        self.assertIn("中文标题", crawler.decode_html(raw, None))

    def test_accept_title_filters_team_intro(self):
        self.assertFalse(crawler.accept_title("三江实验室大豆精深加工及副产物综合利用创新团队"))
        self.assertTrue(crawler.accept_title("大豆精深加工及副产物综合利用研究"))

    def test_parse_toc_filters_directory_and_resolves_relative_links(self):
        items = crawler.parse_toc(PAGE, {
            "journal_key": "a" * 16, "name": "示例期刊", "url": "https://example.cn",
            "current_url": "https://example.cn/display_son.aspx?Vid=-1&Nid=34354&DWid=141",
        })
        self.assertEqual(2, len(items))
        self.assertEqual("34353", items[0]["external_id"])
        self.assertEqual("https://example.cn/display_son.aspx?Vid=-1&Nid=34353&DWid=141", items[0]["url"])
        self.assertEqual("custom_toc", items[0]["source_api"])

    def test_parse_toc_accepts_en_doi_links_and_skips_labels(self):
        page = """<html><body>
        <a href="/EN/10.15302/J-FASE-2026698">Beyond technology in building resilience</a>
        <a href="/article/doi/10.1016/j.virs.2026.08.014">[Abstract]</a>
        <a href="/article/doi/10.1016/j.virs.2026.08.014">Viral manipulation of DNA damage response</a>
        </body></html>"""
        items = crawler.parse_toc(page, {
            "journal_key": "b" * 16, "name": "示例期刊", "url": "https://example.cn",
            "current_url": "https://journal.example.cn/fase/EN/current",
        })
        self.assertEqual(2, len(items))
        self.assertEqual("10.15302/J-FASE-2026698", items[0]["external_id"])
        self.assertEqual("10.15302/J-FASE-2026698", items[0]["doi"])
        self.assertEqual("10.1016/j.virs.2026.08.014", items[1]["doi"])

    def test_parse_json_toc_maps_fields(self):
        journal = {
            "journal_key": "c" * 16, "name": "示例期刊", "url": "https://example.cn",
            "current_url": "https://example.cn/api/latest",
            "json_api": {"url": "https://example.cn/api/latest", "data_path": "data",
                         "fields": {"title": "title", "url": "content", "id": "id", "authors": "author",
                                    "doi": "DOI", "year": "publishTime", "issue": "no"}},
        }
        payload = {"data": {"栏目": [{
            "title": "基于JACK仿真的明式坐具现代办公适配优化研究", "id": 22,
            "content": "https://example.cn/upload/a.pdf", "author": "张三，李四",
            "DOI": "10.16771/j.cn43-1247/ts.2026.08.007", "publishTime": "2026-10-30", "no": 8,
        }]}}
        items = crawler.parse_json_toc(payload, journal)
        self.assertEqual(1, len(items))
        self.assertEqual("22", items[0]["external_id"])
        self.assertEqual("2026年第8期", items[0]["issue"])
        self.assertEqual("10.16771/j.cn43-1247/ts.2026.08.007", items[0]["doi"])
        self.assertEqual("张三，李四", items[0]["authors"])

    def test_parse_json_toc_maps_configured_abstract_field(self):
        journal = {
            "journal_key": "c" * 16, "name": "示例期刊", "url": "https://example.cn",
            "current_url": "https://example.cn/api/latest",
            "json_api": {"url": "https://example.cn/api/latest", "data_path": "data",
                         "fields": {"title": "title", "url": "url", "abstract": "abstractCn"}},
        }
        payload = {"data": [{
            "title": "基于JACK仿真的明式坐具现代办公适配优化研究",
            "url": "https://example.cn/article/1",
            "abstractCn": "本文研究明式坐具在现代办公场景中的适配优化问题，通过JACK仿真评估人体工学表现并提出改进方案。",
        }]}
        items = crawler.parse_json_toc(payload, journal)
        self.assertEqual(1, len(items))
        self.assertIn("JACK仿真", items[0]["abstract"])

    def test_parse_json_toc_uses_common_abstract_fields_by_default(self):
        journal = {
            "journal_key": "c" * 16, "name": "示例期刊", "url": "https://example.cn",
            "current_url": "https://example.cn/api/latest",
            "json_api": {"url": "https://example.cn/api/latest", "data_path": "data",
                         "fields": {"title": "title", "url": "url"}},
        }
        payload = {"data": [
            {"title": "第一篇文章标题示例", "url": "https://example.cn/article/1",
             "abstract": "这是第一篇文章的摘要文本，内容长度足够通过摘要有效性检查，用于验证默认字段映射。"},
            {"title": "第二篇文章标题示例", "url": "https://example.cn/article/2",
             "abstractinfoCn": "这是第二篇文章的中文摘要，字段名为abstractinfoCn，属于常见中文期刊接口字段。"},
            {"title": "第三篇文章标题示例", "url": "https://example.cn/article/3"},
        ]}
        items = crawler.parse_json_toc(payload, journal)
        self.assertEqual(3, len(items))
        self.assertIn("第一篇文章", items[0]["abstract"])
        self.assertIn("第二篇文章", items[1]["abstract"])
        self.assertIsNone(items[2]["abstract"])

    def test_parse_json_toc_rejects_placeholder_or_title_abstract(self):
        journal = {
            "journal_key": "c" * 16, "name": "示例期刊", "url": "https://example.cn",
            "current_url": "https://example.cn/api/latest",
            "json_api": {"url": "https://example.cn/api/latest", "data_path": "data",
                         "fields": {"title": "title", "url": "url", "abstract": "abstract"}},
        }
        title = "这是一个用于验证占位摘要拒绝逻辑的文章标题"
        payload = {"data": [
            {"title": title, "url": "https://example.cn/article/1", "abstract": "暂无"},
            {"title": title + "二", "url": "https://example.cn/article/2", "abstract": title + "二"},
            {"title": title + "三", "url": "https://example.cn/article/3", "abstract": "   "},
        ]}
        items = crawler.parse_json_toc(payload, journal)
        self.assertEqual(3, len(items))
        self.assertTrue(all(item["abstract"] is None for item in items))

    def test_extract_abstract_from_meta_and_label(self):
        meta_page = ('<html><head><meta name="citation_abstract" '
                     'content="这是一段通过citation_abstract元数据提供的摘要文本，长度超过四十个字符，用于验证元数据提取路径。">'
                     '</head></html>')
        self.assertIn("citation_abstract", crawler.extract_abstract(meta_page))
        label_page = """<div id="zhaiyao"><div class="panel-body">
        <p><strong>摘要： </strong><span>针对夏季干旱预测难度大和前兆信号复杂等问题，本文构建多要素综合气候状态变量并开展跨季节预测检验。</span></p>
        <p><strong>关键词: </strong><a>干旱</a></p></div></div>"""
        abstract = crawler.extract_abstract(label_page)
        self.assertTrue(abstract.startswith("针对夏季干旱预测难度大"))
        self.assertNotIn("关键词", abstract)
        value_page = '<div class="CnAbstract"><p class="CnAbstractValue">长期施肥下红壤性水稻土有机碳组分发生变化，本文分析不同施肥处理的碳固存效应及其组分差异。</p></div>'
        self.assertIn("红壤性水稻土", crawler.extract_abstract(value_page))
        label_only_page = '<p class="in_abst">摘要</p><p>光遗传学通过遗传策略限定干预对象，并在明确时间窗口内激活或抑制目标细胞，使研究者能够检验特定通路的因果作用。</p>'
        self.assertIn("光遗传学", crawler.extract_abstract(label_only_page))
        class_page = '<div class="article-abstract"><p>这是一段使用article-abstract样式容器承载的摘要文本，长度足够通过有效性检查并使用通用规则提取。</p></div>'
        self.assertIn("article-abstract", crawler.extract_abstract(class_page))
        self.assertIsNone(crawler.extract_abstract('<div class="article_abstract_main"><h1>文章标题示例</h1></div>'))

    def test_extract_abstract_rejects_placeholder(self):
        self.assertIsNone(crawler.extract_abstract("<p><strong>摘要：</strong>暂无</p>"))
        self.assertIsNone(crawler.extract_abstract("<p><strong>摘要：</strong>无摘要</p>"))
        self.assertIsNone(crawler.extract_abstract("<html><body>没有摘要信息</body></html>"))

    def test_enrich_abstracts_skips_pdf_existing_and_respects_limit(self):
        items = [
            {"url": "https://example.cn/article/1", "title": "第一篇文章", "abstract": None},
            {"url": "https://example.cn/files/2.pdf", "title": "第二篇文章", "abstract": None},
            {"url": "https://example.cn/article/3", "title": "第三篇文章", "abstract": "已有摘要"},
            {"url": "https://example.cn/article/4", "title": "第四篇文章", "abstract": None},
            {"url": "https://example.cn/article/5", "title": "第五篇文章", "abstract": None},
        ]
        article = ('<p><strong>摘要：</strong><span>这是一段从文章详情页提取的摘要文本，内容长度足够通过有效性检查，用于验证补抓逻辑。</span></p>'
                   '<p><strong>关键词：</strong>测试</p>')

        def fake_fetch(url, timeout):
            if url.endswith("/4"):
                raise OSError("boom")
            return article

        with patch.object(crawler, "fetch_text", side_effect=fake_fetch) as fetch, \
                patch.object(crawler.time, "sleep") as sleep:
            crawler.enrich_abstracts(items, 5, 2)
        self.assertIn("文章详情页", items[0]["abstract"])
        self.assertIsNone(items[1]["abstract"])
        self.assertEqual("已有摘要", items[2]["abstract"])
        self.assertIsNone(items[3]["abstract"])
        self.assertIsNone(items[4]["abstract"])
        self.assertEqual(2, fetch.call_count)
        self.assertEqual(1, sleep.call_count)

    def test_collect_enriches_latest_issue_abstract(self):
        key = "a" * 16
        journals = {key: {"journal_key": key, "name": "示例期刊", "url": "https://example.cn",
                          "current_url": "https://example.cn/display_son.aspx?Vid=-1&Nid=34354&DWid=141"}}
        request = {"query": "不会匹配", "limit": 2,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue", "per_journal_limit": 2}}
        article = ('<p><strong>摘要：</strong><span>这是文章详情页中的摘要文本，长度超过四十个字符，用于验证 latest_issue 模式下的摘要补抓。</span></p>'
                   '<p><strong>关键词：</strong>测试</p>')
        with patch.object(crawler, "read_page", return_value=PAGE), \
                patch.object(crawler, "fetch_text", return_value=article) as fetch, \
                patch.object(crawler.time, "sleep"):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(2, len(items))
        self.assertTrue(all(item["abstract"] for item in items))
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)
        self.assertEqual(2, fetch.call_count)

    def test_collect_can_disable_abstract_enrichment(self):
        key = "a" * 16
        journals = {key: {"journal_key": key, "name": "示例期刊", "url": "https://example.cn",
                          "current_url": "https://example.cn/display_son.aspx?Vid=-1&Nid=34354&DWid=141"}}
        request = {"query": "不会匹配", "limit": 2,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue",
                                  "per_journal_limit": 2, "enrich_abstract": False}}
        with patch.object(crawler, "read_page", return_value=PAGE), \
                patch.object(crawler, "fetch_text") as fetch:
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(2, len(items))
        self.assertTrue(all(item["abstract"] is None for item in items))
        fetch.assert_not_called()
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)

    def test_parse_onclick_toc_builds_url_from_template(self):
        page = """<a href="#" onclick="ShowPdf('abc123',0)">青铜峡灌区主要粮食作物生产水足迹时空演变与节水潜力分析</a>"""
        journal = {
            "journal_key": "d" * 16, "name": "示例期刊", "url": "http://example.cn",
            "current_url": "http://example.cn/Home/Qkxx?EPqId=x",
            "onclick_link": {"regex": "ShowPdf\\(\\s*['\"]([^'\"]+)['\"]\\s*,\\s*(\\d+)\\s*\\)",
                             "url_template": "http://example.cn/Home/HtmlPdfView?egjid={0}&mt={1}"},
        }
        items = crawler.parse_onclick_toc(page, journal)
        self.assertEqual(1, len(items))
        self.assertEqual("abc123", items[0]["external_id"])
        self.assertEqual("http://example.cn/Home/HtmlPdfView?egjid=abc123&mt=0", items[0]["url"])

    def test_parse_toc_uses_journal_link_regex(self):
        page = ('<a href="/cn/article/abc123">真实文章标题示例</a>'
                '<a href="/news/1">新闻动态</a>')
        journal = {
            "journal_key": "f" * 16, "name": "示例期刊", "url": "https://example.cn",
            "current_url": "https://example.cn/CN/current",
            "article_link_regex": r"/cn/article/\w+",
        }
        items = crawler.parse_toc(page, journal)
        self.assertEqual(1, len(items))
        self.assertEqual("https://example.cn/cn/article/abc123", items[0]["url"])

    def test_parse_pair_toc_pairs_title_and_abstract_link(self):
        page = """<table>
        <tr><td><b>基于标题文本配对的示例文章</b></td><td><a href="/CN/abstract/abstract123.shtml">摘要</a></td></tr>
        <tr><td><b>封面与目录</b></td><td><a href="/CN/abstract/abstract999.shtml">摘要</a></td></tr>
        </table>"""
        journal = {
            "journal_key": "9" * 16, "name": "示例期刊", "url": "https://example.cn",
            "current_url": "https://example.cn/CN/volumn/current.shtml",
            "pair_link": {"row_regex": r"<tr>.*?</tr>", "title_regex": r"<b>(.*?)</b>",
                          "link_regex": r'href="([^"]*abstract[^"]*)"'},
        }
        items = crawler.parse_pair_toc(page, journal)
        self.assertEqual(1, len(items))
        self.assertEqual("123", items[0]["external_id"])
        self.assertEqual("https://example.cn/CN/abstract/abstract123.shtml", items[0]["url"])

    def test_parse_pair_toc_builds_url_from_js_link_template(self):
        page = ('<table><tr><td class="title">基于JS链接模板的示例文章</td>'
                '<td><a href="Javascript:viewPaper(\'2026-00055p\')">详细</a></td></tr></table>')
        journal = {
            "journal_key": "9" * 16, "name": "示例期刊", "url": "https://example.cn",
            "current_url": "https://example.cn/",
            "pair_link": {
                "row_regex": r"<tr>.*?</tr>",
                "title_regex": r'<td class="title">(.*?)</td>',
                "link_regex": r"viewPaper\('([^']+)'\)",
                "url_template": "https://example.cn/paper?PAPERID={0}",
            },
        }
        items = crawler.parse_pair_toc(page, journal)
        self.assertEqual(1, len(items))
        self.assertEqual("https://example.cn/paper?PAPERID=2026-00055p", items[0]["url"])
        self.assertEqual("基于JS链接模板的示例文章", items[0]["title"])

    def test_collect_skips_empty_upcoming_issue(self):
        key = "7" * 16
        index_page = ('<a href="/article/issue/2026_11">第11期</a>'
                      '<a href="/article/issue/2026_10">第10期</a>')
        empty_issue = "<html><body>暂无文章</body></html>"
        issue_page = ('<a href="article/abstract/202501">第一篇真实文章标题</a>'
                      '<a href="article/abstract/202502">第二篇真实文章标题</a>')
        journals = {key: {
            "journal_key": key, "name": "示例期刊", "url": "https://example.cn",
            "current_url": "https://example.cn/issue/browser",
            "link_base": "https://example.cn/",
            "article_link_regex": r"/article/abstract/\d+$",
            "issue_link": {"regex": "/article/issue/20\\d{2}_\\d+",
                           "base": "https://example.cn/", "require_articles": True},
        }}
        request = {"query": "不会匹配", "limit": 5,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue",
                                  "per_journal_limit": 5, "enrich_abstract": False}}

        def fake_read_page(journal, timeout):
            if journal["current_url"].endswith("/issue/browser"):
                return index_page
            return empty_issue if "2026_11" in journal["current_url"] else issue_page

        with patch.object(crawler, "read_page", side_effect=fake_read_page):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(2, len(items))
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)

    def test_relaxed_title_filter_allows_dynamic_keyword(self):
        title = "智能体人格动态交互框架"
        self.assertFalse(crawler.accept_title(title))
        self.assertTrue(crawler.accept_title(title, {"relaxed_title_filter": True}))

    def test_normalize_url_percent_encodes_non_ascii(self):
        self.assertEqual(
            "https://example.cn/CN/%EF%BC%BBDOI%EF%BC%BD10.%201",
            crawler.normalize_url("https://example.cn/CN/［DOI］10. 1"),
        )

    def test_collect_resolves_latest_issue_from_index(self):
        key = "e" * 16
        index_page = '<a href="journal/article/issue/2026_5">第5期</a>'
        issue_page = ('<a href="journal/article/abstract/20260501">'
                      '晚期分化型甲状腺癌侵犯喉气管食管后的切除与修复</a>')
        journals = {key: {
            "journal_key": key, "name": "示例期刊", "url": "https://example.cn",
            "current_url": "https://example.cn/journal/issue/browser",
            "link_base": "https://example.cn/",
            "issue_link": {"regex": "/article/issue/20\\d{2}_\\d+", "base": "https://example.cn/"},
        }}
        request = {"query": "不会匹配", "limit": 5,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue",
                                  "per_journal_limit": 5, "enrich_abstract": False}}

        def fake_read_page(journal, timeout):
            return issue_page if "issue/2026_5" in journal["current_url"] else index_page

        with patch.object(crawler, "read_page", side_effect=fake_read_page):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(1, len(items))
        self.assertEqual("20260501", items[0]["external_id"])
        self.assertEqual("https://example.cn/journal/article/abstract/20260501", items[0]["url"])
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)

    def test_collect_issue_link_selects_latest_when_index_ascending(self):
        key = "6" * 16
        index_page = ('<a href="/book/2026nian/di1qi/">第1期</a>'
                      '<a href="/book/2026nian/di4qi/">第4期</a>'
                      '<a href="/book/2026nian/di5qi/">第5期</a>'
                      '<a href="/book/2025nian/di6qi/">第6期</a>')
        issue_page = ('<a href="https://example.cn/a/20260928/5551.html">'
                      '当前中国省级城市足球超级联赛的风险研判与路径探索</a>')
        journals = {key: {
            "journal_key": key, "name": "示例期刊", "url": "https://example.cn",
            "current_url": "https://example.cn/book/",
            "link_base": "https://example.cn/",
            "article_link_regex": r"^https?://example\.cn/a/\d{8}/\d+\.html$",
            "issue_link": {"regex": r"/book/20\d{2}nian/di\d+qi/$",
                           "base": "https://example.cn/", "select": "latest"},
        }}
        request = {"query": "不会匹配", "limit": 5,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue",
                                  "per_journal_limit": 5, "enrich_abstract": False}}

        def fake_read_page(journal, timeout):
            return issue_page if "di5qi" in journal["current_url"] else index_page

        with patch.object(crawler, "read_page", side_effect=fake_read_page):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(1, len(items))
        self.assertEqual("https://example.cn/a/20260928/5551.html", items[0]["url"])
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)

    def test_collect_latest_issue(self):
        key = "a" * 16
        journals = {key: {"journal_key": key, "name": "示例期刊", "url": "https://example.cn",
                          "current_url": "https://example.cn/display_son.aspx?Vid=-1&Nid=34354&DWid=141"}}
        request = {"query": "不会匹配", "limit": 2,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue",
                                  "per_journal_limit": 2, "enrich_abstract": False}}
        with patch.object(crawler, "read_page", return_value=PAGE):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(2, len(items))
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)

    def test_keyword_terms_require_all_words_and_allow_aliases(self):
        terms = crawler.keyword_terms({"query": "人工智能 教育", "aliases": ["AI"]})
        self.assertTrue(crawler.matches_keywords({"title": "人工智能在教育中的应用"}, terms))
        self.assertTrue(crawler.matches_keywords({"title": "AI Education"}, terms))
        self.assertFalse(crawler.matches_keywords({"title": "人工智能"}, terms))

    def test_parse_toc_section_bounds_links(self):
        page = ('<a href="/article/1">旧栏目文章标题示例一</a>'
                '<div id="start"></div>'
                '<a href="/article/2">本期文章标题示例二</a>'
                '<div id="end"></div>'
                '<a href="/article/3">其他栏目文章标题示例三</a>')
        journal = {
            "journal_key": "1" * 16, "name": "示例期刊", "url": "https://example.cn",
            "current_url": "https://example.cn/list",
            "article_link_regex": r"/article/\d+$",
            "section_start_regex": r'<div id="start">',
            "section_end_regex": r'<div id="end">',
        }
        items = crawler.parse_toc(page, journal)
        self.assertEqual(1, len(items))
        self.assertEqual("https://example.cn/article/2", items[0]["url"])

    def test_parse_toc_last_section_regex_keeps_latest(self):
        page = ('<span class="btn-primary">第1期</span>'
                '<a href="/article/1">第一期文章标题示例</a>'
                '<span class="btn-primary">第2期</span>'
                '<a href="/article/2">第二期文章标题示例</a>')
        journal = {
            "journal_key": "2" * 16, "name": "示例期刊", "url": "https://example.cn",
            "current_url": "https://example.cn/year",
            "article_link_regex": r"/article/\d+$",
            "last_section_regex": r'<span class="btn-primary">第\d+期</span>',
        }
        items = crawler.parse_toc(page, journal)
        self.assertEqual(1, len(items))
        self.assertEqual("https://example.cn/article/2", items[0]["url"])

    def test_read_page_honors_max_response_bytes(self):
        response = MagicMock()
        response.read.return_value = b"x" * 11
        response.headers.get_content_charset.return_value = "utf-8"
        response.__enter__.return_value = response
        with patch.object(crawler.OPENER, "open", return_value=response):
            with self.assertRaises(ValueError):
                crawler.read_page({"current_url": "https://example.cn", "max_response_bytes": 10}, 5)

    def test_read_page_uses_journal_user_agent(self):
        response = MagicMock()
        response.read.return_value = b"<html></html>"
        response.headers.get_content_charset.return_value = "utf-8"
        response.__enter__.return_value = response
        with patch.object(crawler.OPENER, "open", return_value=response) as opener:
            crawler.read_page({"current_url": "https://example.cn", "user_agent": "ExampleUA"}, 5)
        request = opener.call_args.args[0]
        self.assertEqual("ExampleUA", request.get_header("User-agent"))

    def test_fetch_text_rejects_pdf_response(self):
        response = MagicMock()
        response.headers.get_content_type.return_value = "application/pdf"
        response.__enter__.return_value = response
        with patch.object(crawler.OPENER, "open", return_value=response):
            with self.assertRaises(ValueError):
                crawler.fetch_text("https://example.cn/article/1", 5)
        response.read.assert_not_called()

    def test_collect_follows_pagination(self):
        key = "8" * 16
        page1 = '<a href="/article/1">第一页文章标题示例</a>'
        page2 = '<a href="/article/2">第二页文章标题示例</a>'
        page3 = "<html><body>暂无文章</body></html>"
        journals = {key: {
            "journal_key": key, "name": "示例期刊", "url": "https://example.cn",
            "current_url": "https://example.cn/list?p=1",
            "article_link_regex": r"/article/\d+$",
            "pagination": {"url_template": "https://example.cn/list?p={page}", "start": 2, "max_pages": 3},
        }}
        request = {"query": "不会匹配", "limit": 5,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue",
                                  "per_journal_limit": 5, "enrich_abstract": False}}

        def fake_read_page(journal, timeout):
            url = journal["current_url"]
            if url.endswith("p=1"):
                return page1
            if url.endswith("p=2"):
                return page2
            return page3

        with patch.object(crawler, "read_page", side_effect=fake_read_page):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(2, len(items))
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)
        self.assertEqual("https://example.cn/article/2", items[1]["url"])

    def test_explicit_pagination_resolves_relative_template(self):
        key = "8" * 16
        page1 = '<a href="/article/1">第一页文章标题示例研究</a>'
        page2 = ('<a href="/article/2">第二页文章标题示例研究</a>'
                 '<a href="?apage4=3">3</a>')
        page3 = "<html><body>暂无文章</body></html>"
        journals = {key: {
            "journal_key": key, "name": "示例期刊", "url": "https://example.cn",
            "current_url": "https://example.cn/list.html",
            "article_link_regex": r"/article/\d+$",
            "pagination": {"url_template": "?apage4={page}", "start": 2, "max_pages": 4},
        }}
        request = {"query": "不会匹配", "limit": 5,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue",
                                  "per_journal_limit": 5, "enrich_abstract": False}}
        calls = []

        def fake_read_page(journal, timeout):
            calls.append(journal["current_url"])
            if "apage4=2" in journal["current_url"]:
                return page2
            if "apage4=3" in journal["current_url"]:
                return page3
            return page1

        with patch.object(crawler, "read_page", side_effect=fake_read_page):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(2, len(items))
        self.assertEqual([], warnings)
        self.assertEqual(
            ["https://example.cn/list.html", "https://example.cn/list.html?apage4=2",
             "https://example.cn/list.html?apage4=3"],
            calls,
        )

    def test_auto_pagination_requires_same_issue_marker(self):
        key = "8" * 16
        page1 = ('<div>2026年第11期</div>'
                 '<a href="/article/1">第一页文章标题示例研究</a>'
                 '<a href="?page=2">2</a><a href="?page=3">3</a>')
        page2 = ('<div>2026年第10期</div>'
                 '<a href="/article/2">第二页文章标题示例研究</a>')
        journals = {key: {
            "journal_key": key, "name": "示例期刊", "url": "https://example.cn",
            "current_url": "https://example.cn/list",
            "article_link_regex": r"/article/\d+$",
        }}
        request = {"query": "不会匹配", "limit": 5,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue",
                                  "per_journal_limit": 5, "enrich_abstract": False}}

        def fake_read_page(journal, timeout):
            return page2 if "page=2" in journal["current_url"] else page1

        with patch.object(crawler, "read_page", side_effect=fake_read_page):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(1, len(items))
        self.assertEqual(1, successful)
        self.assertTrue(any("PAGINATION_STOPPED ISSUE_MARKER" in warning for warning in warnings))

    def test_auto_pagination_rejects_year_and_issue_params(self):
        key = "8" * 16
        page1 = ('<a href="/article/1">第一页文章标题示例研究</a>'
                 '<a href="?year_id=2025&page=2">往年</a>'
                 '<a href="?issue=10&page=2">过刊</a>'
                 '<a href="?page=2">2</a><a href="?page=3">3</a>')
        journals = {key: {
            "journal_key": key, "name": "示例期刊", "url": "https://example.cn",
            "current_url": "https://example.cn/list",
            "article_link_regex": r"/article/\d+$",
        }}
        request = {"query": "不会匹配", "limit": 5,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue",
                                  "per_journal_limit": 5, "enrich_abstract": False}}
        calls = []

        def fake_read_page(journal, timeout):
            calls.append(journal["current_url"])
            if "page=2" in journal["current_url"] and "year_id" not in journal["current_url"] \
                    and "issue" not in journal["current_url"]:
                return '<a href="/article/2">第二页文章标题示例研究</a>'
            if "page=3" in journal["current_url"] and "year_id" not in journal["current_url"] \
                    and "issue" not in journal["current_url"]:
                return '<a href="/article/3">第三页文章标题示例研究</a>'
            return page1

        with patch.object(crawler, "read_page", side_effect=fake_read_page):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(3, len(items))
        self.assertEqual([], warnings)
        self.assertFalse(any("year_id" in url or "issue=" in url for url in calls))

    def test_auto_pagination_stops_on_repeated_page(self):
        key = "8" * 16
        page1 = ('<a href="/article/1">第一页文章标题示例研究</a>'
                 '<a href="?page=2">2</a><a href="?page=3">3</a>')
        journals = {key: {
            "journal_key": key, "name": "示例期刊", "url": "https://example.cn",
            "current_url": "https://example.cn/list",
            "article_link_regex": r"/article/\d+$",
        }}
        request = {"query": "不会匹配", "limit": 5,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue",
                                  "per_journal_limit": 5, "enrich_abstract": False}}
        with patch.object(crawler, "read_page", return_value=page1):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(1, len(items))
        self.assertTrue(any("PAGINATION_STOPPED REPEATED_PAGE" in warning for warning in warnings))

    def test_auto_pagination_caps_at_ten_pages(self):
        key = "8" * 16
        page1 = '<a href="/article/1">第一页文章标题示例研究</a>' + "".join(
            f'<a href="?page={number}">{number}</a>' for number in range(2, 16))
        journals = {key: {
            "journal_key": key, "name": "示例期刊", "url": "https://example.cn",
            "current_url": "https://example.cn/list",
            "article_link_regex": r"/article/\d+$",
        }}
        request = {"query": "不会匹配", "limit": 20,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue",
                                  "per_journal_limit": 20, "enrich_abstract": False}}
        calls = []

        def fake_read_page(journal, timeout):
            calls.append(journal["current_url"])
            if journal["current_url"].endswith("/list"):
                return page1
            number = journal["current_url"].rsplit("=", 1)[-1]
            return f'<a href="/article/{number}">第{number}页文章标题示例</a>'

        with patch.object(crawler, "read_page", side_effect=fake_read_page):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(10, len(items))
        self.assertEqual(10, len(calls))
        self.assertTrue(any("PAGE_LIMIT auto 15 capped 10" in warning for warning in warnings))

    def test_explicit_pagination_caps_at_twenty_pages(self):
        journal = {
            "journal_key": "8" * 16, "name": "示例期刊", "url": "https://example.cn",
            "current_url": "https://example.cn/list",
            "article_link_regex": r"/article/\d+$",
            "pagination": {"url_template": "https://example.cn/list?page={page}", "max_pages": 50},
        }
        warnings = []
        with patch.object(crawler, "read_page", return_value="<html>暂无文章</html>") as read:
            crawler.extend_paged_items([], journal, 5, "plain", None, 50, warnings)
        self.assertEqual(1, read.call_count)
        self.assertTrue(any("PAGE_LIMIT requested 50 capped 20" in warning for warning in warnings))

    def test_json_api_does_not_auto_paginate(self):
        journal = {
            "journal_key": "8" * 16, "name": "示例期刊", "url": "https://example.cn",
            "current_url": "https://example.cn/api?page=1",
            "json_api": {"url": "https://example.cn/api?page=1", "data_path": "data",
                         "fields": {"title": "title", "url": "url"}},
        }
        rows = [{"url": "https://example.cn/api/1"}]
        warnings = []
        with patch.object(crawler, "read_page") as read, patch.object(crawler, "fetch_text") as fetch:
            result = crawler.extend_paged_items(
                rows, journal, 5, "json",
                '<a href="?page=2">2</a><a href="?page=3">3</a>', 50, warnings)
        self.assertIs(result, rows)
        self.assertEqual([], warnings)
        read.assert_not_called()
        fetch.assert_not_called()

    def test_json_api_follows_explicit_pagination(self):
        journal = {
            "journal_key": "8" * 16, "name": "示例期刊", "url": "https://example.cn",
            "current_url": "https://example.cn/api?page=1",
            "json_api": {"url": "https://example.cn/api?page=1", "data_path": "data",
                         "fields": {"title": "title", "url": "url"}},
            "pagination": {"url_template": "https://example.cn/api?page={page}", "max_pages": 2},
        }
        rows = crawler.parse_json_toc(
            {"data": [{"title": "第一篇文章标题示例", "url": "https://example.cn/a/1"}]}, journal)
        payload = json.dumps({"data": [{"title": "第二篇文章标题示例", "url": "https://example.cn/a/2"}]},
                             ensure_ascii=False)
        warnings = []
        with patch.object(crawler, "fetch_text", return_value=payload) as fetch:
            result = crawler.extend_paged_items(rows, journal, 5, "json", None, 50, warnings)
        self.assertEqual(2, len(result))
        self.assertEqual("https://example.cn/api?page=2", fetch.call_args[0][0])
        self.assertEqual([], warnings)

    def test_extract_abstract_prefers_long_meta_description(self):
        body = "这是一段由站点描述元数据提供的摘要，用于验证长度阈值。" * 5
        page = f'<html><head><meta name="description" content="{body}"></head></html>'
        self.assertIn("站点描述元数据", crawler.extract_abstract(page))
        short = ('<html><head><meta name="description" content="《示例期刊》由中国示例学会主办，主要刊登经济管理、'
                 '工程技术等领域的研究论文、综述与学术动态，面向国内外公开发行，欢迎投稿与订阅。"></head></html>')
        self.assertIsNone(crawler.extract_abstract(short))

    def test_extract_abstract_reads_bracketed_label(self):
        page = ('<div class=TRS_Editor><div>【摘要】为实现复杂系统安全性分析，本文在MBSE框架下研究'
                '故障模式及影响分析的自动化方法，并给出推进系统示例。</div>'
                '<div>【关键词】载人航天；系统工程</div>'
                '<div>【作者】张三，李四</div></div>')
        abstract = crawler.extract_abstract(page)
        self.assertTrue(abstract.startswith("为实现复杂系统安全性分析"))
        self.assertNotIn("关键词", abstract)
        self.assertNotIn("张三", abstract)

    def test_extract_abstract_reads_zhaiyaojs_and_skips_author_block(self):
        page = """<div class="zhaiyaojs">
        <div style="margin-bottom:10px;" class="main_content_center_left_zhengwen">
          <ul class="AuthorUl"><li>作 者：张三</li></ul>
        </div>
        <div style="margin-bottom:10px;" class="main_content_center_left_zhengwen">
          19世纪以来，公民受教育权与国家教育权的关系愈益复杂，各国开始建立公立学校系统，
          确立国家教育职能，形成以权利为核心的社会政治关系模式，并需要在宪法规范下寻找平衡点。
        </div>
        <div class="main_content_center_left_one_title"><h3><b>Abstract</b></h3></div>
        <div style="margin-bottom:10px;" class="main_content_center_left_zhengwen">
          Since the 19th century, the relationship has become complex and requires balancing.
        </div>
        </div>"""
        abstract = crawler.extract_abstract(page)
        self.assertTrue(abstract.startswith("19世纪以来"))
        self.assertNotIn("AuthorUl", abstract)
        self.assertNotIn("Since the 19th", abstract)

    def test_extract_abstract_does_not_override_existing(self):
        item = {"url": "https://example.cn/article/1", "title": "已有摘要文章", "abstract": "已有摘要内容"}
        with patch.object(crawler, "fetch_text") as fetch:
            crawler.enrich_abstracts([item], 5, 3)
        self.assertEqual("已有摘要内容", item["abstract"])
        fetch.assert_not_called()

    def test_keyword_filter_matches_current_issue(self):
        key = "a" * 16
        journals = {key: {"journal_key": key, "name": "示例期刊", "url": "https://example.cn",
                          "current_url": "https://example.cn/display_son.aspx?Vid=-1&Nid=34354&DWid=141"}}
        request = {"query": "郭鸣", "limit": 10,
                   "parameters": {"journal_keys": [key], "collect_mode": "keywords", "per_journal_limit": 10}}
        with patch.object(crawler, "read_page", return_value=PAGE):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(1, len(items))
        self.assertEqual("郭鸣交响乐创作技法研究——以《竹海聆风》为例", items[0]["title"])
        self.assertEqual([], warnings)


if __name__ == "__main__":
    unittest.main()
