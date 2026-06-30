# Task 3 报告：Add PostgreSQL Fetch Pipeline

## 实现内容
- 给 `CbAuctionT0Engine` 补齐了 `run()` 编排：按顺序调用 `_fetch_effective_trade_date`、`_fetch_previous_trade_date`、`_fetch_trigger_stocks`、`_fetch_concepts`、`_fetch_bonds`。
- 新增了 5 个 PostgreSQL fetch helper，覆盖：
  - 竞价封板触发股
  - 同花顺概念映射
  - 转债映射
  - 交易日/前一交易日推导
- 保持原有 `_assemble_result` 和 `_relation_reason` 行为不变。
- 按 brief 口径保留：
  - `limit_type = 'U'`
  - `first_time IS NOT NULL`
  - `first_time <= '09:30:00'`
  - `fd_amount > 1_000_000_000`
  - 前一交易日同股已涨停则拒绝
  - 缺少 `fd_amount` 直接拒绝，不估算封单金额
  - 转债侧不按强赎、溢价率、成交额、剩余规模、退市日期做硬过滤

## TDD 证据
### RED
命令：
```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_auction_t0.py -q -k test_run_assembles_fetcher_outputs_without_postgres
```
结果：
```text
F ... AttributeError: <kronos_factors.engine.cb_auction_t0.CbAuctionT0Engine object at ...> has no attribute '_fetch_effective_trade_date'
```

### GREEN
同一命令在实现后通过：
```text
. [100%]
```

### 回归确认
命令：
```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_auction_t0.py -q
```
结果：
```text
......... [100%]
```

## 测试命令和结果
- `bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_auction_t0.py -q -k test_run_assembles_fetcher_outputs_without_postgres`
  - 先失败，后通过
- `bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_auction_t0.py -q`
  - 通过，9 个测试全绿

## 文件变更
- `packages/kronos-factors/kronos_factors/engine/cb_auction_t0.py`
- `packages/kronos-factors/tests/test_cb_auction_t0.py`

## 自查结果
- `run()` 现在会真正走 fetch 编排，不再返回空壳结果。
- patched fetchers + fake connection 的单测已覆盖，不依赖本机 PostgreSQL。
- 现有 8 个 helper/assembly 测试未回归。

## 疑虑
- 无额外疑虑；本任务按要求没有连接真实 PostgreSQL，当前验证范围已覆盖 brief 要求的编排逻辑。
