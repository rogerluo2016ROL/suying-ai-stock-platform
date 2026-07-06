package com.ds.cockpit.screen.system.service.chatbi.impl;

import cn.hutool.core.lang.UUID;
import cn.hutool.http.HttpRequest;
import cn.hutool.http.HttpResponse;
import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONArray;
import com.alibaba.fastjson2.JSONObject;
import com.ds.cockpit.screen.system.service.chatbi.ChatBILLMGatewayService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import javax.annotation.PostConstruct;
import javax.annotation.Resource;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class JdbcChatBILLMGatewayService implements ChatBILLMGatewayService {
    private static final Logger log = LoggerFactory.getLogger(JdbcChatBILLMGatewayService.class);

    @Resource
    private JdbcTemplate jdbcTemplate;

    @PostConstruct
    public void initSchema() {
        try {
            jdbcTemplate.execute("CREATE TABLE IF NOT EXISTS chatbi_llm_invocations (" +
                    "invocation_id VARCHAR(128) PRIMARY KEY," +
                    "session_id VARCHAR(64)," +
                    "message_id VARCHAR(64)," +
                    "agent_id VARCHAR(64)," +
                    "node_type VARCHAR(64)," +
                    "provider_id VARCHAR(64)," +
                    "model_id VARCHAR(128)," +
                    "status VARCHAR(32) NOT NULL," +
                    "input_tokens INTEGER," +
                    "output_tokens INTEGER," +
                    "fallback_reason TEXT," +
                    "error_message TEXT," +
                    "latency_ms INTEGER," +
                    "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP" +
                    ")");
        } catch (Exception ex) {
            log.warn("ChatBI LLM schema init skipped: {}", ex.getMessage());
        }
    }

    @Override
    public Map<String, Object> generate(Map<String, Object> request) {
        String sessionId = text(request, "session_id", text(request, "sessionId", ""));
        String messageId = text(request, "message_id", text(request, "messageId", ""));
        String agentId = text(request, "agent_id", text(request, "agentId", "default"));
        String nodeType = text(request, "node_type", text(request, "nodeType", "answer_generation"));
        List<String> candidates = resolveModelCandidates(request, agentId, nodeType);
        List<Map<String, Object>> attempts = new ArrayList<>();

        for (String modelId : candidates) {
            Map<String, Object> model = one("SELECT m.model_id, m.model_name, m.max_output_tokens, p.provider_id, p.provider_type, p.base_url, p.api_key_ref, p.timeout_seconds " +
                    "FROM chatbi_model_versions m JOIN chatbi_model_providers p ON m.provider_id = p.provider_id " +
                    "WHERE m.model_id = ? AND m.status = 'active' AND p.status = 'active'", modelId);
            if (model.isEmpty()) {
                attempts.add(attempt(modelId, "", "not_found", "模型或供应商未启用"));
                continue;
            }
            Map<String, Object> result = callProvider(request, model, sessionId, messageId, agentId, nodeType);
            attempts.add(result);
            if ("ok".equals(result.get("status"))) {
                result.put("attempts", attempts);
                return result;
            }
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", "unavailable");
        result.put("agent_id", agentId);
        result.put("node_type", nodeType);
        result.put("attempts", attempts);
        result.put("message", "所有候选模型均不可用，已降级为模板化回答。");
        return result;
    }

    private Map<String, Object> callProvider(Map<String, Object> request, Map<String, Object> model, String sessionId, String messageId, String agentId, String nodeType) {
        long start = System.currentTimeMillis();
        String providerId = string(model.get("provider_id"));
        String modelId = string(model.get("model_id"));
        String modelName = string(model.get("model_name"));
        String apiKeyRef = string(model.get("api_key_ref"));
        String key = apiKeyRef.length() == 0 ? "" : System.getenv(apiKeyRef);
        if (key == null || key.length() == 0) {
            int latency = (int) (System.currentTimeMillis() - start);
            saveInvocation(sessionId, messageId, agentId, nodeType, providerId, modelId, "unavailable", null, null, "missing_api_key:" + apiKeyRef, "", latency);
            return attempt(modelId, providerId, "unavailable", "未配置环境变量：" + apiKeyRef);
        }

        String baseUrl = string(model.get("base_url"));
        if (baseUrl.length() == 0) {
            int latency = (int) (System.currentTimeMillis() - start);
            saveInvocation(sessionId, messageId, agentId, nodeType, providerId, modelId, "unavailable", null, null, "missing_base_url", "", latency);
            return attempt(modelId, providerId, "unavailable", "供应商 base_url 为空");
        }

        try {
            JSONObject payload = new JSONObject();
            payload.put("model", modelName);
            payload.put("messages", buildMessages(request));
            payload.put("temperature", decimalNumber(request, "temperature", 0.2));
            payload.put("max_tokens", number(request, "max_tokens", number(request, "maxTokens", intValue(model.get("max_output_tokens"), 1200))));

            int timeoutMs = number(request, "timeout_ms", intValue(model.get("timeout_seconds"), 30) * 1000);
            HttpResponse response = HttpRequest.post(resolveChatUrl(baseUrl))
                    .header("Authorization", "Bearer " + key)
                    .header("Content-Type", "application/json")
                    .body(payload.toJSONString())
                    .timeout(timeoutMs)
                    .execute();
            int latency = (int) (System.currentTimeMillis() - start);
            if (!response.isOk()) {
                String error = truncate(response.body(), 1000);
                saveInvocation(sessionId, messageId, agentId, nodeType, providerId, modelId, "error", null, null, "http_" + response.getStatus(), error, latency);
                return attempt(modelId, providerId, "error", "HTTP " + response.getStatus());
            }
            JSONObject root = JSON.parseObject(response.body());
            String content = extractContent(root);
            JSONObject usage = root.getJSONObject("usage");
            Integer inputTokens = usage == null ? null : usage.getInteger("prompt_tokens");
            Integer outputTokens = usage == null ? null : usage.getInteger("completion_tokens");
            saveInvocation(sessionId, messageId, agentId, nodeType, providerId, modelId, "ok", inputTokens, outputTokens, "", "", latency);

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("status", "ok");
            result.put("provider_id", providerId);
            result.put("model_id", modelId);
            result.put("model_name", modelName);
            result.put("content", content);
            result.put("latency_ms", latency);
            Map<String, Object> usageMap = new LinkedHashMap<>();
            usageMap.put("input_tokens", inputTokens);
            usageMap.put("output_tokens", outputTokens);
            result.put("usage", usageMap);
            return result;
        } catch (Exception ex) {
            int latency = (int) (System.currentTimeMillis() - start);
            saveInvocation(sessionId, messageId, agentId, nodeType, providerId, modelId, "error", null, null, "exception", ex.getMessage(), latency);
            return attempt(modelId, providerId, "error", ex.getMessage());
        }
    }

    private List<String> resolveModelCandidates(Map<String, Object> request, String agentId, String nodeType) {
        String modelId = text(request, "model_id", text(request, "modelId", ""));
        if (modelId.length() > 0) {
            return Arrays.asList(modelId);
        }
        Map<String, Object> binding = one("SELECT primary_model_id, fallback_model_ids FROM chatbi_agent_model_bindings WHERE agent_id = ? AND node_type = ? AND enabled = TRUE", agentId, nodeType);
        List<String> candidates = new ArrayList<>();
        if (!binding.isEmpty()) {
            addCandidate(candidates, string(binding.get("primary_model_id")));
            for (String fallback : string(binding.get("fallback_model_ids")).split(",")) {
                addCandidate(candidates, fallback.trim());
            }
        }
        if (candidates.isEmpty()) {
            candidates.add("deepseek-chat");
            candidates.add("glm-5.2");
            candidates.add("custom-model");
        }
        return candidates;
    }

    private JSONArray buildMessages(Map<String, Object> request) {
        Object raw = request.get("messages");
        if (raw instanceof List) {
            return JSONArray.from(raw);
        }
        JSONArray messages = new JSONArray();
        String system = text(request, "system", "你是投研 ChatBI 助手，只能基于工具返回的数据回答。");
        String prompt = text(request, "prompt", text(request, "question", ""));
        JSONObject systemMsg = new JSONObject();
        systemMsg.put("role", "system");
        systemMsg.put("content", system);
        messages.add(systemMsg);
        JSONObject userMsg = new JSONObject();
        userMsg.put("role", "user");
        userMsg.put("content", prompt);
        messages.add(userMsg);
        return messages;
    }

    private String extractContent(JSONObject root) {
        JSONArray choices = root.getJSONArray("choices");
        if (choices == null || choices.isEmpty()) {
            return "";
        }
        JSONObject first = choices.getJSONObject(0);
        JSONObject message = first.getJSONObject("message");
        if (message != null) {
            return string(message.get("content"));
        }
        return string(first.get("text"));
    }

    private String resolveChatUrl(String baseUrl) {
        String normalized = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        if (normalized.endsWith("/chat/completions")) {
            return normalized;
        }
        return normalized + "/chat/completions";
    }

    private void saveInvocation(String sessionId, String messageId, String agentId, String nodeType, String providerId, String modelId, String status, Integer inputTokens, Integer outputTokens, String fallbackReason, String errorMessage, int latencyMs) {
        try {
            jdbcTemplate.update("INSERT INTO chatbi_llm_invocations(invocation_id, session_id, message_id, agent_id, node_type, provider_id, model_id, status, input_tokens, output_tokens, fallback_reason, error_message, latency_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    UUID.randomUUID().toString(), sessionId, messageId, agentId, nodeType, providerId, modelId, status, inputTokens, outputTokens, fallbackReason, errorMessage, latencyMs);
        } catch (Exception ex) {
            log.warn("ChatBI save LLM invocation skipped: {}", ex.getMessage());
        }
    }

    private Map<String, Object> attempt(String modelId, String providerId, String status, String message) {
        Map<String, Object> attempt = new LinkedHashMap<>();
        attempt.put("model_id", modelId);
        attempt.put("provider_id", providerId);
        attempt.put("status", status);
        attempt.put("message", message);
        return attempt;
    }

    private Map<String, Object> one(String sql, Object... args) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(sql, args);
        return rows.isEmpty() ? new LinkedHashMap<>() : rows.get(0);
    }

    private void addCandidate(List<String> candidates, String modelId) {
        if (modelId != null && modelId.length() > 0 && !candidates.contains(modelId)) {
            candidates.add(modelId);
        }
    }

    private String text(Map<String, Object> request, String key, String defaultValue) {
        Object value = request.get(key);
        if (value == null || String.valueOf(value).trim().length() == 0) {
            return defaultValue;
        }
        return String.valueOf(value).trim();
    }

    private String string(Object value) {
        return value == null ? "" : String.valueOf(value);
    }

    private int number(Map<String, Object> request, String key, int defaultValue) {
        Object value = request.get(key);
        if (value instanceof Number) {
            return ((Number) value).intValue();
        }
        try {
            return value == null ? defaultValue : Integer.parseInt(String.valueOf(value));
        } catch (Exception ex) {
            return defaultValue;
        }
    }

    private String numberText(Map<String, Object> request, String key, String defaultValue) {
        Object value = request.get(key);
        return value == null ? defaultValue : String.valueOf(value);
    }

    private double decimalNumber(Map<String, Object> request, String key, double defaultValue) {
        Object value = request.get(key);
        if (value instanceof Number) {
            return ((Number) value).doubleValue();
        }
        if (value == null || String.valueOf(value).trim().length() == 0) {
            return defaultValue;
        }
        try {
            return Double.parseDouble(String.valueOf(value).trim());
        } catch (Exception ex) {
            return defaultValue;
        }
    }

    private int intValue(Object value, int defaultValue) {
        if (value instanceof Number) {
            return ((Number) value).intValue();
        }
        try {
            return value == null ? defaultValue : Integer.parseInt(String.valueOf(value));
        } catch (Exception ex) {
            return defaultValue;
        }
    }

    private String truncate(String text, int maxLength) {
        if (text == null || text.length() <= maxLength) {
            return text;
        }
        return text.substring(0, maxLength);
    }
}
