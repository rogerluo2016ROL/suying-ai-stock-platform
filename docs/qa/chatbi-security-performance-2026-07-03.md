# ChatBI 性能和安全验收报告

日期：2026-07-04

## 验收范围

```text
独立移动端 ChatBI Java 后端
标准 SSE 问答接口 /api/v1/chatbi/messages/stream
K线大模型工具网关 http://127.0.0.1:18088/api/v1
30 问核心问题集
权限上下文拦截
密钥和敏感信息扫描
```

## 性能结果

数据来源：

```text
outputs/chatbi_uat/chatbi_uat_30q_results.json
```

冷缓存统计结果：

```text
样本数=30
通过=30
部分通过=0
不通过=0
最小耗时=180ms
最大耗时=11200ms
平均耗时=3545.57ms
P50=292.5ms
P90=9178ms
P95=9641ms
<=2秒=19条
>3秒=11条
```

热缓存统计结果：

```text
通过=30
部分通过=0
不通过=0
最小耗时=164ms
最大耗时=313ms
平均耗时=251.37ms
P50=275.5ms
P90=303ms
P95=310ms
<=2秒=30条
>3秒=0条
```

结论：

```text
普通模型清单、数据质量、模型共振占位接口基本在 2 秒内。
产业链候选、公司证据链、报告草稿类问题依赖 supply-chain candidate-ranking 工具，冷缓存首次计算约 9-11 秒。
新增 5 分钟工具响应内存缓存后，热缓存 30 问 P95=310ms，达到普通工具查询 P95 <= 2 秒目标。
服务端已新增 ChatBI SSE 专用 Async TaskExecutor，未再出现 SimpleAsyncTaskExecutor under load 警告。
```

后续优化项：

```text
1. 给 supply-chain candidate-ranking 增加持久化缓存或预聚合表，降低冷缓存耗时。
2. 区分快速回答和深度思考：快速回答优先返回缓存摘要，深度思考再补全证据。
3. 把公司证据链拆成按公司代码查询，避免每次拉全候选榜。
4. 报告导出进入异步任务，先返回任务进度，再生成文件。
5. 内存缓存后续改成 Redis 或本地 Caffeine，支持多实例部署和容量限制。
```

## 安全结果

执行范围：

```text
chatbi-workspace/backend-java
chatbi-workspace/frontend-vue
db/migration/chatbi
docs/prd/chatbi-standalone-reuse-implementation-plan-2026-07-03.md
docs/qa/chatbi-uat-report-2026-07-03.md
```

扫描结论：

```text
未发现 Bearer app- 明文生产密钥。
未发现真实 DeepSeek/GLM/OpenAI API Key。
数据库密码已改为环境变量占位。
扫描命中 password、secret、Authorization、api_key_ref、agentKey 等字段名，主要来自 RuoYi 基础用户体系、旧 Dify/RAGFlow 兼容字段、配置占位和文档命令，不是明文生产密钥。
```

需要保留的风险说明：

```text
旧 AiAgentType.agentKey 字段仍存在于原后端兼容模块和 Mapper 中，虽然本轮标准 ChatBI API 不再依赖 Dify，但旧兼容代码尚未彻底删除。
application.yml 中 CHATBI_DB_PASSWORD 默认值仍为本地开发占位 kronos，生产部署必须由环境变量覆盖。
CHATBI_TOKEN_SECRET 必须由部署环境提供，不能使用 UAT 的 uat-secret。
```

## 权限结果

权限矩阵：

```text
chatbi.supply_chain -> 产业链候选、公司证据链
chatbi.report_export -> 报告导出
chatbi.model -> 选股、选债、模型共振、无票诊断
chatbi.admin -> 全部放行
```

实测结果：

```text
无 chatbi.supply_chain 权限查询 AI算力候选公司Top5 -> blocked
无 chatbi.report_export 权限生成中际旭创产业链拆解报告 -> blocked
chatbi.admin 查询 AI算力候选公司Top5 -> ready
```

结论：权限拦截通过。当前权限从请求上下文读取；企业平台真实接入后，需要由平台身份映射层注入权限上下文。
