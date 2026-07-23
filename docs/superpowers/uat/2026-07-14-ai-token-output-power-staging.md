# AI Token 输出电力产业链 staging 验收记录

**日期：** 2026-07-14
**链标识：** `ai_token_output_power`
**状态：** staging 数据库迁移、八层注册、候选映射和 D 池物化已完成；未进行 production 注册。

## 已执行命令

```bash
cd backend && .venv/bin/alembic upgrade 034
python3 tools/register_ai_token_output_power.py --mode staging --as-of-date 2026-07-14
python3 tools/seed_ai_token_output_power_candidates.py --as-of-date 2026-07-14
python3 tools/materialize_ai_token_output_power.py --mode staging --as-of-date 2026-07-14 --top-n 2000
python3 tools/audit_ai_token_output_power.py --as-of-date 2026-07-14
```

## 当前 staging 结果

数据库当前 Alembic 版本为 `034`。已注册 8 个 L1-L8 节点和 8 个拆解视图，并从现有 AI 算力、AI 应用商业化、新型电力系统三条链生成跨链候选：

```json
{
  "chain_id": "ai_token_output_power",
  "mapping_count": 1018,
  "unique_company_count": 784,
  "evidence_count": 1018,
  "formal_count": 0,
  "provisional_count": 1018,
  "pool_counts": {"A": 0, "B": 0, "C": 0, "D": 1018},
  "coverage_ratio": 0.0
}
```

L3-L8 映射数分别为 22、242、234、83、65、372；L1/L2 是宏观约束和电力可利用量，不直接映射公司。全部证据均为 `E0 + candidate + unknown power_source_type`。这表示业务相关性候选，不表示已验证的可利用电力、Token 产能、客户或收入，因此 A/B/C 正式池保持为 0。

## 已验证的结构门槛

- L1-L8 配置齐全。
- 七个产业维度与市场交易层分离。
- 电力来源区分弃风弃光、低谷电、园区/长期购电协议和名义容量。
- Token 产能、单位成本、证据等级和 A/B/C/D 池均有纯函数测试。
- rejected/disabled 映射不会进入正式排名。
- D 池只作为 `provisional_items`，不进入正式推荐和回测。
- production 注册需要 `ALLOW_SUPPLY_CHAIN_PRODUCTION_REGISTRATION=1`，未授权时会拒绝执行。

## 专项测试结果

- `packages/kronos-factors`：9 项通过。
- `services/screener-service` Token 专项：6 项通过。
- `packages/kronos-factors` 与服务层合计：15 项通过。
- 三组测试分开运行是因为仓库的多个 `tests` 目录在同一 pytest 收集命令下会发生模块名冲突；分组运行结果可复现，代码本身没有测试失败。

## 阻断项和下一验证节点

1. 补充并人工审核电力、并网、PPA、算力上线、推理运行和收入原始证据。
2. 证据达到 E2 后才允许进入 C 池；E3/E4/E5 分别对应 B/A 池升级条件。
3. 当前电力字段和 Token 产能模型覆盖率均为 0%，不得据此排序正式受益程度。
4. 只有正式池证据链和 API 下钻均通过，才讨论 production 注册；本记录不构成交易建议。
