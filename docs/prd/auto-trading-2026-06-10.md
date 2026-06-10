# Auto Trading — 量化自动交易 spec

> PRD AC-10.6~10.8 + AC-11.5~11.6 | 2026-06-10

## Scope
从确认方案 → 自动生成量化策略 → 自动执行买卖（模拟+实盘）。
用户可自定义策略条件，可暂停/恢复/终止。

## Components
1. **Strategy Generator**: Scheme → Strategy (买入条件/卖出条件/仓位/风控)
2. **Strategy Executor**: 定时检查条件 → 触发交易
3. **Strategy Monitor**: 实时状态、持仓、调仓日志
4. **Strategy Builder**: 用户自定义策略编辑器
