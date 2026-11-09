# 通用 RSS 来源扩充记录

日期：2026-10-13。此次扩充使用现有 `rss_multi_feed` 1.0.0 的配置接口，没有更换插件、修改已安装文件摘要、增加结果表或启用定时调度。

## 1. 扩充方式

- 原先 4 个订阅地址扩充到 32 个，原有 IEEE Spectrum、Breaking Defense、Defense News、Naval News 全部保留。
- 32 是现有协议允许的地址数上限，表示 32 个频道，不代表 32 家不同媒体。
- 扩充配置保存为 `configs/rss-multi-feed-expanded.json`，可通过默认配置接口应用，不需要重新导入 ZIP。
- 每个订阅的输出上限调整为 1,000；三个手动验收任务的总上限调整为 10,000。此次快照没有因这些上限发生截断。
- 保留 `lookback_days=0`，不额外限制历史日期；保留每次请求 20 秒超时和 5 MiB 读取上限。
- 同步更新监控任务 6、7、8 的 RSS 配置，分别对应整站样本、具身智能、军事智能体。两个主题的 query、aliases、扩展词和组合词均保持不变。
- 其他任务和插件不变；三个验收任务仍为 `manual`，没有启动 Scheduler 或生成 AI 周报。

包的清单仍保留四地址基础默认值。部署后的默认配置存在数据库中，任务还各自保存配置覆盖值。因此，修改采集源默认配置不会自动覆盖已经创建的任务；本次明确同步了上述三个验收任务。

## 2. 启用来源

下表为扩充前逐源探测的快照条数，不是每日产量。正式执行期间条数可能因来源更新而变化，跨频道的同一 URL 会在本包内去重。

| 分类 | 名称 | 快照条数 | RSS 地址 |
| --- | --- | ---: | --- |
| 科技 | IEEE Spectrum | 30 | https://spectrum.ieee.org/feeds/feed.rss |
| 防务 | Breaking Defense | 30 | https://breakingdefense.com/full-rss-feed/ |
| 防务 | Defense News | 25 | https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml |
| 防务 | Naval News | 10 | https://www.navalnews.com/feed/ |
| 中文综合 | 中新网即时新闻 | 30 | https://www.chinanews.com.cn/rss/scroll-news.xml |
| 中文综合 | 中新网国际新闻 | 30 | https://www.chinanews.com.cn/rss/world.xml |
| 中文综合 | 中新网时政新闻 | 30 | https://www.chinanews.com.cn/rss/china.xml |
| 中文综合 | 中新网财经新闻 | 30 | https://www.chinanews.com.cn/rss/finance.xml |
| 中文科技 | IT之家 | 60 | https://www.ithome.com/rss/ |
| 中文科技 | Solidot | 20 | https://www.solidot.org/index.rss |
| 国际综合 | BBC World | 36 | https://feeds.bbci.co.uk/news/world/rss.xml |
| 科技 | BBC Technology | 21 | https://feeds.bbci.co.uk/news/technology/rss.xml |
| 中文综合 | DW 中文 | 60 | https://rss.dw.com/xml/rss-chi-all |
| 中文综合 | 联合国新闻中文 | 30 | https://news.un.org/feed/subscribe/zh/news/all/rss.xml |
| 聚合 | Google 新闻中文头条 | 26 | https://news.google.com/rss?hl=zh-CN&gl=CN&ceid=CN:zh-Hans |
| 国际综合 | NPR Top Stories | 10 | https://feeds.npr.org/1001/rss.xml |
| AI / 机器人 | MIT AI | 50 | https://news.mit.edu/rss/topic/artificial-intelligence2 |
| AI / 机器人 | MIT Robotics | 50 | https://news.mit.edu/topic/mitrobotics-rss.xml |
| AI / 机器人 | The Robot Report | 15 | https://www.therobotreport.com/feed/ |
| AI / 机器人 | Robohub | 75 | https://robohub.org/feed/ |
| AI / 机器人 | NVIDIA Blog | 18 | https://blogs.nvidia.com/feed/ |
| AI / 机器人 | Google AI Blog | 20 | https://blog.google/technology/ai/rss/ |
| AI / 机器人 | Hugging Face Blog | 876 | https://huggingface.co/blog/feed.xml |
| AI / 机器人 | Microsoft Research | 10 | https://www.microsoft.com/en-us/research/feed/ |
| 科技 | TechCrunch | 20 | https://techcrunch.com/feed/ |
| 科技 | Ars Technica | 20 | https://feeds.arstechnica.com/arstechnica/index |
| AI / 机器人 | TechXplore Robotics | 30 | https://techxplore.com/rss-feed/robotics-news/ |
| 防务 | The War Zone | 31 | https://www.twz.com/feed/ |
| 防务 | Defense One | 19 | https://www.defenseone.com/rss/all/ |
| 防务 | DefenseScoop | 10 | https://defensescoop.com/feed/ |
| 防务 | C4ISRNET | 25 | https://www.c4isrnet.com/arc/outboundfeeds/rss/?outputType=xml |
| 防务 / 科技 | The Debrief | 100 | https://thedebrief.org/feed/ |

中新网地址来自[官方订阅目录](https://www.chinanews.com.cn/rss/)，MIT 地址来自[官方 RSS 目录](https://news.mit.edu/rss)。其他来源也使用发布者自己的订阅地址，不依赖第三方公共 RSSHub 实例。

## 3. 候选与排除记录

逐个低频检查 48 个候选地址，其中 41 个在本次检查中能够解析、有有效记录，且最新可解析日期距检查时间不超过 45 天。选择上述 32 个，另外 9 个保留为技术可用备选，不自动启用：

| 备选 | 地址 |
| --- | --- |
| Google 新闻英文头条 | https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en |
| NPR Technology | https://feeds.npr.org/1019/rss.xml |
| The Verge | https://www.theverge.com/rss/index.xml |
| WIRED | https://www.wired.com/feed/rss |
| Nature | https://www.nature.com/nature.rss |
| Phys.org | https://phys.org/rss-feed/ |
| Army Technology | https://www.army-technology.com/feed/ |
| Airforce Technology | https://www.airforce-technology.com/feed/ |
| MIT Security Studies | https://news.mit.edu/rss/topic/security-studies |

未通过或有明确限制的来源：

- 人民网旧地址 `https://www.people.com.cn/rss/ywkx.xml`：可解析，但最新可解析日期仍为 2016-04-05，未启用。
- China Daily 的 `china_rss.xml`、`world_rss.xml`、`bizchina_rss.xml` 三个旧地址：此次返回 404；不代表该媒体所有可能的 RSS 都不可用。
- `https://36kr.com/feed`：此次返回的内容不是可识别 RSS/Atom，未启用。
- RFI 中文 `https://www.rfi.fr/cn/rss`：本机此次发生 SSL 连接错误，未启用；未绕过访问限制或关闭证书验证。
- MIT 原先尝试的 `/rss/topic/robotics` 返回 404，已从官方目录找到并验证 `/topic/mitrobotics-rss.xml`，使用更正后的地址。
- ScienceDaily：[使用条款](https://www.sciencedaily.com/terms.htm)明确要求数据库保存前取得书面同意，本次没有请求或入库其内容。
- Guardian：[官方说明](https://www.theguardian.com/help/feeds)限定个人非商业用途，暂不纳入企业数据服务的默认列表。

“技术可用”不等于已经获得商业授权。其他来源的商用、数据库存储及再分发权限没有在本次完成全面审查；当前手动测试不应被作为商业上线授权依据。

## 4. 验证与证据

扩充前所有 feed 在来源探测中各读取一次；补验的两个 MIT 官方地址另各读取一次。两个主题的离线验证复用同一快照，没有再次按关键词请求外站。

| 离线模式 | 去重后记录 | 核心主题词命中 | 平台拒收 |
| --- | ---: | ---: | ---: |
| 整站样本 | 1,826 | 不适用 | 0 |
| 具身智能，原有宽松配置 | 176 | 16 | 0 |
| 军事智能体，原有宽松配置 | 71 | 0 | 0 |

这里“核心主题词”只计算原任务 query 与 aliases，不包括额外扩展词或组合词。候选数不等于经过人工或 AI 核验的相关报道数。Hugging Face 等订阅保留较多历史条目，上表不是当日新增量。

四个中新网订阅在现有插件的解析方式下有可恢复的解析提示，但标题、链接及日期仍可正常输出；没有因此丢弃全部记录。没有访问详情页，不保证 RSS 中的内容就是完整正文。

测试：52 项平台测试、22 项采集包测试通过；新增测试验证扩充配置符合现有清单协议、32 地址唯一、原有四地址保留、资源上限合法。

证据目录：`crawler_platform_runtime/probes/rss-expansion-20261013/`。

- `availability.json`：每个候选地址的格式、有效条数、最新日期、耗时和失败原因。
- `feed-snapshot.json`：通过来源探测的订阅快照。
- `before.json`：变更前的默认配置与三个任务设置。
- `all/`、`embodied/`、`military/`：离线协议请求与输出。
- `offline-summary.json`：离线统计与匹配数量。
- `platform-acceptance.json`：默认配置更新、任务配置及正式执行记录。

## 5. 使用边界

1. 当前仍是手动采集，没有启用每日任务，也没有实现每周 AI 汇总。
2. 持续监控不应把当前样本数当成每日产量。短列表可能每天刷新多次，之后应按来源窗口长度安排采集频率。
3. 包内按规范化文章 URL 去重；Google 新闻包装链接与媒体原始链接并不一定能合并，跨 URL 的语义去重不在本次范围内。
4. 初次补入的历史文章需要按文章发布时间判断是否属于某周，不能直接把入库时间作为周报时间范围。
5. 无原生 RSS 的网站留待 RSSHub 路由单独验证，本次没有部署 RSSHub 或引入其公共实例依赖。
6. 包版本、结果表与数据库结构保持不变。后续若要超过 32 个地址，需要增加任务拆分或升级协议约束，不能直接向当前数组塞入更多地址。

## 6. 正式运行验收

通过默认配置与任务来源设置 API 应用配置，再通过持久队列和 Worker 实际执行。不是仅运行离线解析脚本。

| 运行 ID | 监控 ID | 测试 | 状态 | 获取 | 新增 | 更新 | 未变化 | 拒收 |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 22 | 6 | 扩充后的整站样本 | completed | 1,829 | 1,734 | 0 | 95 | 0 |
| 23 | 6 | 重复采集 | completed | 1,829 | 0 | 3 | 1,826 | 0 |
| 24 | 7 | 具身智能 | completed | 176 | 0 | 3 | 173 | 0 |
| 25 | 8 | 军事智能体 | completed | 71 | 0 | 0 | 71 | 0 |

四次插件进程均正常退出，退出码为 0；每次结果都有 32 条来源统计，没有 `FEED_FAILED`、`ITEM_LIMIT`、`PER_FEED_LIMIT` 或提前触及执行期限的提示。

MySQL 与 API 核验结果：

- 仍使用包 ID 7 和结果表 `pkg_data_000007`，版本 1.0.0、安装摘要均未改变。
- 数据表记录数、唯一身份数、唯一 URL 数均为 1,829，未生成重复文章行。
- 三个任务的数据预览数量分别为 1,829、176、71，与数据库关联统计一致。
- 两个主题交集为 21 条；文章只存一份，分别关联任务。
- 原有关键词与别名保持不变，任务均仍为手动模式；检查时没有遗留排队或运行中的采集任务。
- 当前默认配置与三个任务配置均包含 32 个地址；任务总上限为 10,000。

重复采集出现的 3 条更新来自 Microsoft Research 订阅的 `content` 字段变化，不是新增重复记录。随后主题采集的 3 条更新中，1 条是该来源的内容变化，2 条是同一 MIT 文章同时出现在 AI 与 Robotics 频道，当前包所选 `publisher`、`feed_url` 发生变化。身份保持稳定，但单值频道溯源仍有轻微更新噪声，留待后续协议升级时优化，没有为了此次扩充改动已安装包。

查看入口：

- 默认配置：`http://127.0.0.1:8090/sources`，选择通用 RSS 多源采集的默认配置。
- 全量数据：`http://127.0.0.1:8090/data?source=rss_multi_feed`。
- 具身智能：`http://127.0.0.1:8090/data?source=rss_multi_feed&monitor=7`。
- 军事智能体：`http://127.0.0.1:8090/data?source=rss_multi_feed&monitor=8`。
- 运行详情：`http://127.0.0.1:8090/runs/22` 至 `/runs/25`。

完整运行统计、逐源结果、运行目录、日志路径、字段变化与数据库核验保存在 `platform-acceptance.json`。每次运行目录的 `output/result.json` 包含来源统计，`output/items.jsonl` 包含输出记录；成功时 `process.log` 可能为空。
