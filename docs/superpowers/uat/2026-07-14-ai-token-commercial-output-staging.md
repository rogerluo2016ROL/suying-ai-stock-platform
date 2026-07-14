# AI Token 商业输出产业链 staging 验收记录

**日期：** 2026-07-14

**链标识：** `ai_token_output`

**状态：** staging 迁移、八层注册、严格候选重建和D池物化已完成；未执行production注册。

## 口径

主链为 Token 需求、模型产品、推理软件、核心硬件、集群支撑、服务交付、计量运营和商业输出。电力只属于单位Token成本因素，不作为主层级或股票池升级门槛。旧链 `ai_token_output_power` 保留且未删除。

## 已执行命令

```bash
cd backend && .venv/bin/alembic upgrade 035
python3 tools/register_ai_token_output.py --mode staging --as-of-date 2026-07-14
python3 tools/rebuild_ai_token_output_candidates.py --as-of-date 2026-07-14 --mode staging
python3 tools/materialize_ai_token_output.py --as-of-date 2026-07-14 --mode staging
python3 tools/audit_ai_token_output.py --as-of-date 2026-07-14
```

## 实际结果

- Alembic：`035 (head)`；
- 新链节点/视图：8/8；
- 源映射：2,173条；
- 严格分类映射：1,405条，涉及533家标准化代码公司；
- 宽泛标签待人工复核：768条；
- L1-L8映射：717、0、398、74、216、0、0、0；
- 股票池：A=0、B=0、C=0、D=1,405；
- 国内商业输出已验证公司：0；海外商业输出已验证公司：0；
- Token数量/价格字段缺失比例：100%；
- 旧链映射：迁移前后均为1,018条。

L2、L6、L7、L8当前没有公司映射，是严格规则的结果：宽泛“大模型、云服务、软件、数据中心”标签不会自动进入这些层级，必须补充产品、API调用、计费、客户或收入证据后再分类。

## 审计结果

- 标准化代码后的同公司同层同标签重复：0；
- 宽泛标签进入正式池：0；
- 股票池证据门槛违规：0；
- rejected/disabled进入正式池：0；
- 旧链非预期改动：0；
- blocking issues：0。

## 结论与限制

当前成果完成了产业链结构和严格候选池，不代表完成了正式选股。所有新映射均从 `candidate/E0/D` 开始；没有客户调用、持续交付、Token/API收入等公司级审核证据，因此A/B/C保持为0。D池不进入正式推荐或回测，本记录不构成投资建议。
