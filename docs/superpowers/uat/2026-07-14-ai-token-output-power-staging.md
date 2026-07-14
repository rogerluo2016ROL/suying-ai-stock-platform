# AI Token 输出电力产业链 staging 验收记录

**日期：** 2026-07-14  
**链标识：** `ai_token_output_power`  
**状态：** staging 代码已完成，数据库迁移尚未执行，未进行 production 注册。

## 已执行命令

```bash
python3 tools/materialize_ai_token_output_power.py --mode dry-run --as-of-date 2026-07-14 --top-n 200
python3 tools/audit_ai_token_output_power.py --as-of-date 2026-07-14
```

## 当前 dry-run 结果

由于本地数据库尚未执行 Alembic `032`，Token 证据表不存在，dry-run 没有生成候选映射：

```json
{
  "chain_id": "ai_token_output_power",
  "mapping_count": 0,
  "evidence_count": 0,
  "formal_count": 0,
  "provisional_count": 0,
  "pool_counts": {"A": 0, "B": 0, "C": 0, "D": 0},
  "coverage_ratio": 0.0
}
```

失败原因是数据状态，不是用默认值伪造结果：`business_tag_token_output_power_evidence` 尚未创建。当前结果不能解读为“没有 Token 产业链公司”，只能解读为“尚未落库”。

## 已验证的结构门槛

- L1-L8 配置齐全。
- 七个产业维度与市场交易层分离。
- 电力来源区分弃风弃光、低谷电、园区/长期购电协议和名义容量。
- Token 产能、单位成本、证据等级和 A/B/C/D 池均有纯函数测试。
- rejected/disabled 映射不会进入正式排名。
- D 池只作为 `provisional_items`，不进入正式推荐和回测。
- production 注册需要 `ALLOW_SUPPLY_CHAIN_PRODUCTION_REGISTRATION=1`，未授权时会拒绝执行。

## 阻断项和下一验证节点

1. 在受控环境执行 Alembic `032`，确认六张 Token 输出表和索引创建成功。
2. 导入经过审核的电力、并网、算力上线、推理运行和收入证据，再运行 staging 物化。
3. 检查四池数量、七维覆盖率、重复证据数和 rejected/disabled 排除数。
4. 只有正式池证据链和 API 下钻均通过，才讨论 production 注册；本记录不构成交易建议。
