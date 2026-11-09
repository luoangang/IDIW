# 爬虫包分类与目录规范

## 六类数据

| category | 名称 | 主要输出 |
| --- | --- | --- |
| news | 新闻资讯 | 新闻、RSS、公告、资讯 |
| academic | 学术文献 | 期刊、会议、学位论文、预印本 |
| patents | 专利 | 专利申请、授权、法律状态 |
| reference | 知识资料 | 百科、图书、技术文档、标准 |
| entities | 主体信息 | 企业、机构、学者、产品属性 |
| community | 社区内容 | 论坛、社交、问答、评论 |

按主要输出类型归类，每个包只属于一类。军事、金融、人工智能等行业和主题不作为这一层目录。多类型采集器优先拆包。

## 目录

```text
crawler_packages/                   # 开发者维护的源码
  news/google_news_rss/
  news/sina_news/
  academic/
  patents/
  reference/baidu_baike/
  reference/wikipedia/
  entities/
  community/

crawler_platform_runtime/packages/  # 平台安装的不可变制品
  <category>/<package_key>/<package_version>/<artifact_digest>/
```

新包的 `manifest.json` 使用六个标准 category 值之一。分类目录和清单声明必须一致。ZIP 内部仍可只包含一个包，不需要把分类目录打进 ZIP；平台按清单分类安装。

旧包的 `encyclopedia`、`books` 自动解释为 `reference`，`paper` 自动解释为 `academic`。为避免同版本摘要变化，现有已发布包的清单原文暂不改写；下一次发布新版本时使用标准值。不认识的分类拒绝导入。

分类不参与包身份：package_key 仍全局唯一，每个包一张结果表。独立 Python 环境继续按 package_key/version 存储，不搬动 venv，避免 Windows 启动器内嵌绝对路径失效。

## 导入与发现

```powershell
.\.venv\Scripts\python.exe platform_main.py import crawler_packages\reference\baidu_baike
.\.venv\Scripts\python.exe platform_main.py import crawler_packages --all
.\.venv\Scripts\python.exe platform_main.py import crawler_packages\news --all
```

发现器支持单个包、原来的平铺目录，以及六类目录；不递归扫描任意深度的安装制品。批量导入逐包提交，一个包失败停止后续导入，已成功的包不回滚。重复导入仍复用已登记的安装路径。

`GET /api/v1/categories` 返回六类标识和中文名称。

## 已安装包迁移

```powershell
.\.venv\Scripts\python.exe platform_main.py migrate-package-layout
```

迁移先复制并校验制品内容，再在一个数据库事务中更新包的分类、活动路径、执行记录的制品路径和监控任务的分类选择。任务 ID、包 ID、数据表、默认参数、采集数据均不变；未知分类、缺失文件或摘要冲突会中止，并回滚数据库。

旧制品保留在原目录作为回退副本，保证迁移前已启动的进程仍能使用旧路径。失败时可能留下已校验的副本，可重复运行迁移。建议维护窗口执行，复制期间会短暂持有数据库行锁。此命令不自动清除旧目录；确认没有进程使用旧路径后才能另行清理。
