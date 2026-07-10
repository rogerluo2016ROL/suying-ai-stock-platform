# ADR-018: Schema and table ownership release gate

每张业务表必须声明唯一 owner，且 writers 只能包含 owner。CI 在发布前运行
`python3 tools/audit_table_ownership.py --fail-on violation`；违反即阻断发布。

## 决策

- `configs/data_ownership.json` 是关键业务表唯一写入方的事实源，覆盖数据就绪、筛选、策略、训练、回测和交易域。
- 豁免必须同时填写原因 `exemption` 和 ISO 日期 `exempt_until`；过期豁免按违规处理，不能永久放行。
- `services/sql/audit/schema_audit.py` 继续只读 PostgreSQL，同时支持 `--json` 和 `--fail-on low|medium|high|none`。
- JSON finding 固定携带 `severity`、`owner`、`exemption`、`exempt_until`、`exempt` 和差异明细。
- 类型比较先标准化 PostgreSQL 别名，例如 `varchar/character varying`、`timestamptz/timestamp with time zone`，避免假阳性。

## 发布门

CI 无数据库凭据时运行纯函数契约测试和所有权检查；部署/SIT 环境再对现有库与 fresh DB 执行：

```bash
KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos \
  python3 services/sql/audit/schema_audit.py --json outputs/schema-audit.json --fail-on medium
```

任何未处于有效豁免期的 high/medium finding 都返回非零退出码。真实 drift 应通过迁移或 init schema 对齐解决，禁止降低阈值绕过。
