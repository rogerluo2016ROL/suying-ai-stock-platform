# 毕师傅硬核科技趋势启动四轴增强 UAT 记录

## 1. 结论

- Feature: 毕师傅硬核科技趋势启动 V13 四轴增强
- Date: 2026-06-24
- Stage: Self-UAT
- Branch: `feature/suying-ai-stock-platform`
- Related commits: `4e84199`, `1365da1`, `fdd7bb2`, `e2edd4e`, `32c66ee`, `33bbbc3`
- Verdict: Pass

本轮把策略输出从单一总分扩展为四轴解释：启动质量、点火爆发、硬科技确信度、可解释原因。后端真实 PG 数据、前端组件测试、浏览器展开走查、UAT 前端代理路径都已验证。追加赛道归因收窄后，通信主线公司只在证据文本里顺带出现“芯片”时，不再被覆盖成半导体 core。

## 2. 改动范围

| Area | File | Change |
|---|---|---|
| 策略设计 | `docs/superpowers/specs/2026-06-24-bi-trend-hard-tech-four-axis-design.md` | 记录四轴增强方案和边界 |
| 因子引擎 | `packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py` | 新增启动质量、点火爆发、硬科技确信度和解释输出 |
| 因子测试 | `packages/kronos-factors/tests/test_bi_trend_four_axis.py` | 覆盖四轴字段、风险旗标、执行计划赛道和泛关键词覆盖边界 |
| 前端展示 | `frontend/src/pages/Screener.tsx` | 名称列展示硬科技赛道和层级；展开行展示四轴解释 |
| 前端测试 | `frontend/src/__tests__/Screener.test.tsx` | 覆盖四轴标签和展开详情 |
| UAT 启动 | `frontend/proxyTargets.ts`, `frontend/package.json`, `frontend/vite.config.ts` | 新增 `npm run dev:uat`，固定代理到 19001/18001 |

## 3. 测试证据

| Scope | Command | Result |
|---|---|---:|
| 因子四轴聚焦测试 | `cd packages/kronos-factors && pytest tests/test_bi_trend_four_axis.py -v` | 8 passed |
| 因子包全量测试 | `cd packages/kronos-factors && pytest tests/ -v` | 80 passed |
| 真实 PG 方案生成抽样 | `KRONOS_PG_URL=... PYTHONPATH=packages/kronos-factors .venv/bin/python -c "<run bi trend + generate plan>"` | 永鼎股份=通信 strategic；执行计划使用 refined track |
| 前端 focused 四轴测试 | `cd frontend && npx vitest run src/__tests__/Screener.test.tsx` | passed |
| 前端代理配置测试 | `cd frontend && npx vitest run src/__tests__/vite-config.test.ts` | 2 passed |
| 前端全量测试 | `cd frontend && npx vitest run` | 56 passed |
| TypeScript | `cd frontend && npx tsc -b --noEmit` | passed |
| 前端 build | `cd frontend && npm run build` | passed, Vite chunk size warning only |
| UAT 代理 | `cd frontend && npm run dev:uat` | 3002 served, screener proxy hit 18001 |

## 4. 真实数据样例

UAT 通过 `POST /api/v1/screener/run?mode=bi_trend_launch&top_n=5` 取真实 PG 数据。返回体包含 `hard_tech`、`factor_breakdown`、`entry_reason`、`risk_flags`、`power_flags`。

最新真实 PG 抽样结果：

| Rank | Code | Name | Track | Tier | Execution plan track | Note |
|---:|---|---|---|---|---|---|
| 1 | 002281 | 光迅科技 | AI算力 | core | AI算力 | 旧 `hard_tech_track` 为通信，执行计划已优先使用 refined track |
| 2 | 600105 | 永鼎股份 | 通信 | strategic | 通信 | 证据文本顺带出现“芯片”时，未覆盖成半导体 core |
| 3 | 003009 | 中天火箭 | 军工 | strategic | 军工 | 赛道和执行计划一致 |
| 4 | 600862 | 中航高科 | 军工 | strategic | 军工 | 赛道和执行计划一致 |
| 5 | 688584 | 上海合晶 | 半导体 | core | 半导体 | 半导体主线保持 core |

光迅科技的展开详情在浏览器中显示：

```text
硬科技: AI算力(core)；风险: late_rebound、ma20_extension
启动质量 -7.0
点火爆发 0.0
硬科技 4.0
late_rebound
ma20_extension
算力
芯片
通信
```

## 5. 前端 UAT 路径

推荐用 UAT 代理脚本验证四轴链路：

```bash
cd frontend
npm run dev:uat
```

启动后打开：

```text
http://127.0.0.1:3002/screener
```

操作路径：

1. 选择 `毕师傅硬核科技趋势启动 V13`
2. 点击 `开始选股`
3. 检查名称列是否展示赛道标签，例如 `AI算力 core`
4. 点击 `四轴`
5. 检查展开行是否展示 `硬科技`、`启动质量`、`点火爆发`、风险旗标和关键词

## 6. 环境注意事项

默认 `npm run dev` 仍使用 `http://localhost:8001` 作为 screener-service 代理目标。若本机 8001 跑的是旧服务，页面会缺少四轴字段。`npm run dev:uat` 固定使用 `http://127.0.0.1:18001`，该路径已验证能拿到四轴字段。

## 7. 剩余风险

| Risk | Impact | Next action |
|---|---|---|
| 跨赛道公司仍需持续抽样 | 光迅这类公司可能同时具备通信、算力、芯片证据，需要继续观察 refined track 是否符合主线叙事 | 扩充真实样本回放，重点看通信/算力/半导体交叉公司 |
| 评分仍可能奖励趋势末端票 | `late_rebound` 已能降分并解释，但部分高分票仍处于高位 | 增加真实样本复核和 OOS 质量对比 |
| 真实 UAT 认证服务不可控 | 19001 可能不是可登录 mock，浏览器验证需要可用账号或 mock auth | 保留 `dev:uat`，必要时单独启动 mock auth |

已补充回归测试 `test_generate_bi_plan_uses_refined_hard_tech_track` 和 `test_hard_tech_conviction_avoids_single_chip_keyword_overriding_communication`。执行计划现在优先使用 `hard_tech.track`，旧 `hard_tech_track` 只作为 fallback；硬科技证据文本只出现泛化“芯片”时，不会覆盖已有通信主线。

## 8. 下一步

下一轮优先做质量打磨，不再改 UI。重点检查趋势末端票和高位延伸票的 OOS 表现，先从光迅科技、永鼎股份、中航高科三只样例开始复核。
