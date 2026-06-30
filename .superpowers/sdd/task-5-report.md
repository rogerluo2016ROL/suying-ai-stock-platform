# Task 5 Report: Register Engine And Backtest-Service Mode

## 实现内容
- 在 `packages/kronos-factors/kronos_factors/engine/__init__.py` 导出 `CbAuctionT0Engine`。
- 在 `services/backtest-service/app/routes.py` 的 `run_cb_backtest` 增加 `mode="cb_auction_t0"` 分支。
- 对 `CbAuctionT0Engine.run()` 的返回值按 `raw_result.get("bonds", [])` 取出 picks，再进入后续回测流程。
- 未改动 `cb_floor`、`cb_intraday`、`cb_auction` 的现有行为。

## TDD 过程
### RED
命令：
```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_auction_t0.py::test_engine_package_exports_cb_auction_t0 -q
```
结果：
- 失败，报 `ImportError: cannot import name 'CbAuctionT0Engine' from 'kronos_factors.engine'`

### GREEN
命令：
```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_auction_t0.py -q
python3 -m py_compile services/backtest-service/app/routes.py
```
结果：
- 测试通过：`11 passed`
- 编译通过：`python3 -m py_compile` 退出码 0

## 文件变更
- `packages/kronos-factors/kronos_factors/engine/__init__.py`
- `services/backtest-service/app/routes.py`
- `packages/kronos-factors/tests/test_cb_auction_t0.py`

## 自查结果
- 新增包级导出后，测试文件里的包导入通过。
- `cb_auction_t0` 仅在新增分支中走 `bonds`，没有影响其他三种 CB 模式。
- 路由文件通过语法编译检查。

## 疑虑
- 任务要求里写的是 `python -m py_compile`，但当前环境没有 `python` 命令，只能用 `python3` 做等价检查。
