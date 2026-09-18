# 来源插件标准

## 必填声明

```python
class ExamplePlugin(SourcePlugin):
    module = "paper"
    name = "example_papers"
    label = "示例论文源"
    resource_type = "academic_paper"
    supported_modes = ("search", "sync")
    contract_version = 1
```

来源名称只能使用小写字母、数字及下划线。一个来源文件只能暴露一个直接继承 `SourcePlugin` 的插件类。插件不决定物理表，系统按照 `module` 自动写入对应模块资源表。

## 采集入口

```python
def collect(self, request: CollectionRequest) -> list[SourceItem]:
    self.validate_request(request)
    ...
```

插件必须遵守 `request.limit`。搜索模式必须使用 `request.query`；不支持关键词的平台应声明只支持 `sync`，由本地数据库承担检索，不能忽略关键词后返回无关结果。

## 标准资源

所有记录必须提供：

- `title`：非空标题；
- `url`：可定位原始记录的链接；
- `resource_type`：具体资源类型；
- `source_item_id`：来源稳定编号，能提供时必须填写。

领域标识符放入 `identifiers`，例如：

```python
identifiers={"doi": "10.1000/example"}
identifiers={"patent_number": "CN123456A"}
```

论文作者使用 `authors` 列表，卷、期、页码、机构、关键词等放入 `extra`。禁止把密码、Cookie、访问令牌或完整响应头写入 `extra`。

## 错误和网络

- 网络请求必须有超时并检查 HTTP 状态。
- 解析失败应抛出带上下文的异常，不能伪装成成功空结果。
- 一个插件不得直接访问数据库或写入其他模块资源表。
- 日常采集不得执行模型生成的代码。
- AI 生成的来源配置必须经过确定性小样本验证和人工发布。

## 测试要求

新增来源至少覆盖：

1. 插件可被自动发现且无注册错误；
2. 样本响应能转换为 `SourceItem`；
3. 无效响应返回明确错误或空结果；
4. `limit`、模式和配置项被正确执行；
5. 稳定标识在不同查询词下保持一致。
