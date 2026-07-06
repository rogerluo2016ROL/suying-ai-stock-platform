package com.ds.cockpit.screen.system.service.chatbi.impl;

import cn.hutool.core.lang.UUID;
import com.ds.cockpit.screen.system.service.chatbi.ChatBILLMGatewayService;
import com.ds.cockpit.screen.system.service.chatbi.ChatBIPreviewService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import javax.annotation.PostConstruct;
import javax.annotation.Resource;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class JdbcChatBIPreviewService implements ChatBIPreviewService {
    private static final Logger log = LoggerFactory.getLogger(JdbcChatBIPreviewService.class);

    @Resource
    private JdbcTemplate jdbcTemplate;

    @Resource
    private ChatBILLMGatewayService llmGatewayService;

    @PostConstruct
    public void initSchema() {
        try {
            jdbcTemplate.execute("CREATE TABLE IF NOT EXISTS chatbi_preview_logs (" +
                    "preview_id VARCHAR(128) PRIMARY KEY," +
                    "agent_id VARCHAR(64)," +
                    "node_type VARCHAR(64)," +
                    "provider_id VARCHAR(64)," +
                    "model_id VARCHAR(128)," +
                    "prompt_version_id VARCHAR(128)," +
                    "status VARCHAR(32) NOT NULL," +
                    "input_tokens INTEGER," +
                    "output_tokens INTEGER," +
                    "latency_ms INTEGER," +
                    "error_message TEXT," +
                    "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP" +
                    ")");
        } catch (Exception ex) {
            log.warn("ChatBI preview schema init skipped: {}", ex.getMessage());
        }
    }

    @Override
    public Map<String, Object> preview(Map<String, Object> request) {
        long start = System.currentTimeMillis();
        String previewId = UUID.randomUUID().toString();
        String agentId = text(request, "agent_id", text(request, "agentId", "default"));
        String nodeType = text(request, "node_type", text(request, "nodeType", "answer_generation"));
        String modelId = text(request, "model_id", text(request, "modelId", ""));
        String promptVersionId = text(request, "prompt_version_id", text(request, "promptVersionId", resolvePromptVersion(agentId, nodeType)));
        String question = text(request, "question", text(request, "prompt", ""));

        Map<String, Object> prompt = one("SELECT prompt_version_id, system_prompt, task_prompt FROM chatbi_prompt_versions WHERE prompt_version_id = ? AND status = 'published'", promptVersionId);
        if (prompt.isEmpty()) {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("preview_id", previewId);
            result.put("status", "invalid_prompt");
            result.put("agent_id", agentId);
            result.put("node_type", nodeType);
            result.put("model_id", modelId);
            result.put("prompt_version_id", promptVersionId);
            result.put("message", "提示词版本不存在或未发布：" + promptVersionId);
            saveLog(previewId, agentId, nodeType, "", modelId, promptVersionId, "invalid_prompt", null, null, (int) (System.currentTimeMillis() - start), String.valueOf(result.get("message")));
            return result;
        }

        Map<String, Object> llmRequest = new LinkedHashMap<>();
        llmRequest.put("session_id", "preview");
        llmRequest.put("message_id", previewId);
        llmRequest.put("agent_id", agentId);
        llmRequest.put("node_type", nodeType);
        if (modelId.length() > 0) {
            llmRequest.put("model_id", modelId);
        }
        llmRequest.put("prompt_version_id", promptVersionId);
        llmRequest.put("system", string(prompt.get("system_prompt")));
        llmRequest.put("prompt", string(prompt.get("task_prompt")) + "\n\n用户问题：" + question);
        llmRequest.put("temperature", text(request, "temperature", "0.2"));
        llmRequest.put("max_tokens", number(request, "max_tokens", number(request, "maxTokens", 1200)));

        Map<String, Object> llmResult = llmGatewayService.generate(llmRequest);
        String status = string(llmResult.get("status"));
        String providerId = string(llmResult.get("provider_id"));
        String resolvedModelId = string(llmResult.get("model_id"));
        if (resolvedModelId.length() == 0) {
            Map<String, Object> firstAttempt = firstAttempt(llmResult);
            providerId = string(firstAttempt.get("provider_id"));
            resolvedModelId = string(firstAttempt.get("model_id"));
        }

        Map<String, Object> usage = usage(llmResult);
        Integer inputTokens = integer(usage.get("input_tokens"));
        Integer outputTokens = integer(usage.get("output_tokens"));
        int latencyMs = (int) (System.currentTimeMillis() - start);
        saveLog(previewId, agentId, nodeType, providerId, resolvedModelId, promptVersionId, status, inputTokens, outputTokens, latencyMs, string(llmResult.get("message")));

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("preview_id", previewId);
        result.put("agent_id", agentId);
        result.put("node_type", nodeType);
        result.put("model_id", resolvedModelId);
        result.put("provider_id", providerId);
        result.put("prompt_version_id", promptVersionId);
        result.put("status", status);
        result.put("latency_ms", latencyMs);
        result.put("usage", usage);
        result.put("result", llmResult);
        result.put("persisted_to_session", false);
        return result;
    }

    private String resolvePromptVersion(String agentId, String nodeType) {
        Map<String, Object> binding = one("SELECT prompt_version_id FROM chatbi_agent_model_bindings WHERE agent_id = ? AND node_type = ? AND enabled = TRUE", agentId, nodeType);
        return binding.isEmpty() ? "default_prompt_v1" : string(binding.get("prompt_version_id"));
    }

    private void saveLog(String previewId, String agentId, String nodeType, String providerId, String modelId, String promptVersionId, String status, Integer inputTokens, Integer outputTokens, int latencyMs, String errorMessage) {
        try {
            jdbcTemplate.update("INSERT INTO chatbi_preview_logs(preview_id, agent_id, node_type, provider_id, model_id, prompt_version_id, status, input_tokens, output_tokens, latency_ms, error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    previewId, agentId, nodeType, providerId, modelId, promptVersionId, status, inputTokens, outputTokens, latencyMs, errorMessage);
        } catch (Exception ex) {
            log.warn("ChatBI save preview log skipped: {}", ex.getMessage());
        }
    }

    private Map<String, Object> one(String sql, Object... args) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(sql, args);
        return rows.isEmpty() ? new LinkedHashMap<>() : rows.get(0);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> firstAttempt(Map<String, Object> result) {
        Object attempts = result.get("attempts");
        if (attempts instanceof List && !((List<?>) attempts).isEmpty() && ((List<?>) attempts).get(0) instanceof Map) {
            return (Map<String, Object>) ((List<?>) attempts).get(0);
        }
        return new LinkedHashMap<>();
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> usage(Map<String, Object> result) {
        Object usage = result.get("usage");
        if (usage instanceof Map) {
            return (Map<String, Object>) usage;
        }
        Map<String, Object> empty = new LinkedHashMap<>();
        empty.put("input_tokens", null);
        empty.put("output_tokens", null);
        return empty;
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

    private Integer integer(Object value) {
        if (value instanceof Number) {
            return ((Number) value).intValue();
        }
        try {
            return value == null ? null : Integer.parseInt(String.valueOf(value));
        } catch (Exception ex) {
            return null;
        }
    }
}
