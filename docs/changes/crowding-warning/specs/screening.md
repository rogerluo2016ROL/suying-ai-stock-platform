# Delta: screening

## ADDED Requirements

### Requirement: 选股候选标注拥挤度

The system MUST 对每只选股候选计算拥挤度 (CI = turnover_rate_f / amount / volume_ratio / pb / 20日涨幅 / 主力净流入 六成分时序滚动分位等权合成) 并在 pick 响应返回 `crowding_level` (high/medium/low) 与 `crowding_score`; 当 level 为 high/medium 时 MUST 在 `risk_flags` 追加可读标签。

#### Scenario: 高拥挤候选显示预警标签

- WHEN 某候选股拥挤度 CI > 0.90 (high)
- THEN 该 pick 的 `crowding_level="high"`, `crowding_score` 有值, 且 `risk_flags` 含 "拥挤度高(CI=...)" 标签

#### Scenario: 拥挤度计算失败不阻塞选股

- WHEN 拥挤度计算抛异常 (数据缺失 / 历史不足)
- THEN 选股正常返回, crowding 字段缺省 (try/except 降级, 不阻塞主流程)

### Requirement: 拥挤度批量扫描预警

The system MUST 提供 `POST /api/v1/alert/crowding-scan`, 对指定板块 (默认科创板 688) 扫描当日 high/medium 拥挤标的, 逐个推送 alert (app + 飞书), 科创板 (688) 加 ⭐ 标注。

#### Scenario: 盘后扫描科创板高拥挤

- WHEN `POST /crowding-scan?board=688&level=high&channel=app,feishu`
- THEN 返回 high 拥挤票列表 (含 code/level/ci_score/is_kechuang) + 推送飞书卡片, 响应含 `n_warnings` / `n_pushed_feishu`
