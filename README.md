# 爬虫工具包管理与执行平台

当前建设主线是一个独立的爬虫工具包平台。第三方开发者按协议提交目录，平台负责验证、为每个包建立独立结果表、创建关键词任务、定时启动独立进程、去重入库并提供查询 API。新工具包不继承平台类，也不能直接连接数据库。

最新进度与待办统一见 [当前进度](docs/current-progress.md)（更新于 2026-11-09），其中区分已上线、已验收、已知缺陷和仅有视觉稿的设计。

## 大模型辅助建任务

侧边栏“大模型辅助”使用 DeepSeek 将对话整理成新任务草案。填写采集主题、来源范围、北京时间执行时刻和数量要求后，可在右侧调整关键词、别名、每源上限和插件参数，再点击“检查配置”和“确认创建”。只有确认对话框中的“创建任务”会写入现有任务表；模型不能修改旧任务、运行命令或直接启动采集。

服务器 `.env` 配置 `DEEPSEEK_API_KEY`，可用 `DEEPSEEK_ASSISTANT_MODEL` 指定模型（默认 `deepseek-flash`），修改后重启 API。对话内容会发送到 DeepSeek，不要填写密码或密钥。首版会话只保存在当前页面内存，刷新或新对话会清空，不增加数据库表；已创建的任务不受影响。模型不可用时，已有任务与手动配置仍可正常使用。

插件能力目录位于 [configs/assistant-source-profiles.json](configs/assistant-source-profiles.json)，区分 `keyword`、`feed`、`identifier`、`site`。新导入但未登记能力的包不会被 AI 自动选择；登记后仍按包内 `parameters_schema` 校验。带敏感参数名的包暂不开放给助手。大期刊目录不会全部发送给模型，精确选刊可在草案的来源参数中使用期刊选择器。确认凭据有效期 15 分钟；改参数、更新插件或重启 API 后需重新检查。

接口为 `GET /api/v1/assistant/catalog`、`POST /api/v1/assistant/chat`、`POST /api/v1/assistant/preview`、`POST /api/v1/assistant/monitors`。最后一个接口要求 `confirmed: true` 和预览返回的 `confirmation_token`，创建前重新校验；每日/每周任务仍由现有 Scheduler/Worker 执行。模型请求最多 20 条消息、24000 字符、4000 输出 token，60 秒超时，同时最多处理两条对话请求。对外部署时需启用平台鉴权或反向代理访问控制，不能将可消耗 API 额度的接口无保护地暴露到公网。

## 当前状态

- 已实现工具包清单、参数、结果和输出结构协议。
- 当前源码含十张固定平台表（含版本记录表），以及“每个工具包一张结果表”的自动建表机制。
- 已实现独立环境、进程执行、持久队列、任务关联、游标和结果查询。
- 已提供百度百科、Wikipedia、Google 新闻 RSS 等可独立导入的示例工具包。
- 通用 RSS/Atom 多地址采集包 [`rss_multi_feed`](crawler_packages/news/rss_multi_feed/README.md) 已在本机导入并实测，支持主题叫法、关键词组和整站订阅；新部署仍需手动导入，源码本身不会自动创建监控。关键词组与主词并列 OR 的限制见当前进度。
- 期刊工作簿已按模板/供应商整理为 [分类目录](docs/journal-template-classification.md)；候选站点的 [逐站验收结果](docs/journal-audit-2026-10-23.md) 已归档。当前 CBPT 包仅保留 509 家、玛格泰克包仅保留 98 家可选期刊；[清理口径](docs/journal-catalog-pruning-2026-10-30.md) 记录了筛选依据，新部署需手动导入。
- 勤云、仁和汇智、西安三才三个独立期刊包已完成 [630 家逐刊测试](docs/supplier-journal-audit-2026-10-26.md)，将通过筛选的 104、122、1 家纳入目录；2026-11-06 平台验收已确认这三个包与玛格泰克、CBPT 均已安装。目录数不是当日全源可用性保证。
- DeepSeek [情报周报](docs/weekly-intelligence-reports.md) 已接入：按任务选择性启用，周一北京时间 10:00 汇总上周新增匹配，保存可追溯证据与模型输出。具身智能、军事智能体两项任务已完成真实报告验收。
- 任务归档/恢复、活跃名称唯一约束和十页分组/输入跳页已上线。助手七场景验收为五项完整、两项部分满足，见 [验收报告](reports/assistant-evaluation-20261106-224559.md)。
- Google 新闻 RSS 已于 2026-11-08 升级到 `1.0.3`，补齐主词与别名分别检索、合并去重及全局上限；[实网记录](reports/google-news-rss-aliases-20261108-115859.json)。助手 UI 新视觉稿、标签式别名和统一布尔检索计划尚未落地。

### 平台代理池

运行一次 `python platform_main.py init-db` 应用代理池迁移；已有采集数据不会清除。随后在管理界面的“代理池”页添加 `http://主机:端口` 节点并启用。没有启用节点时，采集包沿用原有网络设置；有启用节点时，Worker 在每次包运行前轮换分配一个节点，失败重试会重新分配。运行详情显示所用节点名称，已排队但尚未开始的运行也会读取最新设置，无需重新创建监控任务。

代理地址仅支持不含账号密码的 HTTP 代理（HTTPS 目标通过 CONNECT）；节点分配通过 `HTTP_PROXY`、`HTTPS_PROXY` 及小写形式传给子进程。内置包使用的 Python `urllib` 会读取这些变量；第三方包应使用尊重标准代理环境变量的 HTTP 客户端，不得自行覆盖代理或使用浏览器直连。平台不做透明的网络拦截，不能强制不遵守约定的包走代理。页面“检查连接”只验证代理端口可连接，不代表目标网站可访问。节点暂时不自动根据网站返回的错误停用，以免把解析失败误判为代理故障。已经分配过的节点地址不能修改；需要换地址时停用旧节点并新增一个，以保留运行审计。停用所有节点可恢复原有网络设置。
- RSS 包的开源选型、真实来源与两主题测试结果见 [RSS 实测记录](docs/rss-multi-feed-evaluation-2026-10-13.md)。
- 已提供 [32 地址扩充配置](configs/rss-multi-feed-expanded.json)；来源选择、排除原因和正式运行结果见 [RSS 扩充记录](docs/rss-source-expansion-2026-10-13.md)。该配置通过默认配置 API 保存，不改变已安装包的版本或摘要；已有任务需同步更新自己的来源配置。
- 默认使用独立数据库 `crawler_platform` 和 API 端口 `8090`。

## 快速启动

```powershell
.\.venv\Scripts\python.exe -X utf8 platform_main.py init-db
.\.venv\Scripts\python.exe -X utf8 platform_main.py import crawler_packages\reference\baidu_baike
.\.venv\Scripts\python.exe -X utf8 platform_main.py import crawler_packages\reference\wikipedia
.\.venv\Scripts\python.exe -X utf8 platform_main.py import crawler_packages\news\google_news_rss
```

执行 `启动平台.bat` 后，API 地址为 `http://127.0.0.1:8090`。详细命令见 `docs/crawler-platform-quickstart.md`。

## 核心目录

工具包按 `news`、`academic`、`patents`、`reference`、`entities`、`community` 六类组织，源码目录为 `crawler_packages/<category>/<package_key>/`，安装目录为 `packages/<category>/<package_key>/<version>/<digest>/`。分类不改变包标识和结果表。目录、兼容规则和迁移命令见 [爬虫包分类规范](docs/package-categories.md)。

- `crawler_platform`：全新平台的协议、存储、导入、执行、调度和 API。
- `crawler_packages`：可独立导入的示例工具包。
- `protocol/v1`：机器可读协议 Schema。
- `docs/crawler-platform-technical-spec-v1.md`：技术实施规范。
- `tests_platform`：新平台契约测试。

## 开发采集插件（工具包）

插件不需要继承平台类。平台将一个目录作为一个工具包导入，为它创建独立的结果表和 Python 虚拟环境；每次执行时传入请求文件路径，读取插件写出的结果文件。建议先阅读可运行的 [`crawler_packages/news/google_news_rss`](crawler_packages/news/google_news_rss)（无增量 RSS）或 [`crawler_packages/reference/baidu_baike`](crawler_packages/reference/baidu_baike)（百科条目）。本节以当前代码为准；完整规则见 [`docs/crawler-platform-technical-spec-v1.md`](docs/crawler-platform-technical-spec-v1.md)。

### 1. 准备目录

```text
my_source/
  manifest.json       # 身份、运行时、参数和输出字段声明
  crawler.py           # Python 入口脚本
  requirements.lock    # pip 依赖；仅用标准库时也要保留空文件
  README.md            # 来源、参数、限制和使用说明
  tests/
    request.json       # 推荐：与清单身份和版本一致的本地测试请求
    items.jsonl        # 推荐：一条合法输出样例
    result.json        # 推荐：对应的结果样例
```

导入器必须能找到清单、入口脚本、依赖文件和 README。`package_key` 是稳定的包身份，匹配 `^[a-z][a-z0-9_]{2,63}$`；`package_version` 使用三段数字（如 `1.0.0`）。同一身份和版本修改文件后不能覆盖导入，须提高版本号。当前平台使用 Python 3.14；清单声明的 `runtime.python_version` 必须与**运行平台的解释器 major.minor 完全一致**，不是只要语法兼容即可。

多期刊包可附带 `journals.json` 作为界面选择目录，每条至少提供 `journal_key` 和 `name`；可选 `tags` 字符串数组，例如 `{"journal_key":"sample","name":"示例医学期刊","tags":["医学健康"]}`。平台只用这些标签做期刊搜索与筛选，实际采集仍通过 `journal_keys` 参数传递。未声明标签时，界面根据刊名做粗分类；无法确定时显示“综合/待细分”。修改目录后重新导入需提高 `package_version`。

### 2. 声明清单与表结构

以下是最小的、无第三方依赖、无增量游标的 `manifest.json` 示例。把名称和字段按目标网站实际数据调整；平台按 `output_schema` 自动建表，插件本身不建表、不连接平台数据库。

```json
{
  "protocol_version": "1.0",
  "package_key": "my_source",
  "package_version": "1.0.0",
  "name": "我的采集源",
  "description": "按关键词采集条目",
  "category": "news",
  "runtime": {
    "type": "python",
    "python_version": "3.14",
    "entrypoint": "crawler.py",
    "dependencies": "requirements.lock"
  },
  "capabilities": {"incremental": false},
  "parameters_schema": {
    "type": "object",
    "properties": {"language": {"type": "string", "default": "zh"}},
    "additionalProperties": false
  },
  "secret_names": [],
  "output_schema_version": 1,
  "output_schema": {
    "fields": [
      {"name": "external_id", "type": "string", "max_length": 255, "nullable": false},
      {"name": "title", "type": "string", "max_length": 1000, "nullable": false},
      {"name": "url", "type": "text", "nullable": true},
      {"name": "summary", "type": "text", "nullable": true}
    ],
    "identity_fields": ["external_id"],
    "indexes": [],
    "mapping": {"title": "title", "url": "url", "summary": "summary"}
  }
}
```

`parameters_schema` 使用 JSON Schema Draft 2020-12，顶层必须是 object 且 `additionalProperties` 为 false；可给参数设置 `default`、范围、枚举及嵌套规则，不使用远程 `$ref`。`fields` 中至少有一个字段，最多 64 个；每个字段都要声明 `nullable`。支持 `string`（必须有 `max_length`，1–1000）、`text`、`integer`、`decimal`（声明 `precision` 和 `scale`，值以 JSON 字符串输出）、`boolean`、`date`、`datetime`（带时区的 RFC 3339 字符串）、`array` 和 `object`（必须附对应的 JSON Schema）。字段名只能是小写字母、数字、下划线，且不能以 `sys_` 开头。

`identity_fields` 必须指向不可空的稳定标量字段，不能使用搜索词、抓取时间或易变标题做身份。多个站点可能有相同 ID 时，增加 `source_site` 字段并使用 `['source_site', 'external_id']` 作为联合身份。`mapping.title` 必须指向非空展示标题；`url`、`summary`、`published_at` 为可选映射。最多声明 8 个索引，每个索引 1–3 个可索引标量字段。插件输出不能包含平台保留的 `sys_*` 字段。

### 3. 处理请求并输出文件

平台调用形式为 `python crawler.py --request <绝对路径> --output <绝对路径>`。请求 JSON 包含 `protocol_version`、`execution_id`、`package_key`、`package_version`、`query`、`aliases`、`limit`、`parameters`、`cursor`、`cursor_version`、`time_range`（`from`/`to`）和 `deadline_at`。`query` 非空；每次最多输出 `limit` 条。不能支持某项过滤条件时，应在结果的 `warnings` 中说明，不要假称已过滤。

入口脚本的最小骨架如下；把 `fetch_items` 替换成真实抓取和解析逻辑。无结果也可以成功返回空列表。

```python
import argparse
import json
import sys
from pathlib import Path


def fetch_items(request):
    # TODO: fetch from the target using request["query"] and request["parameters"].
    # Every item must match the fields declared in manifest.json.
    return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    status, error, items = "completed", None, []
    try:
        items = fetch_items(request)[:request["limit"]]
    except Exception as exc:
        status = "failed"
        error = {"code": "NETWORK_OR_PARSE_ERROR", "message": str(exc), "retryable": True}
    with (output / "items.jsonl").open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + "\n")
    result = {
        "protocol_version": "1.0", "execution_id": request["execution_id"],
        "status": status, "item_count": len(items), "next_cursor": None,
        "has_more": False, "warnings": [], "error": error,
    }
    temporary = output / "result.json.tmp"
    temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    temporary.replace(output / "result.json")
    return 1 if status == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
```

`items.jsonl` 每行一个 JSON 对象，**只能**含清单声明的业务字段；`item_count` 等于非空记录行数，包括被平台判为不合格的行，不是“新增入库数”。`result.json` 顶层必须恰好包含上述八个键，`execution_id` 必须与请求相同。`completed`/`partial` 退出码为 0；`failed` 必须非 0 并填写 `error`，失败尝试不入库。写完 `items.jsonl` 后再原子替换 `result.json`。日志写 stdout/stderr，平台会存到本次运行目录。

默认 `incremental: false` 必须返回 `next_cursor: null`、`has_more: false`。若要增量采集，声明 `incremental: true`，读取请求的 `cursor`，成功时返回可 JSON 序列化的 `next_cursor`；`has_more: true` 必须同时返回非空游标。`partial` 或 `failed` 不推进游标。凭证只通过清单的 `secret_names` 声明，由平台以 `CRAWLER_SECRET_<NAME>` 环境变量注入，绝不写入清单、样例请求或日志。

### 4. 本地测试、导入与查询

先把 `tests/request.json` 中的 `package_key`、`package_version`、参数和 `execution_id` 调整到与新包一致，然后在仓库根目录运行：

```powershell
.\.venv\Scripts\python.exe my_source\crawler.py --request my_source\tests\request.json --output my_source\test-output
Get-Content my_source\test-output\result.json
Get-Content my_source\test-output\items.jsonl
.\.venv\Scripts\python.exe -X utf8 platform_main.py import my_source
.\.venv\Scripts\python.exe -X utf8 platform_main.py list packages
.\.venv\Scripts\python.exe -X utf8 platform_main.py create-monitor "新来源测试" "人工智能" --packages my_source
.\.venv\Scripts\python.exe -X utf8 platform_main.py run 1
.\.venv\Scripts\python.exe -X utf8 platform_main.py worker --once
.\.venv\Scripts\python.exe -X utf8 platform_main.py list run 1
```

上例中的两个 `1` 只是示意：运行时分别替换为 `create-monitor` 返回的监控 ID 和 `run` 返回的运行 ID。导入需要已按“快速启动”初始化 MySQL；导入器会检查清单和 Python 版本、安装依赖并创建结果表。运行后可通过 `GET /api/v1/runs/{id}` 查看每个包的状态和错误，通过 `GET /api/v1/packages/{package_key}/records` 查询记录；执行目录位于 `crawler_platform_runtime/runs/<execution_id>/`，包含 `request.json`、`process.log`、`output/items.jsonl`、`output/result.json`，有坏行时还会有 `output/rejected.jsonl`。最后运行仓库契约测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests_platform -v
```

## 验证

每日自动采集按北京时间设定，已有任务可在“监控任务 > 执行计划”启用；服务器需要 API、Scheduler、Worker 三个常驻进程。部署和失败恢复说明见 [每日定时采集部署](docs/daily-scheduled-collection.md)。

监控任务可在“进行中 / 已归档”之间管理。归档会停止该任务后续的定时采集和周报、取消未开始的周报，但保留运行记录、采集结果和匹配关系；正在采集或生成周报时须等当前执行结束再归档。恢复时可修改任务名称，任务恢复后仍处于停用状态，需在“执行计划”中重新启用。未归档任务名称经 Unicode 规范化、空格合并和大小写折叠后必须唯一；同一关键词可以创建不同名称的任务，页面仅作提醒。首次升级已有数据库运行 `python platform_main.py init-db` 应用归档迁移；若旧任务重名，需先归档或改名其中一个，再重试迁移。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests_platform -v
```
