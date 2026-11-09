# 通用 RSS 多源采集包

版本 1.0.0，Python 3.14，平台文件协议 1.0，分类 news。

使用开源 [feedparser](https://github.com/kurtmckee/feedparser) 6.0.14 解析 RSS/Atom，平台负责调度、结果表、任务关联和幂等入库。本包不连接数据库，不使用浏览器，不抓取文章详情网页，也不调用 AI。

## 配置

| 参数 | 默认 | 含义 |
| --- | --- | --- |
| feed_urls | 四个公开 RSS 地址 | 1 至 32 个 HTTP(S) 订阅地址，可自行增删 |
| match_mode | keywords | keywords 按主题匹配；all 保留全部条目 |
| extra_keywords | [] | 额外主题叫法，与 query、aliases 任意一项命中即可 |
| keyword_groups | [] | 每组内部全部命中，各组之间为 OR；与普通关键词也为 OR |
| per_feed_limit | 100 | 每个订阅最多输出的匹配条数 |
| timeout_seconds | 20 | 每个 HTTP 请求超时，秒 |
| max_feed_bytes | 5242880 | 单个订阅最大读取字节数 |
| lookback_days | 0 | 0 不限制日期；正数为最近若干天，显式 time_range.from 优先 |

平台请求的 limit 是本次所有来源的总上限。建议本次默认四个来源使用总上限 200；配置更多来源后相应提高。少量 RSS 条目不会因为上限提高而变成完整历史。

默认来源：IEEE Spectrum、Breaking Defense、Defense News、Naval News。来源数组在网页参数编辑器中以 JSON 输入，或者通过任务来源配置 API 设置。

匹配标题、订阅摘要以及订阅本身提供的 content；统一大小写、全半角和标点。英文使用词边界，避免 AI 匹配到其他单词中。不会自动翻译，中文关键词要通过 extra_keywords 或 aliases 添加英文叫法。没有使用排除词、相关性硬阈值或全文下载。

具身智能的任务级参数示例：

```json
{
  "extra_keywords": ["embodied AI", "embodied intelligence", "humanoid", "robotics", "vision language action"],
  "keyword_groups": [["robot", "AI"]]
}
```

军事智能体的任务级参数示例：

```json
{
  "extra_keywords": ["military AI agents", "military artificial intelligence"],
  "keyword_groups": [["AI", "military"], ["AI", "defense"], ["autonomous", "military"], ["agents", "defence"]]
}
```

这些是高召回探索配置，特别是 robotics、AI + defense 会包含相关但并非严格同义的文章；正文背景、通讯推荐段落也可能导致命中。应在周报分析阶段进一步排序，不能把所有命中都称为“具身智能/军事智能体成果”。测试报告另列核心词命中数，但核心词命中也不是语义准确性的保证。两个主题使用各自的任务配置，不把全部扩展词混入全局默认值。

## 输出与身份

输出标题、链接、摘要、订阅提供的内容、作者、发布者、发布时间、更新时间、语言、站点和订阅地址。`content_scope` 为 feed_content、feed_summary 或 title_only，不表示已经获得完整文章。

以规范化文章 URL 的 SHA-256 为 external_id，联合 source_site 去重；移除 URL fragment 与常见 utm/fbclid/gclid 跟踪参数，保留其他业务参数。同一篇文章在多个任务中保持相同身份；query、匹配词和采集时间不参与身份，也不写入原始内容字段。相同 URL 出现在多个订阅时本次保留一条，feed_url 记录最先遇到的订阅。

单源失败时保留其他来源的数据，结果为 partial；所有来源失败时 failed 并返回非零退出码。各源 scanned/matched/retained 数量写入 warnings 中的 FEED_STATS。截断、无日期和坏条目均有独立提示；正常没有关键词命中也是 completed，不伪造数据。

## 每日监控限制

本包声明 incremental=false，每次重新读取订阅当前内容，返回空游标，由平台幂等入库。不会将易变 RSS 列表的页码当作第二天进度，不会启用无限续采。时间窗口为左闭右开；没有日期的匹配条目仍保留并提示，以保证召回。

建议每天执行，每周读取已经入库的记录汇总。RSS 是滚动窗口，不保证不漏收；高频发布且窗口很短的来源应增加采集频率或选择其他授权接口。当前平台的调度时区和崩溃恢复仍有待修复，安装本包不代表上述平台缺口已经解决。

## 导入和本地运行

本包不会自行导入或创建监控。导入源目录：

```powershell
.\.venv\Scripts\python.exe -X utf8 platform_main.py import crawler_packages\news\rss_multi_feed
```

也可以将生成的 `packages_ready_to_import/news/rss_multi_feed-1.0.0.zip` 上传到平台来源页面。导入后平台自动建立该包独立结果表，不修改其他包的结果表。

独立运行：在 Python 3.14 虚拟环境安装 requirements.lock，然后执行：

```powershell
python crawler.py --request tests/request.json --output output
python -m unittest discover -s tests -v
```

仓库根目录的 `scripts/test_rss_multi_feed.py` 可以缓存一次真实抓取，再对两个主题分别进行离线匹配。外部来源不会因此按主题重复请求。`scripts/validate_rss_probe.py` 使用平台实际协议校验测试输出，不写数据库。

只配置可信、公开的 RSS 地址。这里的 URL 校验不是完整的网络安全沙箱；服务器的出站访问限制仍应由平台部署层负责。内容使用与再分发权限由各发布者决定，开源解析库的许可不授予文章版权。

