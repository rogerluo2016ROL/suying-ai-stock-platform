# services/sql — SQL 资产分类与执行方式

> 2026-07-23 梳理：此前 9 个 SQL 文件游离在 compose initdb 与 alembic 之外，只能手工 apply。
> 现按性质分三类管理。schema 权威链仍是 `backend/alembic`（backend 启动时自动 `upgrade head`），
> 本目录的 init 脚本仅在**全新 PG 数据卷**首次启动时由 docker-entrypoint-initdb.d 执行。

## A. initdb 自动执行（compose 挂载，全新卷首次启动）

| 文件 | 挂载序号 | 内容 |
|---|---|---|
| `init_postgres.sql` | 01 | 80 张业务表初始 schema |
| `materialized_views.sql` | 02 | 4 个物化视图 |
| `self_learning_init.sql` | 03 | 因子快照自学习（轻量版，无需 pgvector） |
| `tushare_parameter_catalog.sql` | 04 | Tushare 参数型接口目录表 |
| `data_governance_completion.sql` | 05 | daily_basic 等兼容字段补列（幂等 ADD COLUMN IF NOT EXISTS） |

注意：initdb 只在空 `pgdata` 卷首次启动时跑；既有部署需要手工执行一次后补的脚本。

## B. 手动执行（环境受限，不能进 initdb）

| 文件 | 原因 | 用法 |
|---|---|---|
| `pgvector_init.sql` | 依赖 pgvector 扩展，`postgres:15-alpine` 官方镜像未内置；挂载进 initdb 会导致首次初始化失败 | 换用带 pgvector 的镜像（如 `pgvector/pgvector:pg15`）后：`psql -h localhost -p 6432 -U kronos -d kronos -f services/sql/pgvector_init.sql` |

## C. 运维脚本（非 schema 初始化，不入 initdb）

| 文件 | 性质 | 用法 |
|---|---|---|
| `data_quality_check.sql` | 周期性检查（建议 cron 每周） | `psql -U kronos -d kronos -f services/sql/data_quality_check.sql` |
| `data_quality_fix.sql` | 一次性清理 + 约束加固（幂等，可重复） | 同上 |
| `register_bi_shifu_trend_v23.sql` | 一次性模型注册 INSERT | 同上 |
| `cb_sector.sql` | pg_dump 数据导入（含 dump 专用命令，非幂等） | 一次性导入：`psql -U kronos -d kronos -f services/sql/cb_sector.sql` |

`audit/`、`migrate_data.py` 等其余内容为迁移/审计工具，按各自文件头说明使用。
