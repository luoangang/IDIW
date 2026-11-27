import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("candidate_crawler", ROOT / "crawler.py")
CRAWLER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CRAWLER
SPEC.loader.exec_module(CRAWLER)


class CrawlerTests(unittest.TestCase):
    def test_search_sql_contains_keyword_fields_and_page(self):
        value = CRAWLER.search_sql("人工智能", "1", 3)
        self.assertIn("人工智能[Title]", value)
        self.assertIn("人工智能[Abstract]", value)
        self.assertIn("3[Pager]", value)

    def test_parse_magetech_result(self):
        document = '''
        <li id="art123456" class="noselectrow">
          <div class="j-title"><a href="https://www.lis.ac.cn/CN/10.13266/test">人工智能研究</a></div>
          <div class="j-author">张三, 李四</div>
          <span class="j-volumn">2026, 70(1): 1-10</span>
          <div class="j-abstract"><p>这是摘要。</p></div>
          <a href="https://doi.org/10.13266/test">DOI</a>
          <script>lsdy1('PDF','987','https://www.lis.ac.cn')</script>
        </li>
        '''
        item = CRAWLER.parse_items(document, CRAWLER.JOURNALS["lis"])[0]
        self.assertEqual("123456", item["external_id"])
        self.assertEqual(["张三", "李四"], item["authors"])
        self.assertEqual(2026, item["year"])
        self.assertEqual("10.13266/test", item["doi"])
        self.assertIn("id=987", item["pdf_url"])

    def test_fixture_matches_manifest_fields(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        item = json.loads((ROOT / "tests" / "items.jsonl").read_text(encoding="utf-8"))
        fields = {field["name"] for field in manifest["output_schema"]["fields"]}
        self.assertEqual(fields, set(item))

    def test_all_supplier_labeled_journals_are_configured(self):
        rows = json.loads((ROOT / "journals.json").read_text(encoding="utf-8"))
        self.assertEqual(417, len(rows))
        self.assertEqual(417, len({row["journal_key"] for row in rows}))
        self.assertTrue(all(row["supplier"] == "玛格泰克" for row in rows))
        self.assertTrue({"data_analysis", "lis", "qbzl"}.issubset(CRAWLER.JOURNALS))
        self.assertEqual(417, len(CRAWLER.JOURNALS))
        qbzl_row = next(row for row in rows if row["name"] == "情报资料工作")
        self.assertEqual("qbzl", qbzl_row["journal_key"])
        self.assertTrue(set(CRAWLER.DEFAULT_JOURNAL_KEYS) <= {row["journal_key"] for row in rows})

    def test_diangong_jishu_xuebao_config(self):
        rows = json.loads((ROOT / "journals.json").read_text(encoding="utf-8"))
        row = next(row for row in rows if row["name"] == "电工技术学报")
        self.assertEqual("eb848c086da3fb6d", row["journal_key"])
        self.assertEqual("1000-6753", row["issn"])
        self.assertEqual("11-2188/TM", row["cn"])
        self.assertEqual("2026-11-26", row["verified_at"])
        self.assertEqual(23, row["probe_items"])
        self.assertEqual(
            "https://dgjsxb.ces-transaction.com/CN/volumn/current.shtml",
            row["current_url"],
        )
        sample = "https://dgjsxb.ces-transaction.com/CN/abstract/abstract11302.shtml"
        self.assertTrue(sample.startswith(row["link_base"]))
        self.assertRegex(sample, row["article_link_regex"])
        journal = CRAWLER.journal_from_catalog(row)
        self.assertEqual(row["current_url"], CRAWLER.current_issue_url(journal))

    def test_old_template_search_result(self):
        document = '''<DIV id=art456 class=noselectrow><a class="txt_biaoti"
          href="/CN/10.1234/test">旧版文章</a><span class="abs_zuozhe_cn">张三,李四</span>
          <span class="abs_njq">2025, 12(3): 1-9</span>
          <div id="Abstract456" class="white_content"><p>旧版摘要</p></div></DIV>'''
        item = CRAWLER.parse_search_result(document, CRAWLER.JOURNALS["lis"])[0]
        self.assertEqual("456", item["external_id"])
        self.assertEqual("旧版文章", item["title"])
        self.assertEqual(["张三", "李四"], item["authors"])
        self.assertEqual(2025, item["year"])

    def test_legacy_table_toc_parses_article_and_skips_index(self):
        document = '''
        <TABLE border=0>
          <TR><TD class="J_VM" width="5%">0</TD><TD class="J_VM">编辑部</TD></TR>
          <TR><TD class="J_VM"><b>2026年第41卷第21期目录</b></TD></TR>
          <TR><TD class="J_VM">2026&nbsp;Vol. 41&nbsp;(21):&nbsp;0-0
            [<A href="../abstract/abstract11301.shtml">摘要</A>]</TD></TR>
        </TABLE>
        <TABLE border=0>
          <TR><TD class="J_VM" width="5%">7161</TD><TD class="J_VM">徐巍, 赖智鹏, 李亮</TD></TR>
          <TR><TD class="J_VM"><b>局部脉冲强磁场驱动下的薄壁金属构件变形稳定性研究</b></TD></TR>
          <TR><TD class="J_VM">2026&nbsp;Vol. 41&nbsp;(21):&nbsp;7161-7172
            [<A href="../abstract/abstract11302.shtml">摘要</A>]
            <A href="../article/downloadArticleFile.do?attachType=PDF&amp;id=11302">PDF</A>
            <br>doi: 10.19595/j.cnki.1000-6753.tces.251879</TD></TR>
        </TABLE>
        '''
        items = CRAWLER.parse_toc_document(document, CRAWLER.JOURNALS["eb848c086da3fb6d"])
        self.assertEqual(1, len(items))
        item = items[0]
        self.assertEqual("11302", item["external_id"])
        self.assertEqual("局部脉冲强磁场驱动下的薄壁金属构件变形稳定性研究", item["title"])
        self.assertEqual(["徐巍", "赖智鹏", "李亮"], item["authors"])
        self.assertEqual(2026, item["year"])
        self.assertEqual("41", item["volume"])
        self.assertEqual("21", item["issue"])
        self.assertEqual("7161-7172", item["pages"])
        self.assertEqual(
            "https://dgjsxb.ces-transaction.com/CN/abstract/abstract11302.shtml",
            item["url"],
        )
        self.assertEqual("10.19595/j.cnki.1000-6753.tces.251879", item["doi"])
        self.assertIn("id=11302", item["pdf_url"])

    def test_legacy_j_zhaiyao_abstract(self):
        document = '''
        <table><tr>
          <td class="J_zhaiyao"><b>摘要</b>&nbsp;局部脉冲强磁场作用下薄壁金属构件的失稳振动
          是制约其成形精度的关键瓶颈。该文发现工件的结构刚度是主导变形行为稳定性的核心参数，
          并据此提出了预制锥形构件的形貌设计方法。</td>
          <td class="J_zhaiyao">服务</td>
        </tr></table>
        '''
        abstract = CRAWLER.extract_detail_abstract(document)
        self.assertIsNotNone(abstract)
        self.assertTrue(abstract.startswith("局部脉冲强磁场"))
        self.assertNotIn("摘要", abstract)
        self.assertNotIn("服务", abstract)

    def test_cma_variant_search_result(self):
        document = '''<div class="lunwen-liebiao"><div class="title">
          <a class="lunwen" href="https://zhkqyxyjzz.cma-cmc.com.cn/CN/10.3877/cma.j.issn.1674-1366.2026.05.001">测试标题</a>
          </div><div class="zuozhe">张三, 李四</div></div>'''
        item = CRAWLER.parse_search_result(document, CRAWLER.JOURNALS["lis"])[0]
        self.assertEqual("测试标题", item["title"])
        self.assertEqual("10.3877/cma.j.issn.1674-1366.2026.05.001", item["external_id"])
        self.assertEqual(["张三", "李四"], item["authors"])
        self.assertEqual(2026, item["year"])
        self.assertEqual("05", item["issue"])

    def test_unknown_search_markup_is_not_reported_as_successful_empty_page(self):
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_TEMPLATE"):
            CRAWLER.parse_search_result("<html><body>Another platform</body></html>", CRAWLER.JOURNALS["lis"])

    def test_current_issue_url_uses_cn_current(self):
        self.assertEqual(
            "https://www.lis.ac.cn/CN/current",
            CRAWLER.current_issue_url(CRAWLER.JOURNALS["lis"]),
        )

    def test_current_issue_url_prefers_explicit_url(self):
        row = {"journal_key": "d469e63f60674d38", "name": "管理学报",
               "url": "http://manu68.magtech.com.cn",
               "current_url": "https://manu68.magtech.com.cn/glxb/CN/current"}
        journal = CRAWLER.journal_from_catalog(row)
        self.assertEqual(
            "https://manu68.magtech.com.cn/glxb/CN/current",
            CRAWLER.current_issue_url(journal),
        )

    def test_latest_issue_ignores_query_and_limits_results(self):
        document = '''
        <li id="art9001" class="noselectrow">
          <div class="j-title-1"><a href="/CN/10.13266/new1">最新文章一</a></div>
          <div class="j-author">张三</div><span class="j-volumn">2026, 70(9): 1-10</span>
        </li>
        <li id="art9002" class="noselectrow">
          <div class="j-title-1"><a href="/CN/10.13266/new2">最新文章二</a></div>
          <div class="j-author">李四</div><span class="j-volumn">2026, 70(9): 11-20</span>
        </li>
        '''
        request = {
            "query": "不存在的关键词", "limit": 1, "aliases": [],
            "deadline_at": "2099-01-01T00:00:00Z",
            "parameters": {
                "journal_keys": ["lis"], "collect_mode": "latest_issue",
                "request_delay_ms": 0, "enrich_abstract": False,
            },
        }
        with patch.object(CRAWLER, "fetch_current_issue", return_value=document):
            items, warnings, successful = CRAWLER.collect(request)
        self.assertEqual(1, len(items))
        self.assertEqual("9001", items[0]["external_id"])
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)

    def test_manifest_exposes_collect_mode(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        mode = manifest["parameters_schema"]["properties"]["collect_mode"]
        self.assertEqual(["keywords", "latest_issue"], mode["enum"])
        self.assertEqual("keywords", mode["default"])

    def test_generic_toc_parses_cn_y_issue_links(self):
        journal = CRAWLER.Journal("k", "示例期刊", "https://example.cn", "/CN/home",
                                  current_url="https://example.cn/CN/current")
        page = '<a href="/CN/Y2026/V48/I5/1">真实文章标题示例文章</a>'
        items = CRAWLER.parse_generic_toc(page, journal)
        self.assertEqual(1, len(items))
        self.assertEqual("Y2026/V48/I5/1", items[0]["external_id"])

    def test_generic_toc_parses_cn_doi_links(self):
        journal = CRAWLER.Journal("k", "示例期刊", "https://example.cn", "/CN/home",
                                  current_url="https://example.cn/CN/current")
        page = '<a href="/CN/10.3969/j.issn.1001-1935.2026.05.001">耐火材料示例论文标题</a>'
        items = CRAWLER.parse_generic_toc(page, journal)
        self.assertEqual(1, len(items))
        self.assertEqual("10.3969/j.issn.1001-1935.2026.05.001", items[0]["external_id"])
        self.assertEqual("10.3969/j.issn.1001-1935.2026.05.001", items[0]["doi"])

    def test_generic_toc_parses_abstract_shtml_and_skips_cover_toc(self):
        journal = CRAWLER.Journal("k", "示例期刊", "https://example.cn", "/CN/home",
                                  current_url="https://example.cn/CN/current")
        page = (
            '<a href="abstract/abstract6502.shtml">胆固醇代谢重编程相关的示例文章</a>'
            '<a href="/CN/abstract/abstract6503.shtml">宿主代谢物驱动的免疫调控示例</a>'
            '<a href="/CN/Y2026/V47/I11/1">某刊2026年第11期封面和目次</a>'
        )
        items = CRAWLER.parse_generic_toc(page, journal)
        self.assertEqual(["6502", "6503"], [item["external_id"] for item in items])


CURRENT_PAGE_WITH_PAGER = '''
<html><head><title>2026年第10期</title></head><body>
<li id="art1001" class="noselectrow">
  <div class="j-title"><a href="/CN/10.13266/page1a">第一期文章甲标题示例</a></div>
  <div class="j-author">张三</div><span class="j-volumn">2026, 70(10): 1-10</span>
</li>
<li id="art1002" class="noselectrow">
  <div class="j-title"><a href="/CN/10.13266/page1b">第一期文章乙标题示例</a></div>
  <div class="j-author">李四</div><span class="j-volumn">2026, 70(10): 11-20</span>
</li>
<div class="paperPage_list">
  <a href="?page=1">1</a><a href="?page=2">下一页</a>
</div>
</body></html>
'''

CURRENT_PAGE_TWO = '''
<html><head><title>2026年第10期</title></head><body>
<li id="art1003" class="noselectrow">
  <div class="j-title"><a href="/CN/10.13266/page2a">第二期文章丙标题示例</a></div>
  <div class="j-author">王五</div><span class="j-volumn">2026, 70(10): 21-30</span>
</li>
</body></html>
'''


class LatestIssuePaginationTests(unittest.TestCase):
    def request(self, **parameters):
        payload = {
            "journal_keys": ["lis"], "collect_mode": "latest_issue",
            "request_delay_ms": 0, "enrich_abstract": False,
        }
        payload.update(parameters)
        return {
            "query": "不存在的关键词", "limit": 50, "aliases": [],
            "deadline_at": "2099-01-01T00:00:00Z", "parameters": payload,
        }

    def test_pager_pages_are_merged(self):
        fetched = []

        def fake_fetch(opener, journal, url, timeout=25):
            fetched.append(url)
            return CURRENT_PAGE_TWO

        with patch.object(CRAWLER, "fetch_current_issue", return_value=CURRENT_PAGE_WITH_PAGER), \
                patch.object(CRAWLER, "fetch_toc_page", side_effect=fake_fetch):
            items, warnings, successful = CRAWLER.collect(self.request(max_pages_per_journal=3))

        self.assertEqual(["1001", "1002", "1003"], [item["external_id"] for item in items])
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)
        self.assertEqual(1, len(fetched))
        self.assertIn("page=2", fetched[0])

    def test_no_pager_keeps_single_request(self):
        document = CURRENT_PAGE_WITH_PAGER.split('<div class="paperPage_list">')[0] + "</body></html>"
        fetched = []
        with patch.object(CRAWLER, "fetch_current_issue", return_value=document), \
                patch.object(CRAWLER, "fetch_toc_page", side_effect=lambda *a, **k: fetched.append(a) or ""):
            items, warnings, _ = CRAWLER.collect(self.request())
        self.assertEqual(2, len(items))
        self.assertEqual([], fetched)
        self.assertEqual([], warnings)

    def test_cross_issue_and_year_links_are_not_followed(self):
        document = '''
        <li id="art2001" class="noselectrow">
          <div class="j-title"><a href="/CN/10.13266/x1">当期唯一文章标题示例</a></div>
          <div class="j-author">张三</div><span class="j-volumn">2026, 70(10): 1-10</span>
        </li>
        <div class="paperPage_list">
          <a href="/CN/Y2025/V69/I9/2">2</a>
          <a href="?year_id=2025&amp;issue_id=9&amp;page=2">3</a>
          <a href="https://other.example.com/CN/current?page=2">4</a>
          <a href="#">5</a>
        </div>
        '''
        fetched = []
        with patch.object(CRAWLER, "fetch_current_issue", return_value=document), \
                patch.object(CRAWLER, "fetch_toc_page", side_effect=lambda *a, **k: fetched.append(a[2]) or ""):
            items, warnings, _ = CRAWLER.collect(self.request())
        self.assertEqual(1, len(items))
        self.assertEqual([], fetched)
        self.assertEqual([], warnings)

    def test_issue_marker_mismatch_stops_paging(self):
        entry = CURRENT_PAGE_WITH_PAGER.replace("2026年第10期", "2026年第10期")
        other_issue = CURRENT_PAGE_TWO.replace("2026年第10期", "2026年第8期")
        fetched = []
        with patch.object(CRAWLER, "fetch_current_issue", return_value=entry), \
                patch.object(CRAWLER, "fetch_toc_page", side_effect=lambda *a, **k: fetched.append(a[2]) or other_issue):
            items, warnings, _ = CRAWLER.collect(self.request())
        self.assertEqual(2, len(items))
        self.assertEqual(["ISSUE_MARKER_MISMATCH"], [w["code"] for w in warnings])

    def test_zero_new_items_stops_after_duplicate_page(self):
        fetched = []

        def fake_fetch(opener, journal, url, timeout=25):
            fetched.append(url)
            return CURRENT_PAGE_WITH_PAGER

        with patch.object(CRAWLER, "fetch_current_issue", return_value=CURRENT_PAGE_WITH_PAGER), \
                patch.object(CRAWLER, "fetch_toc_page", side_effect=fake_fetch):
            items, warnings, _ = CRAWLER.collect(self.request(max_pages_per_journal=5))
        self.assertEqual(2, len(items))
        self.assertEqual(1, len(fetched))
        self.assertEqual(["PAGINATION_STALLED"], [w["code"] for w in warnings])

    def test_page_cap_is_twenty(self):
        links = "".join(f'<a href="?page={number}">{number}</a>' for number in range(1, 31))
        document = CURRENT_PAGE_WITH_PAGER.split('<div class="paperPage_list">')[0] + links
        pages = CRAWLER.discover_pager_pages(document, "https://www.lis.ac.cn/CN/current", 20)
        self.assertEqual(19, len(pages))
        self.assertNotIn(21, pages)


class StaePaginationTests(unittest.TestCase):
    def make_payload(self, ids, total=None):
        return {"code": 200, "data": {"total": total, "data": [
            {"id": article_id, "titleCn": f"文章{article_id}", "abstractCn": "摘要内容"}
            for article_id in ids
        ]}}

    def test_page_size_and_page_num_loop_until_total(self):
        urls = []

        def fake_json(opener, url, timeout):
            urls.append(url)
            if "article/current" in url:
                return {"data": {"id": "issue1", "year": 2026, "issue": 10}}
            if "pageNum=1" in url:
                return self.make_payload(["a1", "a2"], total=3)
            return self.make_payload(["a3"], total=3)

        journal = CRAWLER.Journal("k", "化学进展", "https://hxjz.example.cn", "/CN/home", api_mode="stae")
        with patch.object(CRAWLER, "read_json_response", side_effect=fake_json):
            items = CRAWLER.fetch_stae_current(None, journal, warnings=[])
        self.assertEqual(3, len(items))
        self.assertIn("pageSize=200", urls[1])
        self.assertTrue(any("pageNum=2" in url for url in urls))

    def test_truncation_warning_when_count_equals_page_size(self):
        warnings = []

        def fake_json(opener, url, timeout):
            if "article/current" in url:
                return {"data": {"id": "issue1", "year": 2026, "issue": 10}}
            return {"data": {"data": [
                {"id": f"a{index}", "titleCn": f"文章{index}"} for index in range(200)
            ]}}

        journal = CRAWLER.Journal("k", "化学进展", "https://hxjz.example.cn", "/CN/home", api_mode="stae")
        with patch.object(CRAWLER, "read_json_response", side_effect=fake_json):
            items = CRAWLER.fetch_stae_current(None, journal, warnings=warnings)
        self.assertEqual(200, len(items))
        self.assertIn("STAE_PAGE_TRUNCATED", [warning["code"] for warning in warnings])


CMA_DETAIL = '''
<html><body><div id="myTabContent" class="tab-content">
  <div role="tabpanel" id="zhaiyao">
    <div class="abs-pic"><img src=""></div>
    <div class="zhaiyao">
      <div class="mag_zhaiyao_sec"><strong class="mag_zhaiyao_title">目的 </strong>
        <p class="mag_zhaiyao_p">比较两种评分系统对创伤性脑损伤患者预后的预测价值。</p></div>
      <div class="mag_zhaiyao_sec"><strong class="mag_zhaiyao_title">方法 </strong>
        <p class="mag_zhaiyao_p">回顾性纳入200例患者，采用多因素Logistic回归分析预后影响因素。</p></div>
      <div class="mag_zhaiyao_sec"><strong class="mag_zhaiyao_title">结果 </strong>
        <p class="mag_zhaiyao_p">NIRIS CT分级曲线下面积最大，特异性显著高于其他评分。</p></div>
    </div>
  </div>
  <div class="key-words"><strong>关键词: </strong><a href="#">脑损伤</a></div>
  <div class="en-abstract">Abstract Objective To compare the predictive value.</div>
</div></body></html>
'''

PANEL_DETAIL = '''
<html><body><div class="panel panel-default">
  <div class="panel-heading" role="tab" id="zhaiyao"><h4><a id="abstract">摘要/Abstract</a></h4></div>
  <div id="collapseOne" class="panel-collapse collapse">
    <div class="panel-body line-height text-justify">
      <p><strong>摘要： </strong>以氧化铝和氧化锆为原料制备复合耐火材料，研究了烧结温度对材料性能的影响。</p>
      <p>结果表明该材料在高温下具有优良的抗侵蚀性能，可用于高温工业窑炉内衬。</p>
    </div>
  </div>
  <div id="collapseTwo"><div class="panel-body"><p>参考文献占位</p></div></div>
</div></body></html>
'''


class AbstractEnrichmentTests(unittest.TestCase):
    def test_extract_cma_abstract_truncated_before_keywords(self):
        abstract = CRAWLER.extract_detail_abstract(CMA_DETAIL)
        self.assertTrue(abstract.startswith("目的"))
        self.assertIn("方法", abstract)
        self.assertNotIn("Abstract", abstract)
        self.assertNotIn("关键词", abstract)
        self.assertNotIn("Objective", abstract)

    def test_extract_panel_body_abstract_fallback(self):
        abstract = CRAWLER.extract_detail_abstract(PANEL_DETAIL)
        self.assertNotIn("摘要", abstract)
        self.assertIn("烧结温度", abstract)
        self.assertNotIn("参考文献", abstract)

    def test_extract_rejects_short_meta_only_pages(self):
        page = '<html><head><meta name="description" content="这是三十三字的搜索引擎描述，不能当摘要使用。"></head></html>'
        self.assertIsNone(CRAWLER.extract_detail_abstract(page))

    def test_enrich_only_fills_empty_abstracts_and_respects_limit(self):
        items = [
            {"external_id": "1", "url": "https://www.lis.ac.cn/CN/1", "abstract": "已有摘要"},
            {"external_id": "2", "url": "https://www.lis.ac.cn/CN/2", "abstract": None},
            {"external_id": "3", "url": "https://www.lis.ac.cn/CN/3", "abstract": "  "},
            {"external_id": "4", "url": "https://www.lis.ac.cn/CN/4", "abstract": None},
        ]
        warnings = []
        fetched = []

        def fake_fetch(opener, journal, url, timeout=25):
            fetched.append(url)
            if url.endswith("/4"):
                raise OSError("boom")
            return CMA_DETAIL

        journal = CRAWLER.JOURNALS["lis"]
        with patch.object(CRAWLER, "fetch_detail_page", side_effect=fake_fetch), \
                patch.object(CRAWLER.time, "sleep"):
            enriched = CRAWLER.enrich_abstracts(None, journal, items, 2, warnings)
        self.assertEqual(2, enriched)
        self.assertEqual("已有摘要", items[0]["abstract"])
        self.assertIsNotNone(items[1]["abstract"])
        self.assertIsNotNone(items[2]["abstract"])
        self.assertIsNone(items[3]["abstract"])
        self.assertEqual(["https://www.lis.ac.cn/CN/2", "https://www.lis.ac.cn/CN/3"], fetched)
        self.assertEqual(0, len(warnings))

    def test_enrich_failure_is_non_fatal_warning(self):
        items = [{"external_id": "9", "url": "https://www.lis.ac.cn/CN/9", "abstract": None}]
        warnings = []
        with patch.object(CRAWLER, "fetch_detail_page", side_effect=OSError("timeout")):
            enriched = CRAWLER.enrich_abstracts(None, CRAWLER.JOURNALS["lis"], items, 5, warnings)
        self.assertEqual(0, enriched)
        self.assertIsNone(items[0]["abstract"])
        self.assertEqual(["ABSTRACT_ENRICH_FAILED"], [warning["code"] for warning in warnings])

    def test_abstract_parameters_validation(self):
        self.assertEqual((True, 5), CRAWLER.abstract_parameters({}))
        self.assertEqual((False, 0), CRAWLER.abstract_parameters(
            {"enrich_abstract": False, "abstract_enrich_limit": 0}))
        self.assertEqual((True, 10), CRAWLER.abstract_parameters({"abstract_enrich_limit": 99}))
        self.assertEqual((True, 0), CRAWLER.abstract_parameters({"abstract_enrich_limit": -3}))
        with self.assertRaises(ValueError):
            CRAWLER.abstract_parameters({"abstract_enrich_limit": "abc"})

    def test_manifest_exposes_enrich_parameters(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        properties = manifest["parameters_schema"]["properties"]
        self.assertEqual("boolean", properties["enrich_abstract"]["type"])
        self.assertTrue(properties["enrich_abstract"]["default"])
        limit = properties["abstract_enrich_limit"]
        self.assertEqual("integer", limit["type"])
        self.assertEqual((0, 10), (limit["minimum"], limit["maximum"]))
        self.assertEqual(5, limit["default"])

    def test_collect_latest_issue_enriches_empty_abstracts_only(self):
        document = '''
        <li id="art3001" class="noselectrow">
          <div class="j-title"><a href="/CN/10.13266/e1">无摘要文章标题示例一</a></div>
          <div class="j-author">张三</div><span class="j-volumn">2026, 70(10): 1-10</span>
        </li>
        <li id="art3002" class="noselectrow">
          <div class="j-title"><a href="/CN/10.13266/e2">无摘要文章标题示例二</a></div>
          <div class="j-author">李四</div><span class="j-volumn">2026, 70(10): 11-20</span>
        </li>
        <li id="art3003" class="noselectrow">
          <div class="j-title"><a href="/CN/10.13266/e3">列表已有摘要文章标题三</a></div>
          <div class="j-author">王五</div><span class="j-volumn">2026, 70(10): 21-30</span>
          <div class="j-abstract">列表已带摘要，不应被覆盖。</div>
        </li>
        '''
        request = {
            "query": "", "limit": 10, "aliases": [],
            "deadline_at": "2099-01-01T00:00:00Z",
            "parameters": {
                "journal_keys": ["lis"], "collect_mode": "latest_issue",
                "request_delay_ms": 0, "enrich_abstract": True,
                "abstract_enrich_limit": 5,
            },
        }
        fetched = []

        def fake_detail(opener, journal, url, timeout=25):
            fetched.append(url)
            return CMA_DETAIL

        with patch.object(CRAWLER, "fetch_current_issue", return_value=document), \
                patch.object(CRAWLER, "fetch_detail_page", side_effect=fake_detail):
            items, warnings, _ = CRAWLER.collect(request)
        self.assertEqual(3, len(items))
        self.assertEqual(2, len(fetched))
        self.assertTrue(items[0]["abstract"].startswith("目的"))
        self.assertEqual("列表已带摘要，不应被覆盖。", items[2]["abstract"])
        self.assertEqual([], warnings)


    def test_repeated_site_ids_fall_back_to_doi(self):
        document = """
        <div id="art2" class="noselectrow">
          <a class="txt_biaoti" href="/CN/10.11923/j.issn.2095-4050.cjas2025-0158">第一篇测试文章标题</a>
          <span class="abs_njq">2026, 11(1): 1-10</span>
        </div>
        <div id="art2" class="noselectrow">
          <a class="txt_biaoti" href="/CN/10.11923/j.issn.2095-4050.cjas2025-0159">第二篇测试文章标题</a>
          <span class="abs_njq">2026, 11(1): 11-20</span>
        </div>
        """
        items = CRAWLER.parse_old_items(document, CRAWLER.JOURNALS["3591dbe91e051d14"])
        self.assertEqual(2, len(items))
        self.assertEqual(
            ["10.11923/j.issn.2095-4050.cjas2025-0158", "10.11923/j.issn.2095-4050.cjas2025-0159"],
            [item["external_id"] for item in items],
        )


    def test_generic_toc_parses_cn_doi_without_slash(self):
        document = """
        <a href="http://www.zgyydk.cn/CN/10.1009-0959.2026.110001">FDA 的 HALO 平台数据环境重构对我国药品智慧监管的启示</a>
        """
        items = CRAWLER.parse_generic_toc(document, CRAWLER.JOURNALS["59fcc5d489beb78a"])
        self.assertEqual(1, len(items))
        self.assertEqual("10.1009-0959.2026.110001", items[0]["external_id"])
        self.assertEqual("10.1009-0959.2026.110001", items[0]["doi"])


if __name__ == "__main__":
    unittest.main()
