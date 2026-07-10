# ADR-018: Schema and table ownership release gate

每张业务表必须声明唯一 owner，且 writers 只能包含 owner。CI 在发布前运行
`python3 tools/audit_table_ownership.py --fail-on violation`；违反即阻断发布。
