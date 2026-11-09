# USPTO 20 个新增授权号实时验收

日期：2026-10-15。与 2026-10-13 的六号码验收样本互不重复。本次通过 USPTO Patent Public Search 公开会话及官方详情接口逐条查询；号码先从公开授权记录挑选。测试采用五条一批、四批运行，不把网页搜索结果当作包的成功证明。

## 结果

- 20/20 个号码命中，20/20 有标题、摘要、申请号、申请人和授权日期。
- 初始包 1.0.2 的受让人字段为 19/20；`US 12,210,592` 官方详情未列受让人，保留空值并报告 `FIELDS_MISSING`。
- 初始包 1.0.2 的申请日期为 18/20。`US 10,162,010` 与 `US 9,787,108` 官方页面使用 `Filed (or PCT Filed)` 标签，旧解析器仅认 `Filed`，属于解析遗漏。包 1.0.3 已支持该标签，两条实时复测分别取得 `2014-11-28` 与 `2013-11-01`。这可能是 PCT 申请日，不应无条件称为美国国家阶段进入日。
- 修复后按这 20 条样本计算，申请日期可获取 20/20；但没有对升级后的 1.0.3 重新完整运行全部 20 条，也没有做平台入库或重复入库验收。

| 授权号 | 类型 | 标题 | 1.0.2 缺失字段 |
| --- | --- | --- | --- |
| [US 11,748,653](https://patents.google.com/patent/US11748653B2/en) | B2 | Machine learning abstraction | 无 |
| [US 11,914,366](https://patents.google.com/patent/US11914366B2/en) | B2 | Blended operator and autonomous control in an autonomous vehicle | 无 |
| [US 11,968,088](https://patents.google.com/patent/US11968088B1/en) | B1 | Artificial intelligence for intent-based networking | 无 |
| [US 9,983,582](https://patents.google.com/patent/US9983582B2/en) | B2 | Autonomous vehicles | 无 |
| [US 12,210,592](https://patents.google.com/patent/US12210592B1/en) | B1 | System, method, and product for transparently encapsulated artificial intelligence | 受让人 |
| [US 10,850,344](https://patents.google.com/patent/US10850344B2/en) | B2 | Robot | 无 |
| [US 10,710,250](https://patents.google.com/patent/US10710250B2/en) | B2 | Robot | 无 |
| [US 11,971,914](https://patents.google.com/patent/US11971914B1/en) | B1 | Artificial intelligence systems and methods | 无 |
| [US 12,174,954](https://patents.google.com/patent/US12174954B1/en) | B1 | Generative AI model information leakage prevention | 无 |
| [US 12,067,476](https://patents.google.com/patent/US12067476B2/en) | B2 | Mixture of experts neural networks | 无 |
| [US 9,931,956](https://patents.google.com/patent/US9931956B2/en) | B2 | Battery management system | 无 |
| [US 10,162,010](https://patents.google.com/patent/US10162010B2/en) | B2 | Wireless network based battery management system | 申请日期（1.0.3 已修复） |
| [US 9,991,724](https://patents.google.com/patent/US9991724B2/en) | B2 | Battery management system for vehicle and controlling method thereof | 无 |
| [US 10,547,184](https://patents.google.com/patent/US10547184B2/en) | B2 | System and method for battery management | 无 |
| [US 9,172,256](https://patents.google.com/patent/US9172256B2/en) | B2 | Battery management circuit and battery management method for managing battery apparatus | 无 |
| [US 9,527,400](https://patents.google.com/patent/US9527400B2/en) | B2 | Smart energy management to improve electrified vehicle battery life | 无 |
| [US 10,374,444](https://patents.google.com/patent/US10374444B2/en) | B2 | Method and system for battery management | 无 |
| [US 9,787,108](https://patents.google.com/patent/US9787108B2/en) | B2 | Enhanced battery management system | 申请日期（1.0.3 已修复） |
| [US 9,377,839](https://patents.google.com/patent/US9377839B2/en) | B2 | Dynamic battery management | 无 |
| [US 12,202,142](https://patents.google.com/patent/US12202142B2/en) | B2 | Systems, apparatuses, and methods for robotic learning and execution of skills including navigation and manipulation functions | 无 |

复跑脚本：`python -m scripts.verify_uspto_20`。它实时请求 USPTO，不是离线单元测试；会遵守包内请求间隔，耗时较长。包 1.0.3 已导入当前平台，沿用原数据表 `pkg_data_000008`。
