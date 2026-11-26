PACKAGE_HELP = {
    "custom_toc_journals": "逐本期刊单独适配的当期目录包。适合官网能看到最新一期目录、但没有统一搜索接口的期刊；只能抓当期并在本期里筛关键词，不能搜历史。",
    "magetech_journals": "玛格泰克平台的期刊包。支持用关键词让期刊网站搜索（范围由站点决定），也能抓最新一期；作者、摘要、DOI 通常较全。",
    "cnki_cbpt": "知网 CBPT/腾云公开门户期刊包。支持关键词检索和当期目录；是期刊的公开门户，不等同于知网付费数据库全库检索。",
    "qinyun_journals": "勤云平台期刊包。支持关键词检索和当期目录；部分期刊只有当期。",
    "rhzh_journals": "仁和汇智平台期刊包。支持关键词检索和当期目录。",
    "sancai_journals": "西安三才平台期刊包。支持关键词检索和当期目录。",
    "flagship_journals": "外文重点期刊元数据包。只按关键词检索 Nature、Science、PNAS、Cell 的公开元数据，不提供当期目录，也不下载全文。",
    "supplement_journals": "补充期刊包。数据来自 OpenAlex/Crossref 元数据，不是期刊官网页面；适合按关键词补外文文献，但要注意来源不是官网。",
    "paperonce_journals": "PaperOnce 平台期刊包。通过公开 API 抓当期文章；只能抓当期并在本期里筛关键词。",
    "founder_journals": "北大方正 rc-pub 平台期刊包。通过公开 API 抓当期文章；只能抓当期并在本期里筛关键词。",
    "oa_rss_journals": "高校期刊官网 RSS 订阅包。RSS 通常只含最新一期或最近文章；只能筛订阅内容，不能补历史。",
    "vsb_journals": "高校 VSB 网站期刊包。读取官网当期目录 HTML；只能抓当期并在本期里筛关键词。",
    "hep_mirror_journals": "HEP 公开镜像备用包。期刊官网打不开时，从中国高校科技期刊集群的公开镜像读取当期目录；不是期刊官网，只能筛镜像当期。",
    "baidu_baike": "百度百科查询包。按词条名称获取百科摘要/正文，适合查概念，不适合新闻监测。",
    "wikipedia": "维基百科查询包。按主题查中英文词条，不是新闻源。",
    "google_news_rss": "谷歌新闻 RSS 包。按关键词检索近期新闻；结果随新闻更新滚动，不是历史全量。",
    "sina_news": "新浪新闻关键词检索包。",
    "rss_multi_feed": "多 RSS 源 + 本地关键词匹配；不是网站全库搜索。",
    "uspto_number_lookup": "只按已知美国专利号查询，不能按主题词搜。",
    "books_to_scrape": "演示用书目站点采集，不支持主题检索。",
}


def help_for(package_key):
    return PACKAGE_HELP.get(str(package_key or ""), "")


PACKAGE_DATA = {
    "magetech_journals": {
        "meta_tag": "JSON/HTML·摘要+DOI", "meta_help": "可获取标题、作者、摘要、DOI、年卷期页。",
        "pdf_tag": "PDF链接", "pdf_help": "保存 pdf_url 下载链接，不下载 PDF 文件。",
    },
    "founder_journals": {
        "meta_tag": "JSON·摘要+DOI", "meta_help": "方正 rc-pub JSON API：标题、作者、摘要、DOI、年/期/页。",
        "pdf_tag": "无PDF", "pdf_help": "当前不提取、不下载 PDF。",
    },
    "paperonce_journals": {
        "meta_tag": "JSON·摘要+DOI", "meta_help": "PaperOnce JSON API：标题、作者、摘要、DOI、年/期。",
        "pdf_tag": "无PDF", "pdf_help": "当前不提取、不下载 PDF。",
    },
    "qinyun_journals": {
        "meta_tag": "HTML/JSON·摘要+DOI", "meta_help": "标题、作者、摘要（模板差异）、DOI、年份。",
        "pdf_tag": "无PDF", "pdf_help": "当前不提取、不下载 PDF。",
    },
    "rhzh_journals": {
        "meta_tag": "HTML/JSON·摘要+DOI", "meta_help": "标题、作者、摘要、DOI、年份。",
        "pdf_tag": "无PDF", "pdf_help": "当前不提取、不下载 PDF。",
    },
    "sancai_journals": {
        "meta_tag": "HTML/JSON·摘要+DOI", "meta_help": "标题、作者、摘要、DOI、年份。",
        "pdf_tag": "无PDF", "pdf_help": "当前不提取、不下载 PDF。",
    },
    "cnki_cbpt": {
        "meta_tag": "HTML·摘要(无DOI)", "meta_help": "CBPT 公开门户：标题、作者、摘要、期次；没有 DOI 字段。",
        "pdf_tag": "无PDF", "pdf_help": "当前不提取、不下载 PDF。",
    },
    "custom_toc_journals": {
        "meta_tag": "HTML/JSON·标题+链接", "meta_help": "普通 HTML 多为标题+文章链接；JSON 类可能有作者/DOI/期次，摘要通常没有。",
        "pdf_tag": "无PDF", "pdf_help": "当前不提取、不下载 PDF。",
    },
    "vsb_journals": {
        "meta_tag": "HTML·标题+链接", "meta_help": "只有标题和文章链接，没有摘要/作者/DOI。",
        "pdf_tag": "无PDF", "pdf_help": "当前不提取、不下载 PDF。",
    },
    "hep_mirror_journals": {
        "meta_tag": "HTML·标题+链接", "meta_help": "只有标题和文章链接，没有摘要/作者/DOI。",
        "pdf_tag": "无PDF", "pdf_help": "当前不提取、不下载 PDF。",
    },
    "oa_rss_journals": {
        "meta_tag": "RSS·摘要", "meta_help": "RSS 通常含标题、作者、摘要、年/期；DOI 视 RSS 而定。",
        "pdf_tag": "无PDF", "pdf_help": "当前不提取、不下载 PDF。",
    },
    "supplement_journals": {
        "meta_tag": "OpenAlex·摘要+DOI", "meta_help": "标题、作者、单位、摘要、DOI、年卷期页、OA/被引；不是官网页面。",
        "pdf_tag": "无PDF", "pdf_help": "元数据源，不含 PDF。",
    },
    "flagship_journals": {
        "meta_tag": "OpenAlex·摘要+DOI", "meta_help": "标题、作者、单位、摘要、DOI、年卷期页、OA/被引。",
        "pdf_tag": "无PDF", "pdf_help": "元数据源，不含 PDF。",
    },
    "baidu_baike": {
        "meta_tag": "HTML·摘要", "meta_help": "词条摘要和正文。",
        "pdf_tag": "无PDF", "pdf_help": "不涉及 PDF。",
    },
    "wikipedia": {
        "meta_tag": "HTML·摘要", "meta_help": "词条摘要和正文。",
        "pdf_tag": "无PDF", "pdf_help": "不涉及 PDF。",
    },
    "google_news_rss": {
        "meta_tag": "RSS·标题+摘要", "meta_help": "新闻标题、链接和摘要。",
        "pdf_tag": "无PDF", "pdf_help": "不涉及 PDF。",
    },
    "sina_news": {
        "meta_tag": "HTML·标题+摘要", "meta_help": "新闻标题、链接和摘要。",
        "pdf_tag": "无PDF", "pdf_help": "不涉及 PDF。",
    },
    "rss_multi_feed": {
        "meta_tag": "RSS·标题+摘要", "meta_help": "RSS 标题、链接和摘要。",
        "pdf_tag": "无PDF", "pdf_help": "不涉及 PDF。",
    },
    "uspto_number_lookup": {
        "meta_tag": "JSON·专利元数据", "meta_help": "按专利号查询公开元数据。",
        "pdf_tag": "无PDF", "pdf_help": "不涉及 PDF。",
    },
    "books_to_scrape": {
        "meta_tag": "HTML·书目", "meta_help": "演示书目元数据。",
        "pdf_tag": "无PDF", "pdf_help": "不涉及 PDF。",
    },
}


def data_profile(package_key):
    return PACKAGE_DATA.get(str(package_key or ""), {})