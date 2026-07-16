# 具身智能每日刷新真实验收（2026-07-17）

> 上线/回滚提醒：Alembic 036/037 的 `downgrade` 会删除刷新运行、证据变动、审计快照、送达记录、映射冲突和迁移历史。生产回滚前必须先备份这些表；未备份执行 downgrade 会永久丢失审计历史，不能作为无损回滚方案。

## 结论

`[COMPUTED]` **通过，带存量数据关注项**。审查阻断问题已修复并按当前日 `2026-07-17`（Asia/Shanghai）重新执行。最终批次 `d0ff8ffd-59c7-4297-8236-b263950627d8` 产生 4 条可追溯的 P3 新候选，0 条 P0–P2，因此三个配置群均未发送。

## 数据截止

同步前：公告 2026-07-15（47,010 行）、互动问答 2026-07-15（225,641 行）、研报 2026-06-24（357,124 行）、画像 2026-07-03 00:47:26（6,294 行）、主营 2026-03-31（379 行）。调用项目既有同步后：公告 2026-07-17（54,902 行）、互动问答 2026-07-17（247,476 行）、主营 2026-03-31（61,232 行）。研报接口返回 12,495 但因空 code 写入 0；画像返回 6,294 但因整数越界写入 0，截止未推进。未用生成内容补齐失败源。

## 迁移、基线与定向清理

- Alembic `035 -> 036 -> 037` 成功；037 增加冲突 proposed-node 列表。
- 原始基线：candidate 21、verified 31、weak_evidence 2；L1–L8 为 `1/2/8/12/16/7/6/7`。
- 审计仍有 4 组重复节点、1 个孤儿节点、18 条缺失节点映射、31 条 verified 映射没有全量 approved 证据。
- 定向清理仅引用错误批次 `45b69356-30be-4922-a2c5-0225e98a9a1d`：清理前 run 1、该批 from_status=NULL 映射 11、transition 11、conflict 4,498、snapshot 6、cursor 5；清理后以上全部为 0，未按代码或全表范围删除存量。
- 修正证据日期后再次定向清理中间批次 `0202dced-d202-4d48-9b41-73425b36ded6`：仅删除该批 4 个新映射、19 个 transition fingerprint 对应事件、4 changes、922 conflicts、6 snapshots、5 cursors 与 1 run；首个事务因 FK 顺序错误整体回滚，确认无部分删除后调整为先删事件再删映射并成功提交。

## Dry-run 审查

dry-run 与 apply 使用同一 mapping state machine；dry-run 仅做内存 projection，不写 run、event、mapping、transition、conflict、snapshot 或 delivery。

dry-run 明确输出 4 条将创建候选与 3 条 node mismatch：

| 代码 | 节点 | 来源与日期 | 处置 |
|---|---|---|---|
| 000559 | `18C-L4-...-6b06d57719` | profile，2026-06-25 | candidate / pending_review |
| 301696 | `18C-L4-...-b446b4c6ef` | 公司互动回答 16 条，2026-06-17 至 2026-07-01 | candidate / pending_review；回答明确销售关节模组、无框力矩电机等，但不自动 verified |
| 605088 | `18C-L4-...-bom_2d000c0657` | research，2025-04-07 | candidate / pending_review；来源较旧 |
| 920418 | `18C-L4-...-6b06d57719` | profile，2026-06-25 | candidate / pending_review |

3 条节点不一致涉及 002048、002708、300421，全部 pending_review。002457 因仅命中宽泛“感知系统”被剔除；002765 的关键词只出现在投资者问题、公司回答未确认机器人业务，已剔除。非六位证券代码（包括字符串 `nan`）被拒绝。

## Apply、变化、证据与冲突

- apply 创建 4 条 candidate、4 条 pending_review transition、4 条 `new_candidate/P3` change；首批无历史 success baseline 时正确使用空 success baseline，不再天然得到 0 changes。
- `business_tag_mapping.evidence_ids` 全部保存稳定 fingerprint event_id，不再保存 source_id。4 个映射分别有 1、16、1、1 个 evidence_ids，数据库 join 数完全一致；source_type、source_id、event_date 均保留。
- 本批共持久化 34 个稳定 evidence events（含待审冲突相关事件），同 fingerprint 不重复。
- 复审时定向删除本批原有 919 条 ambiguous rows，用冻结的五源输入重建。冻结输入产生 977 个原始歧义命中，按 `chain + code + evidence_fingerprint + sorted proposed_nodes` 得到 910 个唯一事件；持久化 910 条，主键、证据复合键和期望集合均为 910，missing=0、extra=0。源级一一对应为 interact_qa 849、profile 13、research 48。空 source_id 为 0，每条均保存至少 2 个 proposed_node_ids；另有 node_mismatch 3 条，总冲突 913，均 pending_review。
- candidate 总数由 21 增至 25；verified 31、weak_evidence 2 不变，没有手工或自动越过审核门。

## 榜单与飞书

正式 Top3 不变：创元科技、秦川机床、国机精工；观察 Top3 不变：宁波华翔、远东传动、万里扬。按已确认的保守规则，4 条变化因六维输入不完整得到 `score=None/P3`，不是完成了六维实评分；P0/P1/P2 均为 0，因此 `delivery_attempted=false`、delivery rows 0、message_id 0，三个群未发送。

## 同批幂等

冻结同一输入/游标后第二次运行直接返回同一 terminal run，不重写 summary。重跑时为 event 34、mapping 4、transition 4、snapshot 6、delivery 0，均无重复；复审后 ambiguous 冲突集合重建为 910 条，加 3 条 node mismatch 后最终 conflict 913。

## 测试与可复现命令

- 具身刷新聚焦套件：100 passed、1 skipped。
- scheduled research：10 passed。可复现命令为 `PYTHONPATH=services/data-service bash tools/codex-lowio.sh py services/data-service/tests/test_scheduled_research.py -q`。
- priority supply chains + research manifest：32 passed。
- `git diff --check` 与 JSON 解析通过。

## 存量关注项

1. 研报同步空 code、画像同步整数越界仍需由上游同步模块修复。
2. 31 条存量 verified 映射证据审核不闭合，正式榜单 evidence_quality 为 0，不应解释为本次新确认。
3. 4 组重复节点、1 个孤儿节点、18 条缺失节点映射仍待治理。

最终运行摘要：`outputs/embodied_refresh/d0ff8ffd-59c7-4297-8236-b263950627d8/result.json`。
