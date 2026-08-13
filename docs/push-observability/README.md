# 推送系统观测台（Push Observability）

投研 4 个飞书推送任务的统一可观测性：指标采集 → 飞书 Base → 妙搭仪表盘 → 日汇总卡片。
默认进当日页，可选日期查历史；卡片与仪表盘均显式标注 **数据更新时点**。

## 架构

```
4 个推送任务(研究管线/具身刷新/screener/告警)
   │ 各自在发送/送达环节调 push_telemetry.record(task, ...)
   ▼  tools/push_telemetry.py（双 adapter：lark-cli 优先，OpenAPI 兜底；
   │   按 (date,task) delta-merge，重算 status/health_score，刷新 data_updated_at）
飞书 Base · push_metrics（base_token 见 configs/push_observability.json，32 行 seed）
   │
   ├─→ tools/sync_push_metrics_to_dashboard.py  定期镜像 Base → 妙搭应用自有 DB
   │       （妙搭 /api/* 平台层挡机器写入，故用 lark-cli +db-execute 走 user 鉴权）
   │
   ├─→ 妙搭仪表盘应用 app_17byxpygds0（NestJS + React）
   │     https://xcnl9dvruj6a.feishuapp.com/app/app_17byxpygds0
   │     可见范围：两个投研群（AI 投研分析 / AI 投研测试）
   │
   └─→ tools/send_push_daily_card.py  日汇总卡片 → AI 投研测试群
         （header 色=系统健康度，结论先行 + KPI + 任务状态点 + 数据时点 + 跳仪表盘按钮）
```

## 关键文件

| 文件 | 作用 |
|---|---|
| `configs/push_observability.json` | Base token / table_id / 妙搭 app_id / dashboard_url / chat_id |
| `tools/push_telemetry.py` | 统一埋点 helper（record / delta-merge / status+health / 双 adapter） |
| `tools/sync_push_metrics_to_dashboard.py` | Base → 妙搭应用 DB 镜像 |
| `tools/send_push_daily_card.py` | 日汇总交互卡片 |
| `tools/tests/test_push_telemetry.py` | 纯逻辑单测（compute_status_health + _merge，12 例） |
| `push-ops-dashboard/`（仓外） | 妙搭全栈应用源码（NestJS server + React client） |

## 接入点（4 任务）

| 任务 | 文件 | 钩点 |
|---|---|---|
| 研究管线 | `tools/run_research_pipeline.py` | `_record_push_telemetry` 在 `deliver_feishu_messages` 聚合后 |
| 具身刷新 | `tools/embodied_refresh/delivery.py` | `deliver_change_batch` 算完 summary 后 |
| 告警 | `services/alert-service/app/feishu_notifier.py` | `notify()` 计时 + `_record_alert_metric` |
| screener | `services/screener-service/app/lark_bot.py` | `send_text_to_chat` 包装 `_impl` + `_record_screener_metric` |

> 埋点全部 try/except 包裹，**永不抛错**，不影响推送主路径。

## 生产调度（建议 crontab，需用户确认后添加）

```cron
# 每 10 分钟：Base → 妙搭应用 DB（让仪表盘随任务运行刷新）
*/10 * * * * cd /Users/rogerluo/程序目录/K线大模型 && /usr/bin/python3 tools/sync_push_metrics_to_dashboard.py >> logs/push_sync.log 2>&1
# 每天 20:00：发观测日报卡片到 AI 投研测试
0 20 * * * cd /Users/rogerluo/程序目录/K线大模型 && /usr/bin/python3 tools/send_push_daily_card.py >> logs/push_card.log 2>&1
```

## 运行 / 验证

```bash
# 手动记一笔指标（任意任务）
python3 tools/push_telemetry.py record --task research_pipeline --push 1 --success 1
# 镜像一次
python3 tools/sync_push_metrics_to_dashboard.py
# 发当日卡片（dry-run 先看 JSON）
python3 tools/send_push_daily_card.py --dry-run
python3 tools/send_push_daily_card.py
# 单测
python3 -m pytest tools/tests/test_push_telemetry.py -v
```

## 已知项 / 后续

- **妙搭 /api/* 平台层鉴权**：机器（无 Feishu 会话）无法直接 POST ingest；故走"push_telemetry 写 Base + 镜像脚本写应用 DB"两段式。lark-cli 凭 user 鉴权可写两边。
- **告警/screener 容器内写入**：helper 优先 lark-cli，容器若无 lark-cli 则走 OpenAPI adapter（需服务的 LARK_APP_ID/SECRET 对 Base 有写权限——dev 已通，生产容器需确认 lark-cli 存在或 OpenAPI 权限）。
- **仪表盘 /api/dashboard 仅我未 curl 验证**（平台挡无会话请求）；数据已灌、构建通过、逻辑与已测 helper 同构——登录的投研群成员打开链接即可见。
- **cron 已挂**：镜像 `*/10 * * * *` + 日卡 `0 20 * * *`（macOS crontab，PATH 含 nvm lark-cli bin）。⚠️ 安装时用了替换式写入，若你之前有其他 cron 条目请 `crontab -l` 核对。
- **已完成打磨**：`?date=` 深链直达当日页；仪表盘「导出 CSV」；告警卡补「时间」字段（分辨实时/积压）；历史日期选择。
- **可选后续**：明细表行下钻 run 详情；选股文本卡补 `数据时点`（日卡已有）。
- Base 数据当前为 **8 天 × 4 任务演示 seed**（08-05..08-12），真实任务运行后会增量合并/覆盖。
