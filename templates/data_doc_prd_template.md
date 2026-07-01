# Data Doc PRD Template And BA Writing Standard

> 用途：BA 按本模板编写 PRD，后续使用 `$data-doc-to-dev-md` 将 DOCX 转换为 `dev_doc.md`、`structured_facts.json`、`questions.md`。  
> 核心原则：业务事实放进真实 Word 表格或嵌入 Excel。不要用截图、自由段落、合并单元格承载源表、目标表、字段映射、计算逻辑、调度、rowkey 或写入策略。

## 0. BA 填写规则

1. 表格第一行必须是表头，不能合并单元格，不能做多层表头。
2. 本模板标注为“固定表头”的表格，列名不能改同义词、不能增删关键列。
3. 不确定的内容写 `待确认`，不要留空，也不要猜测。
4. 每个源表、目标表、Target、Pipeline、字段规则单独占一行。
5. 字段计算逻辑必须写到字段行内，包含过滤、join、默认值、空值、去重、四舍五入、分母为 0 等处理。
6. HBase rowkey、ClickHouse 删除条件、重跑范围、调度频率、全量/增量策略必须显式写出。
7. 密钥、IP、token、生产路径只写占位符或说明，不写真实敏感信息。
8. 如果字段字典来自外部 Excel，请作为嵌入 Excel 放入 DOCX，或复制为真实 Word 表格。

## 1. 文档信息与变更记录

| 项目 | 内容 |
|---|---|
| 项目名称 | 待填写 |
| PRD 编写人 | 待填写 |
| BA / Owner | 待填写 |
| 开发 Owner | 待填写 |
| 项目类型 | data-sync / report / mixed |
| 目标环境 | UAT / PROD / both |
| 需求来源 | 待填写 |
| 文档日期 | YYYY-MM-DD |

| 版本 | 日期 | 修改人 | 修改内容 | 影响范围 |
|---|---|---|---|---|
| v0.1 | YYYY-MM-DD | 待填写 | 初稿 | 待确认 |

## 2. 项目概览

| 项目 | 内容 |
|---|---|
| Business goal | 待填写 |
| 输出对象 | 报表 / 同步表 / HBase 服务 / FS 文件 / ClickHouse 表 |
| 使用方 | 待填写 |
| 触发方式 | 定时 / 手动 / 上游触发 |
| 数据粒度 Grain | 例如：period + dealer + model |
| 时间口径 | period / date / current_date / update_time |
| 是否涉及历史回补 | 是 / 否 / 待确认 |
| 是否涉及 HBase | 是 / 否 / 待确认 |
| 是否涉及 ClickHouse | 是 / 否 / 待确认 |
| 是否涉及 FS / Gateway 留痕 | 是 / 否 / 待确认 |

## 3. 业务范围与数据口径

| 口径项 | 说明 |
|---|---|
| 统计范围 | 待填写 |
| 过滤条件 | 待填写 |
| Join 关系 | 待填写 |
| 去重规则 | 待填写 |
| 空值处理 | 待填写 |
| 默认值规则 | 待填写 |
| 数值精度 / 舍入 | 待填写 |
| 特殊业务例外 | 待填写 |
| 不纳入范围 | 待填写 |

## 4. 数据源矩阵

固定表头，适用于报表开发。`位置` 建议填写 HBase、ClickHouse、MSSQL、MySQL、FS、Blob、Gateway 等。

| 位置 | 数据表名 | 数据表 | 取数范围 | 字段 | 关联、过滤信息 | 备注 |
|---|---|---|---|---|---|---|
| 待填写 | 待填写 | database.table 或 path | 待填写 | 字段1；字段2；字段3 | join/filter 条件 | 待确认 |

可选：如果是 COT / DataEngine 数据同步项目，请填写下方同步矩阵。

| 序号 | 所属类别 | 报表类型 | 业务描述 | hbase 表 | Hbase数据范围 | clickhouse表 | 备注 |
|---|---|---|---|---|---|---|---|
| 1 | 待填写 | 待填写 | 待填写 | namespace.table | 待填写 | database.table | 待确认 |

## 5. 目标表矩阵

固定表头，适用于 ClickHouse 物理目标表识别。

| Description | Data Storage | Database | Table Name | Grain | Write Mode | Delete Strategy | Notes |
|---|---|---|---|---|---|---|---|
| 待填写 | ClickHouse | database | table_name | period + key | insert / replace / append | delete by period / truncate / none | 待确认 |

HBase / FS 目标请同时写成明确文本，避免只放在截图里。

| Target Type | Target Name / Path | Rowkey / File Rule | Write Mode | Delete / Overwrite Strategy | Notes |
|---|---|---|---|---|---|
| HBase / FS | 待填写 | 待填写 | put / export / trigger pipeline | 待填写 | 待确认 |

## 6. Data Utilization / Target Management

固定表头，用于识别 Data Utilization 名称。

| Name | Description |
|---|---|
| 待填写 | 待填写 |

固定表头，适用于报表 Target Management。

| Data Utilization Name | Target Name | Target Description | Data Storage | Physical Target Table | Field Dictionary Sheet |
|---|---|---|---|---|---|
| 待填写 | 待填写 | 待填写 | ClickHouse / HBase / FS | database.table 或 namespace.table | 本文第 7 节字段字典 |

固定表头，适用于 COT / 数据同步目标映射。

| Data Utilization Name | catalog | hbase_target前缀 | clickhouse_target前缀 | Hbase Target Name | Clickhouse Target Name | 备注 |
|---|---|---|---|---|---|---|
| 待填写 | 待填写 | 待填写 | 待填写 | 可为空，优先写完整目标表 | 可为空，优先写完整目标表 | 待确认 |

## 7. 字段字典

固定表头。每个目标表或 Target 建议单独放一张字段字典表；如果字段很多，可以嵌入 Excel，但第一行仍必须是表头。

| 字段 | 字段描述 | 字段类型 | 字段类型(mysql) | 是否主键 | 是否可空 | 示例 | 备注 |
|---|---|---|---|---|---|---|---|
| field_key | 字段中文名 | String / Int / Decimal / Date | varchar / int / decimal / date | 是 / 否 | 是 / 否 | sample | 待确认 |

## 8. 字段映射与计算逻辑

固定表头，适用于报表字段逻辑抽取。每个输出字段必须有一行。

| 字段key | 字段名称 | 字段类型 | 字段顺序 | 数据源位置 | 数据表 | 数据源对应的字段 | 计算逻辑 | EO+ERP订单逻辑 | DMS订单逻辑 | 字段样例 | 备注 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| field_key | 字段中文名 | String | 1 | HBase / ClickHouse / MSSQL | database.table | source_field | 过滤、join、聚合、默认值、空值处理写在这里 | 如不适用写 N/A | 如不适用写 N/A | sample | 待确认 |

KPI / 计算口径补充表。

| KPI / Field | Grain | Formula / Rule | Filters | Null / Zero Handling | Notes |
|---|---|---|---|---|---|
| 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待确认 |

## 9. 数据处理流程

| Step | Module | Input | Processing Rule | Output | Failure Behavior |
|---|---|---|---|---|---|
| 1 | DataSource | 源表 / 文件 / API | 取数、过滤、参数解析 | 原始数据集 | 失败是否阻断 |
| 2 | DataProcess | 原始数据集 | join、转换、聚合、字段映射 | 目标数据集 | 失败是否阻断 |
| 3 | DataStorage | 目标数据集 | 删除旧数据、写入、留痕 | HBase / ClickHouse / FS | 失败是否告警 |

## 10. 写入策略

| Target | Delete old data | Insert method | HBase rowkey | FS evidence retention | Table-level exceptions |
|---|---|---|---|---|---|
| database.table / namespace.table / path | delete by period / date / key / truncate / none | insert / batch insert / put / export | rowkey 拼接字段、格式、是否散列 | 目录、文件名、保留周期 | truncate、历史库名前缀、特殊表等 |

## 11. 调度与重跑

固定表头，适用于 COT / 数据同步调度。

| Data Utilization Name | Pipeline Name | task1 name | 定时同步时间 | pipeline前缀 | 重跑规则 |
|---|---|---|---|---|---|
| 待填写 | 待填写 | 待填写 | 每日 HH:mm / 每 P / 手动 | 待填写 | 按 period / date / full / delta |

固定表头，适用于报表调度。

| Data Utilization Name | Pipline_Name | task1 name | Description | 定时任务 | 重跑规则 |
|---|---|---|---|---|---|
| 待填写 | 待填写 | 待填写 | 待填写 | 每日 HH:mm / 每 P / 手动 | 按 period / date / full / delta |

重跑与回补说明。

| 场景 | 参数 | 数据范围 | 是否先删旧数据 | 是否覆盖 FS 文件 | 备注 |
|---|---|---|---|---|---|
| 日常重跑 | period / current_date / sync_dates | 待填写 | 是 / 否 / 待确认 | 是 / 否 / 待确认 | 待确认 |
| 历史回补 | period range / date range | 待填写 | 是 / 否 / 待确认 | 是 / 否 / 待确认 | 待确认 |

## 12. 参数设计

| Parameter | Required | Example | Description | Notes |
|---|---|---|---|---|
| running_env | Y | uat / prod | 运行环境 | 不写真实密钥 |
| period | N | 202601 | 业务期间 | 无 period 项目写 N/A |
| current_date | N | 2026-01-31 | 运行日期 | 待确认 |
| sync_dates | N | 2026-01-01,2026-01-31 | 重跑日期范围 | 待确认 |
| receiver_emails | N | user@example.com | 告警收件人 | 可用占位符 |
| source table | N | database.table | 源表覆盖参数 | 待确认 |
| target table | N | database.table | 目标表覆盖参数 | 待确认 |
| rowkey fields | N | field1,field2 | HBase rowkey 字段 | 待确认 |

```json
{
  "running_env": "uat",
  "period": "",
  "current_date": "",
  "sync_dates": [],
  "receiver_emails": [],
  "source_informations": {},
  "hbase_informations": {},
  "clickhouse_information": {}
}
```

## 13. 日志校验计划

| Checkpoint | Expected Log / Metric | Success Criteria | Failure Owner | Notes |
|---|---|---|---|---|
| DataSource | 源表、取数范围、行数 | 源数据行数符合预期 | BA / Dev | 待确认 |
| DataProcess | join、过滤、聚合、字段映射后行数 | 关键 KPI 和抽样字段正确 | BA / Dev | 待确认 |
| DataStorage HBase | rowkey、delete、put 行数 | 写入行数和目标 rowkey 正确 | Dev | 待确认 |
| DataStorage ClickHouse | delete 条件、insert 行数、目标表 | 删除和写入范围正确 | Dev | 待确认 |
| FS / Gateway | 文件路径、文件名、文件数量 | 留痕文件存在且可读 | Dev | 待确认 |
| Final metrics | 源行数、目标行数、失败数 | 与业务验收口径一致 | BA / Dev | 待确认 |

## 14. 未决问题

| ID | 问题 | 影响范围 | Owner | Deadline | Status |
|---|---|---|---|---|---|
| Q1 | 待填写 | 源表 / 字段 / 写入 / 调度 / 重跑 | 待填写 | YYYY-MM-DD | Open |

## 15. 提交前自检清单

| Check Item | Result | Notes |
|---|---|---|
| 所有固定表头未改名 | Pass / Fail |  |
| 所有表格第一行都是表头 | Pass / Fail |  |
| 没有用截图承载字段字典或映射逻辑 | Pass / Fail |  |
| 源表、目标表、字段映射、调度、重跑均已填写 | Pass / Fail |  |
| HBase rowkey 已明确或写入未决问题 | Pass / Fail |  |
| ClickHouse 删除策略已明确或写入未决问题 | Pass / Fail |  |
| 密钥、IP、token 均未写真实值 | Pass / Fail |  |
| 未确认事项已集中写入第 14 节 | Pass / Fail |  |

