# Task 2 执行报告（Result Assembly And Theme Sorting）

## 实现内容
- 在 `packages/kronos-factors/kronos_factors/engine/cb_auction_t0.py` 中新增 `CbAuctionT0Engine._assemble_result(...)`，仅处理内存中的候选结果组装，不访问数据库。
- 在 `CbAuctionT0Engine` 中新增 `_relation_reason(...)`，用于输出题材关系文案。
- `_assemble_result` 逻辑包含：
  - 以 `cb_code` 去重并合并重复转债：合并 `matched_concepts` 与 `trigger_sources`，并对金额、触发股数量、概念覆盖度等字段取并集/最大/最小策略。
  - 生成 `is_direct_trigger`、`theme_score`、`risk_notes`、`remain_size_yi`、`code`、`name`、`relation_reason`。
  - 按题材相关性排序：先按是否直接触发股、命中题材数、触发股数、匹配封单额、概念规模宽度排序，最后补充代码顺序，支持 `top_n` 截断。
  - 返回统一结构：`model`、`trade_date`、`trigger_stocks`、`concepts`、`bonds`、`rejections`（可为空）。
- 保持 `run()` 行为不变（仍为现有 stub 行为）。

## 测试命令和结果
- 命令：
  - `bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_auction_t0.py -q`
- 结果：
  - 失败阶段（新增两个测试前）：`AttributeError: 'CbAuctionT0Engine' object has no attribute '_assemble_result'`
  - 通过阶段（实现后）：`6 passed in ...`（本次运行显示 `...... [100%]`）

## TDD RED/GREEN 证据
- RED：首次运行新增测试时有 2 个失败，均来自 `_assemble_result` 不存在。
- GREEN：补齐 `_assemble_result` 与 `_relation_reason` 后，测试全部通过。

## 文件变更
- `packages/kronos-factors/kronos_factors/engine/cb_auction_t0.py`
- `packages/kronos-factors/tests/test_cb_auction_t0.py`

## 自查结果
- 核对了排序逻辑与题材去重行为：重复转债合并后 `matched_concepts`、`trigger_sources` 已去重并有序。
- 风险信息保留为注释字段（`risk_notes`），未作为硬过滤条件。
- 只使用同花顺相关概念字段进行组装/排序依据，不引入交易便利性维度。
- 未改动 `run()` 与其他模型行为。

## 疑虑
- 当前 `CbAuctionT0Engine.run()` 仍是空壳返回，仍需后续 Task 3/4 用真实触发与题材数据接入 `_assemble_result`。
