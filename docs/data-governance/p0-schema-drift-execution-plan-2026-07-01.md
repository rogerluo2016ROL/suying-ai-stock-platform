# P0 表结构漂移执行单

> 日期: 2026-07-01  
> 范围: `limit_list_d`、`moneyflow_hsgt`、`stk_mins`、`ths_concept_map`  
> 状态: 执行中。`moneyflow_hsgt` 的初始化 SQL 已完成低风险对齐；其余表仍需按本文安全边界推进。

## 目标

把真实 PG、初始化 SQL、写入端、查询端统一到同一份口径，保证后端和前端每次取数都知道“表在哪里、字段叫什么、字段是否真实入库”。

## 执行原则

1. 先修可低风险对齐的 DDL，再处理需要业务决策的表。
2. 只做可回滚迁移；涉及大表类型转换、唯一约束替换、字段语义变更时，必须先备份或影子表验证。
3. `init_postgres.sql`、alembic、写入函数、查询函数、目录审计测试必须一起更新，不能只改其中一个。
4. 任何字段被 ETL 丢弃，都要在目录里写明“主动丢弃”还是“待扩表”，不能继续依赖自动过滤造成误判。

## 当前事实

| 表 | 真实 PG 结构 | 初始化 SQL/写入端差异 | 风险判断 | 建议动作 |
|---|---|---|---|---|
| `moneyflow_hsgt` | 9 列：`trade_date`、`north_net_inflow`、`south_net_inflow`、`ggt_ss`、`ggt_sz`、`hgt`、`sgt`、`north_money`、`south_money` | 已补齐 `init_postgres.sql`；真实库本身已是 9 列 | 低 | 已完成初始化 SQL 对齐；后续继续保留测试 |
| `stk_mins` | `trade_time` 是 `text`，约 1963 万行，唯一键为 `(code, trade_time, freq)` | `init_postgres.sql` 期望 `trade_time TIMESTAMP`，索引也不完全一致 | 高 | 暂不直接改类型；先定“保留 text”还是“影子表转 timestamp” |
| `limit_list_d` | `trade_date` 是 `text`；同时存在 `(ts_code, trade_date, up_stat)` 与 `(ts_code, trade_date, limit_type)` 两个唯一索引 | 初始化 SQL 只声明 `(ts_code, trade_date, limit_type)`；字段 `"limit"` 需要统一引用 | 中 | 先保留两个唯一索引，补审计测试；再决定是否合并约束 |
| `ths_concept_map` | 真实 PG 为 `ts_code` 主键，字段是 `ts_code`、`name`、`list_date`、`type` | `sync_ths_concept_map` 写入 `ts_code`、`concept_name`、`concept_code`、`trade_date`；初始化 SQL 也是概念映射明细表设计 | 高 | 先定表语义：概念基础表还是个股-概念映射表；未定前不要迁移 |

## 执行顺序

### 第一步：低风险 DDL 对齐

- 补齐 `moneyflow_hsgt` 初始化 SQL 的 9 列。
- 增加审计测试，要求真实 PG、初始化 SQL、ETL 写入列三方一致。
- 生成只读目录，确认 `moneyflow_hsgt` 不再出现在 P0 漂移列表。

当前状态：已完成初始化 SQL 对齐和测试锁定。真实 PG 已经是 9 列，因此本步不需要对现有库执行 ALTER。

### 第二步：`limit_list_d` 约束治理

- 固定字段清单，明确 `limit` 在 SQL 中统一使用 `"limit"`。
- 保留现有两个唯一索引，先检查是否有依赖 `up_stat` 去重的写入或查询。
- 如果业务确认 `limit_type` 足够唯一，再另开迁移删除旧索引；否则保留并在目录里说明。

### 第三步：`ths_concept_map` 语义拆分

- 如果表要表达“概念基础信息”，采用真实 PG 结构：`ts_code`、`name`、`list_date`、`type`。
- 如果表要表达“个股-概念映射”，应新建或迁移为 `ths_member`/`ths_concept_members` 语义，字段包含 `ts_code`、`concept_name`、`concept_code`、`trade_date`。
- 修正 `sync_ths_concept_map`，避免写入字段和真实 PG 字段不一致。

### 第四步：`stk_mins` 大表处理

- 短期保留 `trade_time text`，让初始化 SQL 反向追认真实库，避免 fresh 部署和现网分叉。
- 中期如果必须改为 timestamp，先建影子表导入、建索引、比对行数和最大最小时间，再切读路径。
- 不允许直接对 1900 万行表执行原地类型转换。

## 验收标准

- `tushare_data_catalog.py` 生成目录成功。
- P0 四表在目录和专项审计里无未知漂移。
- 后端数据状态接口能正确返回日期列和最新日期。
- 相关单测通过，至少覆盖目录解析、字段一致性、同步映射、数据状态日期列。
