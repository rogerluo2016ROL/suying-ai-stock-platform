package com.ds.cockpit.screen.system.service.chatbi.impl;

import cn.hutool.core.lang.UUID;
import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONArray;
import com.alibaba.fastjson2.JSONObject;
import com.ds.cockpit.screen.common.core.domain.AjaxResult;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ChatBIAgentVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ChatBIFeedbackRequest;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ChatBIRequest;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ChatBISessionVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ChatBIStreamEvent;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.IntentResult;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ToolCallResponse;
import com.ds.cockpit.screen.system.service.chatbi.ChatBILLMGatewayService;
import com.ds.cockpit.screen.system.service.chatbi.ChatBIConversationStore;
import com.ds.cockpit.screen.system.service.chatbi.ChatBIOrchestratorService;
import com.ds.cockpit.screen.system.service.chatbi.IntentRouter;
import com.ds.cockpit.screen.system.service.chatbi.ToolGatewayClient;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

import javax.annotation.Resource;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class ChatBIOrchestratorServiceImpl implements ChatBIOrchestratorService {
    private final Map<String, ChatBISessionVO> sessionStore = new ConcurrentHashMap<>();

    @Resource
    private IntentRouter intentRouter;

    @Resource
    private ToolGatewayClient toolGatewayClient;

    @Resource
    private ChatBIConversationStore conversationStore;

    @Resource
    private ChatBILLMGatewayService llmGatewayService;

    @Override
    public ChatBISessionVO createSession() {
        return createSession(null);
    }

    private ChatBISessionVO createSession(ChatBIRequest request) {
        String now = LocalDateTime.now().toString();
        ChatBISessionVO session = new ChatBISessionVO();
        session.setId(UUID.randomUUID().toString());
        session.setSessionId(session.getId());
        session.setTitle("新对话");
        session.setCreatedAt(now);
        session.setUpdatedAt(now);
        sessionStore.put(session.getSessionId(), session);
        conversationStore.saveSession(session, request);
        return session;
    }

    @Override
    public AjaxResult prepareMessage(ChatBIRequest request) {
        String messageId = resolveMessageId(request);
        String sessionId = ensureSessionId(request);
        conversationStore.savePreparedMessage(sessionId, messageId, request);
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("id", messageId);
        data.put("messageId", messageId);
        data.put("sessionId", sessionId);
        data.put("question", request.normalizedQuestion());
        data.put("answerMode", request.normalizedAnswerMode());
        return AjaxResult.success(data);
    }

    @Override
    public Flux<AjaxResult> stream(ChatBIRequest request) {
        String question = request.normalizedQuestion();
        String sessionId = ensureSessionId(request);
        String messageId = resolveMessageId(request);
        conversationStore.savePreparedMessage(sessionId, messageId, request);
        callIntentRecognitionIfNeeded(request, sessionId, messageId, question);
        IntentResult intent = intentRouter.route(question);
        String deniedReason = denyReason(request, intent.getIntent());
        if (deniedReason != null) {
            String answer = "结论：权限不足，已拒绝执行。\n\n"
                    + "问题：" + question + "\n\n"
                    + "限制说明：" + deniedReason + "\n"
                    + "数据源状态：blocked";
            conversationStore.saveCompletedMessage(sessionId, messageId, answer, intent.getIntent());
            List<AjaxResult> deniedEvents = new ArrayList<>();
            deniedEvents.add(event("node_started", "问题识别", "", "", "1", sessionId, messageId));
            deniedEvents.add(event("node_finished", "问题识别", "6ms", intent.getIntent() + "，" + intent.getReason(), "1", sessionId, messageId));
            deniedEvents.add(event("node_finished", "权限校验", "1ms", deniedReason, "1", sessionId, messageId));
            deniedEvents.add(event("message_delta", "回答", "", answer, "1", sessionId, messageId));
            deniedEvents.add(event("done", "生成完成", "0ms", "已拒绝", "1", sessionId, messageId));
            for (int i = 0; i < deniedEvents.size(); i++) {
                Object data = deniedEvents.get(i).get(AjaxResult.DATA_TAG);
                if (data instanceof ChatBIStreamEvent) {
                    conversationStore.saveEvent(sessionId, messageId, i + 1, (ChatBIStreamEvent) data);
                }
            }
            return Flux.fromIterable(deniedEvents).delayElements(Duration.ofMillis(20));
        }
        ToolCallResponse toolResponse = toolGatewayClient.callByIntent(intent.getIntent(), question);
        String generationNodeType = generationNodeType(question);
        Map<String, Object> llmResponse = callGenerationIfNeeded(request, sessionId, messageId, question, intent, toolResponse, generationNodeType);
        String answer = buildAnswer(question, request.normalizedAnswerMode(), intent, toolResponse, llmResponse);
        conversationStore.saveToolCall(sessionId, messageId, intent.getIntent(), toolResponse);
        conversationStore.saveCompletedMessage(sessionId, messageId, answer, intent.getIntent());

        List<AjaxResult> events = new ArrayList<>();
        events.add(event("node_started", "问题识别", "", "", "1", sessionId, messageId));
        events.add(event("node_finished", "问题识别", "6ms", intent.getIntent() + "，" + intent.getReason(), "1", sessionId, messageId));
        events.add(event("node_started", "工具选择", "", "", "1", sessionId, messageId));
        events.add(event("node_finished", "工具选择", "12ms", toolResponse.getSourceStatus(), "1", sessionId, messageId));
        if ("deep".equals(request.normalizedAnswerMode())) {
            events.add(event("node_started", "数据查询", "", "", "1", sessionId, messageId));
            events.add(event("node_finished", "数据查询", "", toolResponse.getMessage(), "1", sessionId, messageId));
            events.add(event("node_started", "report_generation".equals(generationNodeType) ? "报告生成" : "答案生成", "", "", "1", sessionId, messageId));
        }
        events.add(event("message_delta", "回答", "", answer, "1", sessionId, messageId));
        events.add(event("done", "生成完成", "0ms", "生成完成", "1", sessionId, messageId));
        for (int i = 0; i < events.size(); i++) {
            Object data = events.get(i).get(AjaxResult.DATA_TAG);
            if (data instanceof ChatBIStreamEvent) {
                conversationStore.saveEvent(sessionId, messageId, i + 1, (ChatBIStreamEvent) data);
            }
        }
        return Flux.fromIterable(events).delayElements(Duration.ofMillis(20));
    }

    @Override
    public AjaxResult feedback(ChatBIFeedbackRequest request) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("messageId", request.getMessageId());
        data.put("rating", request.getRating());
        data.put("received", true);
        conversationStore.saveFeedback(request);
        return AjaxResult.success(data);
    }

    @Override
    public List<ChatBIAgentVO> agents() {
        List<ChatBIAgentVO> agents = new ArrayList<>();
        agents.add(new ChatBIAgentVO("default", "investment_research", "投研 ChatBI", "产业链、选股、选债和证据链分析"));
        agents.add(new ChatBIAgentVO("quick", "template_query", "快速回答", "模板化查询，只返回结果"));
        agents.add(new ChatBIAgentVO("deep", "deep_research", "深度思考", "模型编排、证据链和结构化分析"));
        return agents;
    }

    @Override
    public List<ChatBISessionVO> sessions() {
        List<ChatBISessionVO> sessions = conversationStore.listSessions();
        if (!sessions.isEmpty()) {
            return sessions;
        }
        return new ArrayList<>(sessionStore.values());
    }

    @Override
    public AjaxResult sessionDetail(String sessionId) {
        ChatBISessionVO session = conversationStore.findSession(sessionId);
        if (session == null) {
            session = sessionStore.get(sessionId);
        }
        if (session == null) {
            return AjaxResult.error("会话不存在或尚未持久化");
        }
        return AjaxResult.success(session);
    }

    private String ensureSessionId(ChatBIRequest request) {
        String sessionId = request.normalizedSessionId();
        if (sessionId.length() == 0) {
            sessionId = createSession(request).getSessionId();
        } else if (!sessionStore.containsKey(sessionId) && conversationStore.findSession(sessionId) == null) {
            ChatBISessionVO session = new ChatBISessionVO();
            session.setId(sessionId);
            session.setSessionId(sessionId);
            session.setTitle("历史会话");
            session.setCreatedAt(LocalDateTime.now().toString());
            session.setUpdatedAt(LocalDateTime.now().toString());
            sessionStore.put(sessionId, session);
            conversationStore.saveSession(session, request);
        }
        return sessionId;
    }

    private String resolveMessageId(ChatBIRequest request) {
        if (request.getMessageId() != null && request.getMessageId().trim().length() > 0) {
            return request.getMessageId().trim();
        }
        if (request.getId() != null) {
            return String.valueOf(request.getId());
        }
        return UUID.randomUUID().toString();
    }

    private AjaxResult event(String type, String node, String times, String message, String isShow, String sessionId, String messageId) {
        ChatBIStreamEvent event = ChatBIStreamEvent.of(type, node, times, message, isShow);
        event.setSessionId(sessionId);
        event.setMessageId(messageId);
        return AjaxResult.success(event);
    }

    private Map<String, Object> callIntentRecognitionIfNeeded(ChatBIRequest request, String sessionId, String messageId, String question) {
        if (!"deep".equals(request.normalizedAnswerMode())) {
            return null;
        }
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("session_id", sessionId);
        payload.put("message_id", messageId);
        payload.put("agent_id", request.getAgentCode() == null ? "default" : request.getAgentCode());
        payload.put("node_type", "intent_recognition");
        payload.put("prompt", "请识别投研问题类型，只输出意图名称和理由。问题：" + question);
        payload.put("max_tokens", 300);
        payload.put("temperature", 0.1);
        return llmGatewayService.generate(payload);
    }

    private Map<String, Object> callGenerationIfNeeded(ChatBIRequest request, String sessionId, String messageId, String question, IntentResult intent, ToolCallResponse toolResponse, String nodeType) {
        if (!"deep".equals(request.normalizedAnswerMode())) {
            return null;
        }
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("session_id", sessionId);
        payload.put("message_id", messageId);
        payload.put("agent_id", request.getAgentCode() == null ? ("report_generation".equals(nodeType) ? "report" : "default") : request.getAgentCode());
        payload.put("node_type", nodeType);
        payload.put("prompt", "问题：" + question + "\n\n意图：" + intent.getIntent() + "\n\n工具状态：" + toolResponse.getSourceStatus() + "\n\n工具结果：" + truncate(toolResponse.getRawBody(), 6000) + "\n\n请基于以上数据生成简洁、可追溯的投研分析。");
        payload.put("max_tokens", 1200);
        payload.put("temperature", 0.2);
        return llmGatewayService.generate(payload);
    }

    private String generationNodeType(String question) {
        if (question != null && (question.contains("报告") || question.contains("研报") || question.contains("导出"))) {
            return "report_generation";
        }
        return "answer_generation";
    }

    private String buildAnswer(String question, String answerMode, IntentResult intent, ToolCallResponse toolResponse, Map<String, Object> llmResponse) {
        StringBuilder answer = new StringBuilder();
        boolean modelIntent = "stock_model_run".equals(intent.getIntent())
                || "bond_model_run".equals(intent.getIntent())
                || "no_pick_diagnosis".equals(intent.getIntent());
        if (modelIntent && toolResponse.isSuccess()) {
            answer.append("### 查询结果\n\n");
            answer.append("- 问题：").append(question).append("\n");
            answer.append("- 模式：").append("quick".equals(answerMode) ? "快速回答，只展示结果清单" : "深度思考，包含模型分析").append("\n");
            answer.append("- 数据源状态：ready\n\n");
            answer.append(formatToolResult(intent.getIntent(), toolResponse.getRawBody()));
            if ("deep".equals(answerMode)) {
                answer.append("\n\n");
                appendLlmSection(answer, llmResponse);
            }
            return answer.toString();
        }
        answer.append("结论：已识别为 ").append(intent.getIntent()).append("。");
        if ("quick".equals(answerMode)) {
            answer.append("快速回答模式只返回模板化查询结果，不展开模型分析。\n\n");
        } else {
            answer.append("深度思考模式已执行问题识别、工具选择、数据查询和答案生成节点。\n\n");
        }
        answer.append("问题：").append(question).append("\n\n");
        if (toolResponse.isSuccess()) {
            answer.append("数据源状态：ready\n");
            answer.append(formatToolResult(intent.getIntent(), toolResponse.getRawBody()));
        } else {
            answer.append("数据源状态：").append(toolResponse.getSourceStatus()).append("\n");
            answer.append("限制说明：").append(toolResponse.getMessage()).append("\n");
            answer.append("下一步建议：启动或配置 `CHATBI_TOOL_GATEWAY_BASE_URL` 指向 K线大模型 FastAPI 后重试。");
        }
        if ("deep".equals(answerMode)) {
            answer.append("\n\n");
            appendLlmSection(answer, llmResponse);
        }
        return answer.toString();
    }

    private void appendLlmSection(StringBuilder answer, Map<String, Object> llmResponse) {
        if (llmResponse == null) {
            answer.append("大模型状态：未触发。");
            return;
        }
        if ("ok".equals(String.valueOf(llmResponse.get("status")))) {
            answer.append("大模型分析：\n").append(String.valueOf(llmResponse.get("content")));
            Map usage = (Map) llmResponse.get("usage");
            if (usage != null) {
                answer.append("\n\n模型：").append(llmResponse.get("provider_id")).append("/").append(llmResponse.get("model_id"))
                        .append("，输入 tokens：").append(usage.get("input_tokens"))
                        .append("，输出 tokens：").append(usage.get("output_tokens"));
            }
            return;
        }
        answer.append("大模型状态：").append(llmResponse.get("status")).append("。")
                .append(llmResponse.get("message") == null ? "已降级为模板化分析。" : llmResponse.get("message"));
    }

    private String formatToolResult(String intent, String rawBody) {
        if ("supply_chain_ranking".equals(intent)) {
            return formatSupplyChainRanking(rawBody);
        }
        if ("company_evidence".equals(intent)) {
            return formatCompanyEvidence(rawBody);
        }
        if ("stock_model_run".equals(intent)) {
            return formatModelRunResults(rawBody, "选股");
        }
        if ("bond_model_run".equals(intent)) {
            return formatModelRunResults(rawBody, "选债");
        }
        if ("no_pick_diagnosis".equals(intent)) {
            return formatNoPickDiagnosis(rawBody);
        }
        if ("model_resonance".equals(intent)) {
            return formatModelResonance(rawBody);
        }
        if ("data_quality".equals(intent)) {
            return formatDataQuality(rawBody);
        }
        if ("report_export".equals(intent)) {
            return formatReportDraft(rawBody);
        }
        return "工具返回：" + truncate(rawBody, 1200);
    }

    private String denyReason(ChatBIRequest request, String intent) {
        String required = requiredPermission(intent);
        if (required == null) {
            return null;
        }
        Map<String, Object> context = request.getContext();
        if (context == null || !context.containsKey("permissions")) {
            return null;
        }
        Object permissions = context.get("permissions");
        if (permissions instanceof Iterable) {
            for (Object permission : (Iterable<?>) permissions) {
                if (required.equals(String.valueOf(permission)) || "chatbi.admin".equals(String.valueOf(permission))) {
                    return null;
                }
            }
        } else if (permissions instanceof String) {
            String value = (String) permissions;
            if (value.contains(required) || value.contains("chatbi.admin")) {
                return null;
            }
        }
        return "当前用户缺少权限 `" + required + "`，不能访问该类 ChatBI 能力。";
    }

    private String requiredPermission(String intent) {
        if ("supply_chain_ranking".equals(intent) || "company_evidence".equals(intent)) {
            return "chatbi.supply_chain";
        }
        if ("report_export".equals(intent)) {
            return "chatbi.report_export";
        }
        if ("stock_model_run".equals(intent) || "bond_model_run".equals(intent)
                || "model_resonance".equals(intent) || "no_pick_diagnosis".equals(intent)) {
            return "chatbi.model";
        }
        return null;
    }

    private String formatSupplyChainRanking(String rawBody) {
        try {
            JSONObject root = JSON.parseObject(rawBody);
            JSONObject summary = root.getJSONObject("summary");
            JSONArray items = root.getJSONArray("items");
            StringBuilder out = new StringBuilder();
            out.append("数据版本：").append(root.getString("version")).append("\n");
            if (summary != null) {
                out.append("覆盖范围：")
                        .append(summary.getIntValue("chain_count")).append(" 条产业链，")
                        .append(summary.getIntValue("company_chain_rows")).append(" 条公司-产业链映射，")
                        .append(summary.getIntValue("mapping_rows")).append(" 条映射记录。\n");
            }
            out.append("\n候选排序：\n");
            if (items == null || items.isEmpty()) {
                out.append("暂无候选结果。\n");
                return out.toString();
            }
            int limit = Math.min(items.size(), 5);
            for (int i = 0; i < limit; i++) {
                JSONObject item = items.getJSONObject(i);
                out.append(i + 1).append(". ")
                        .append(item.getString("name")).append("（").append(item.getString("code")).append("）")
                        .append("：").append(item.getString("signal"))
                        .append("，总分 ").append(item.getString("rank_score"))
                        .append("，三高 ").append(item.getString("three_high_total"))
                        .append("（成长 ").append(item.getString("growth_score"))
                        .append(" / 盈利 ").append(item.getString("profit_score"))
                        .append(" / 围墙 ").append(item.getString("moat_score")).append("）")
                        .append("，阶段 ").append(item.getString("research_stage"))
                        .append(" / ").append(item.getString("commercialization_stage"))
                        .append("，L8证据 ").append(toPercentText(item.getDouble("l8_match_rate")))
                        .append("，事实 ").append(item.getIntValue("fact_count")).append(" 条")
                        .append("，最新交易日 ").append(item.getString("latest_trade_date"))
                        .append("，20日涨幅 ").append(item.getString("change_20d_pct")).append("%。\n");
            }
            out.append("\n说明：快速回答只给模板化结果；深度思考会继续解释三高、阶段、证据和预期差。");
            return out.toString();
        } catch (Exception e) {
            return "工具返回：" + truncate(rawBody, 1200);
        }
    }

    private String formatCompanyEvidence(String rawBody) {
        try {
            JSONObject root = JSON.parseObject(rawBody);
            JSONArray items = root.getJSONArray("items");
            StringBuilder out = new StringBuilder();
            out.append("证据链数据版本：").append(root.getString("version")).append("\n");
            out.append("说明：当前工具返回的是公司-产业链候选证据摘要，还不是完整 L8 逐条证据详情。\n\n");
            if (items == null || items.isEmpty()) {
                out.append("未查询到可用的公司证据摘要。\n");
                return out.toString();
            }
            out.append("候选证据摘要：\n");
            int limit = Math.min(items.size(), 5);
            for (int i = 0; i < limit; i++) {
                JSONObject item = items.getJSONObject(i);
                out.append(i + 1).append(". ")
                        .append(item.getString("name")).append("（").append(item.getString("code")).append("）")
                        .append("：产业链 ").append(item.getString("chain_id"))
                        .append("，标签 ").append(firstTagName(item))
                        .append("，三高总分 ").append(item.getString("three_high_total"))
                        .append("，成长/盈利/围墙 ")
                        .append(item.getString("growth_score")).append("/")
                        .append(item.getString("profit_score")).append("/")
                        .append(item.getString("moat_score"))
                        .append("，研发阶段 ").append(item.getString("research_stage"))
                        .append("，商用阶段 ").append(item.getString("commercialization_stage"))
                        .append("，L8匹配率 ").append(toPercentText(item.getDouble("l8_match_rate")))
                        .append("，事实数 ").append(item.getIntValue("fact_count"))
                        .append("，最新交易日 ").append(item.getString("latest_trade_date"))
                        .append("。\n");
            }
            out.append("\n缺口：如需逐条 L8 原文证据、公告/研报来源、页码和发布时间，需要新增按公司代码查询的证据详情工具接口。");
            return out.toString();
        } catch (Exception e) {
            return "工具返回：" + truncate(rawBody, 1200);
        }
    }

    private String formatModelModes(String rawBody, String modelType) {
        try {
            JSONObject root = JSON.parseObject(rawBody);
            JSONArray modes = root.getJSONArray("modes");
            StringBuilder out = new StringBuilder();
            out.append("最新交易日：").append(root.getString("latest_trade_date")).append("\n");
            JSONObject freshness = root.getJSONObject("data_freshness");
            if (freshness != null) {
                out.append("数据状态：").append(freshness.getString("status"))
                        .append("，来源 ").append(freshness.getString("source"))
                        .append("，质量分 ").append(freshness.getString("quality_score")).append("。\n");
            }
            out.append("\n可用").append(modelType).append("模型：\n");
            int count = 0;
            if (modes != null) {
                for (int i = 0; i < modes.size(); i++) {
                    JSONObject mode = modes.getJSONObject(i);
                    String name = mode.getString("name");
                    boolean matched = "选股".equals(modelType)
                            ? !containsAny(name, "可转债", "选债", "转债")
                            : containsAny(name, "可转债", "选债", "转债");
                    if (!matched) {
                        continue;
                    }
                    count++;
                    out.append(count).append(". ").append(name)
                            .append("（").append(mode.getString("id")).append("）")
                            .append("，周期 ").append(mode.getString("cycle"))
                            .append("，风格 ").append(mode.getString("style")).append("。\n");
                    if (count >= 8) {
                        break;
                    }
                }
            }
            if (count == 0) {
                out.append("当前未返回").append(modelType).append("模型清单。\n");
            }
            out.append("\n限制说明：当前接口只返回模型清单和数据日期；单模型今日候选、无票门槛和逐股票命中详情需要继续接入模型运行结果接口。");
            return out.toString();
        } catch (Exception e) {
            return "工具返回：" + truncate(rawBody, 1200);
        }
    }

    private String formatModelRunResults(String rawBody, String modelType) {
        try {
            JSONObject root = JSON.parseObject(rawBody);
            JSONArray runs = root.getJSONArray("runs");
            if (runs == null) {
                return formatModelModes(rawBody, modelType);
            }
            StringBuilder out = new StringBuilder();
            out.append("### ").append(modelType).append("模型运行结果\n\n");
            out.append("- 最新交易日：").append(root.getString("latest_trade_date") == null ? "--" : root.getString("latest_trade_date")).append("\n");
            out.append("- 数据版本：").append(root.getString("version")).append("\n\n");
            int successCount = 0;
            for (int i = 0; i < runs.size(); i++) {
                JSONObject run = runs.getJSONObject(i);
                out.append("#### ").append(i + 1).append(". ")
                        .append(run.getString("name") == null ? run.getString("mode") : run.getString("name"))
                        .append("\n\n");
                out.append("- 模型ID：`").append(run.getString("mode")).append("`\n");
                if (!"ok".equals(run.getString("status"))) {
                    out.append("- 状态：运行失败\n");
                    out.append("- 原因：").append(run.getString("message")).append("\n\n");
                    continue;
                }
                successCount++;
                JSONObject body = run.getJSONObject("body");
                if (body == null) {
                    out.append("- 状态：接口返回为空。\n\n");
                    continue;
                }
                out.append("- 交易日：").append(body.getString("trade_date")).append("\n");
                out.append("- 候选数：").append(body.getIntValue("total_picks")).append("\n");
                JSONObject freshness = body.getJSONObject("data_freshness");
                if (freshness != null) {
                    out.append("- 数据状态：").append(freshness.getString("status"))
                            .append("，来源 ").append(freshness.getString("source"))
                            .append("，质量分 ").append(freshness.getString("quality_score")).append("\n");
                }
                JSONArray picks = body.getJSONArray("picks");
                if (picks == null || picks.isEmpty()) {
                    out.append("\n本模型当前无候选。\n\n");
                    continue;
                }
                out.append("\n| 排名 | 股票 | 行业 | 等级/信号 | 分数 | 价格 | 涨幅 | 理由/风险 |\n");
                out.append("|---:|---|---|---|---:|---:|---:|---|\n");
                int limit = Math.min(picks.size(), 10);
                for (int j = 0; j < limit; j++) {
                    JSONObject pick = picks.getJSONObject(j);
                    String gradeSignal = joinNonBlank(" / ", pick.getString("grade"), pick.getString("signal"));
                    String reason = firstNonBlank(pick, "entry_reason", "seal_weakness", "resonance_risk");
                    JSONArray riskFlags = pick.getJSONArray("risk_flags");
                    if (riskFlags != null && !riskFlags.isEmpty()) {
                        reason = joinNonBlank("；", reason, "风险 " + riskFlags);
                    }
                    out.append("| ").append(j + 1)
                            .append(" | ").append(mdCell(pick.getString("name"))).append("<br>`").append(mdCell(pick.getString("code"))).append("`")
                            .append(" | ").append(mdCell(pick.getString("industry")))
                            .append(" | ").append(mdCell(gradeSignal))
                            .append(" | ").append(mdCell(firstNonBlank(pick, "score", "total_score")))
                            .append(" | ").append(mdCell(normalizeDisplayNumber(firstNonBlank(pick, "price", "close", "close_14"))))
                            .append(" | ").append(mdCell(firstNonBlank(pick, "daily_gain", "gain_pct")))
                            .append(" | ").append(mdCell(reason))
                            .append(" |\n");
                }
                if (picks.size() > limit) {
                    out.append("\n其余 ").append(picks.size() - limit).append(" 只已返回，当前回答先展示前 ").append(limit).append(" 只。\n");
                }
                out.append("\n");
            }
            if (successCount == 0) {
                out.append("**结论：没有任何").append(modelType).append("模型成功运行，不能给出候选清单。**\n");
            } else {
                out.append("> 说明：以上是模型真实运行结果；快速回答只展示清单，深度思考会继续做解释和风险拆解。");
            }
            return out.toString();
        } catch (Exception e) {
            return "工具返回：" + truncate(rawBody, 1200);
        }
    }

    private String formatNoPickDiagnosis(String rawBody) {
        try {
            JSONObject root = JSON.parseObject(rawBody);
            if (root.getJSONArray("runs") != null) {
                return formatModelRunResults(rawBody, "选股")
                        + "\n\n无票诊断口径：已先执行真实模型。如果某模型候选数为 0，需要继续查看该模型的门槛淘汰明细；如果候选数大于 0，则说明不是“没票”，而是前端或回答层没有展示清单。";
            }
        } catch (Exception ignored) {
        }
        return formatModelModes(rawBody, "选股")
                + "\n\n"
                + formatModelModes(rawBody, "选债")
                + "\n\n无票诊断口径：当前只能确认模型和数据日期可用，尚未接入每个模型的失败门槛明细，因此不能给出完整的逐门槛无票原因。";
    }

    private String formatModelResonance(String rawBody) {
        try {
            JSONObject root = JSON.parseObject(rawBody);
            JSONObject data = root.getJSONObject("data");
            JSONArray diff = data == null ? null : data.getJSONArray("diff");
            StringBuilder out = new StringBuilder();
            out.append("行情来源：").append(root.getString("source")).append("\n");
            out.append("统计日期：").append(root.getString("as_of")).append("\n");
            if (diff == null || diff.isEmpty()) {
                out.append("当前指数/共振接口未返回可用明细。\n");
            } else {
                out.append("返回明细数：").append(diff.size()).append("。\n");
            }
            out.append("限制说明：模型共振需要接入选股、选债、产业链候选的交集统计接口；当前只完成行情接口连通。");
            return out.toString();
        } catch (Exception e) {
            return "工具返回：" + truncate(rawBody, 1200);
        }
    }

    private String formatDataQuality(String rawBody) {
        try {
            JSONObject root = JSON.parseObject(rawBody);
            JSONObject latestDates = root.getJSONObject("latest_dates");
            StringBuilder out = new StringBuilder();
            out.append("最新交易日：").append(root.getString("latest_trade_date")).append("\n");
            if (latestDates != null) {
                out.append("数据表日期：\n");
                for (String key : latestDates.keySet()) {
                    out.append("- ").append(key).append("：").append(latestDates.getString(key)).append("\n");
                }
            }
            JSONObject freshness = root.getJSONObject("data_freshness");
            if (freshness != null) {
                out.append("整体状态：").append(freshness.getString("status"))
                        .append("，质量分 ").append(freshness.getString("quality_score"))
                        .append("，截至 ").append(freshness.getString("as_of")).append("。\n");
            }
            out.append("限制说明：当前数据质量接口还未输出逐产业链证据缺口、公告/研报缺口和模型结果缺口。");
            return out.toString();
        } catch (Exception e) {
            return "工具返回：" + truncate(rawBody, 1200);
        }
    }

    private String formatReportDraft(String rawBody) {
        String ranking = formatSupplyChainRanking(rawBody);
        return "报告草稿已生成，但当前版本只返回文本摘要，没有生成可下载文件。\n\n"
                + "报告结构：\n"
                + "1. 产业链位置和标签\n"
                + "2. 三高评分：成长、盈利、围墙\n"
                + "3. 研发阶段和商用阶段\n"
                + "4. L8 证据匹配和事实数量\n"
                + "5. 交易观察：最新交易日、价格和20日涨幅\n\n"
                + ranking
                + "\n\n导出缺口：Word/Excel 文件导出需要继续接入报告模板渲染和文件存储接口。";
    }

    private String firstTagName(JSONObject item) {
        JSONArray names = item.getJSONArray("tag_names");
        if (names != null && !names.isEmpty()) {
            return names.getString(0);
        }
        return item.getString("best_tag_name");
    }

    private void appendIfPresent(StringBuilder out, String label, String value) {
        if (value != null && value.trim().length() > 0 && !"null".equalsIgnoreCase(value)) {
            out.append(label).append(value);
        }
    }

    private String firstNonBlank(JSONObject item, String... keys) {
        for (String key : keys) {
            String value = item.getString(key);
            if (value != null && value.trim().length() > 0 && !"null".equalsIgnoreCase(value)) {
                return value;
            }
        }
        return null;
    }

    private String joinNonBlank(String separator, String... values) {
        StringBuilder out = new StringBuilder();
        for (String value : values) {
            if (value == null || value.trim().length() == 0 || "null".equalsIgnoreCase(value)) {
                continue;
            }
            if (out.length() > 0) {
                out.append(separator);
            }
            out.append(value.trim());
        }
        return out.toString();
    }

    private String mdCell(String value) {
        if (value == null || value.trim().length() == 0 || "null".equalsIgnoreCase(value)) {
            return "--";
        }
        return value.replace("|", "/")
                .replace("\r", " ")
                .replace("\n", " ")
                .trim();
    }

    private String normalizeDisplayNumber(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        if ("0".equals(trimmed) || "0.0".equals(trimmed) || "0.00".equals(trimmed)) {
            return "--";
        }
        return trimmed;
    }

    private boolean containsAny(String text, String... keywords) {
        String value = text == null ? "" : text.toLowerCase();
        for (String keyword : keywords) {
            if (value.contains(keyword.toLowerCase())) {
                return true;
            }
        }
        return false;
    }

    private String toPercentText(Double value) {
        if (value == null) {
            return "--";
        }
        double normalized = value <= 1 ? value * 100 : value;
        return String.format("%.0f%%", normalized);
    }

    private String truncate(String text, int maxLength) {
        if (text == null) {
            return "";
        }
        if (text.length() <= maxLength) {
            return text;
        }
        return text.substring(0, maxLength) + "...";
    }
}
