# DOCX Extraction Rules

## Evidence Priority

1. Embedded Excel workbooks in `word/embeddings/*.xlsx`
2. Word tables in `word/document.xml`
3. Word paragraph text and heading-like styles
4. Screenshots or images, only when no structured table is available

## Extraction Expectations

- Keep original field names, table names, Chinese labels, and formulas.
- Export embedded Excel sheets and Word tables to CSV with UTF-8 BOM so Excel on Windows can open Chinese text.
- Do not infer table grain, rowkey, delete conditions, or schedule unless explicitly present.
- Any missing business rule belongs in `questions.md`.

## Common DataEngine Document Signals

- Source sections: `Source 数据源`, `数据源详情`, `链接信息`, `数据列表`, `Data Source`
- Target sections: `Data Target`, `目标表`, `Data Storage`, `目标表字典`
- Processing sections: `Data Transformation Logic`, `数据流程`, `同步逻辑`, `写入流程`
- Schedule sections: `Pipeline Planning`, `运行时间`, `调度`, `频率`, `重跑`
- Report sections: `报表字段逻辑`, `KPI`, `汇总逻辑`, `字段映射`

## Output Quality Bar

- `dev_doc.md` should be readable without opening the original DOCX.
- If embedded Excel contains a report/sync matrix, `dev_doc.md` must include the actual rows, not only the CSV filenames.
- Generate and review `dev_doc/structured_facts.json` whenever recognizable matrices exist.
- `questions.md` should contain every material ambiguity that could affect code generation.
- Do not collapse multiple target tables into one vague paragraph; list them separately when possible.

## Recognized COT Sync Matrices

For COT yearly sync docs, detect these embedded Excel shapes:

- Report list: headers like `序号`, `业务描述`, `hbase 表`, `Hbase数据范围`, `clickhouse表`.
- Data Utilization names: headers like `Name`, `Description`.
- Target mapping: headers like `Data Utilization Name`, `catalog`, `hbase_target前缀`, `clickhouse_target前缀`.
- Pipeline schedules: headers like `Data Utilization Name`, `task1 name`, `定时同步时间`, `pipeline前缀`.
- Field dictionaries: headers like `字段`, `字段描述`, `字段类型`, `字段类型(mysql)`.

The handoff to codegen should preserve source table, source range, target table, inferred Data Utilization name, field count, first fields, schedule, and any inferred mapping notes.

## Recognized Report Development Matrices

For DataEngine report docs, detect these embedded Excel shapes:

- Source matrix: headers like `位置`, `数据表名`, `数据表`, `取数范围`, `字段`, `关联、过滤信息`.
- Some supervisor-portal docs use `数据范围` instead of `取数范围` and omit explicit field/filter columns; still extract `位置`, `数据表名`, `数据表`, and the range.
- Physical ClickHouse target matrix: headers like `Description`, `Data Storage`, `Database`, `Table Name`.
- Target Management: headers like `Data Utilization Name`, `Target Name`, `Target Description`, `Data Storage`.
- Pipeline schedule: headers like `Data Utilization Name`, `Pipline_Name`, `task1 name`, `Description`, or `Pipeline Name` + `定时任务`.
- Target field logic: headers like `Key`/`字段 key`/`字段key`, `字段名称`/`字段名`, `数据源位置`, `数据表`, `数据源描述`/`来源库表`, `数据源对应的字段`/`来源字段`, `计算逻辑`.
- Word正文 field tables may contain an explanatory first row before the actual header row; the extractor should detect the real header row and skip the preamble.
- HBase physical target matrices may have headers like `位置`, `数据表`, `数据表名`; treat `Data Hub Hbase` plus a table such as `l1_cot.store_yield_grade_p` as a physical target, not a ClickHouse target.

The handoff to report codegen should preserve source storage type, source table/path, read range, source field list, join/filter notes, logical target names, physical HBase/ClickHouse/FS targets from Data Target text, field order, field-level calculation logic, EO/DMS-specific rules, and schedule rows.
