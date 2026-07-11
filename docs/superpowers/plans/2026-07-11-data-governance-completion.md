# Data Governance Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成参数型接口治理、失效接口标记、业务表字段修复和可重复的增量采集验证。

**Architecture:** 保留 Tushare 原始层作为完整落地层；业务层继续由现有 ETL 写入；调度器只负责检测缺口并触发已有同步函数。参数型 API 使用显式配置，失效 API 保留审计记录但不进入运行队列。

**Tech Stack:** Python, Tushare SDK, PostgreSQL, pytest, 现有 data-service scheduler。

## Global Constraints

- 不伪造缺失数据；参数不足时记录 `requires_params`。
- 不删除已有数据；写入必须幂等。
- 所有日期范围和最新日期以数据库核验结果为准。

### Task 1: 参数与失效接口治理

- [ ] 增加参数配置并为参数型接口执行可复现采集。
- [ ] 将确认为失效的接口记录为 `unsupported_api`，从自动重试队列排除。
- [ ] 运行状态统计并更新报告。

### Task 2: 业务表 schema 与清洗

- [ ] 对照 ETL 字段和 PostgreSQL 实际字段，补齐必要字段。
- [ ] 修复日期 `nan`、大整数和缺列写入问题。
- [ ] 重跑受影响业务表并核验行数和日期范围。

### Task 3: 增量调度与验证

- [ ] 接入按最新日期/缺口计算的增量采集。
- [ ] 增加失败重试和状态记录。
- [ ] 运行 focused tests、状态检查和索引检查。
