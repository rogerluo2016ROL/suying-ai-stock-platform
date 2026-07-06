package com.ds.cockpit.screen.system.service.chatbi.impl;

import cn.hutool.core.lang.UUID;
import com.ds.cockpit.screen.system.service.chatbi.ChatBIConfigService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import javax.annotation.PostConstruct;
import javax.annotation.Resource;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class JdbcChatBIConfigService implements ChatBIConfigService {
    private static final Logger log = LoggerFactory.getLogger(JdbcChatBIConfigService.class);

    @Resource
    private JdbcTemplate jdbcTemplate;

    @PostConstruct
    public void initSchemaAndSeed() {
        try {
            createTables();
            seedDefaults();
        } catch (Exception ex) {
            log.warn("ChatBI config schema init skipped: {}", ex.getMessage());
        }
    }

    @Override
    public Map<String, Object> summary() {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("provider_count", count("chatbi_model_providers"));
        data.put("model_count", count("chatbi_model_versions"));
        data.put("agent_count", count("chatbi_agents"));
        data.put("binding_count", count("chatbi_agent_model_bindings"));
        data.put("prompt_version_count", count("chatbi_prompt_versions"));
        data.put("report_template_count", count("chatbi_report_templates"));
        data.put("report_template_version_count", count("chatbi_report_template_versions"));
        data.put("status", "ready");
        return data;
    }

    @Override
    public List<Map<String, Object>> modelProviders() {
        return rows("SELECT provider_id, provider_name, provider_type, base_url, api_key_ref, status, timeout_seconds, rate_limit_qpm, created_at, updated_at FROM chatbi_model_providers ORDER BY provider_id");
    }

    @Override
    public Map<String, Object> saveModelProvider(Map<String, Object> request) {
        String providerId = text(request, "provider_id", UUID.randomUUID().toString());
        jdbcTemplate.update("INSERT INTO chatbi_model_providers(provider_id, provider_name, provider_type, base_url, api_key_ref, status, timeout_seconds, rate_limit_qpm, created_by, updated_at) " +
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP) " +
                        "ON CONFLICT (provider_id) DO UPDATE SET provider_name = EXCLUDED.provider_name, provider_type = EXCLUDED.provider_type, base_url = EXCLUDED.base_url, api_key_ref = EXCLUDED.api_key_ref, status = EXCLUDED.status, timeout_seconds = EXCLUDED.timeout_seconds, rate_limit_qpm = EXCLUDED.rate_limit_qpm, updated_at = CURRENT_TIMESTAMP",
                providerId,
                text(request, "provider_name", providerId),
                text(request, "provider_type", "openai_compatible"),
                text(request, "base_url", ""),
                text(request, "api_key_ref", ""),
                text(request, "status", "active"),
                number(request, "timeout_seconds", 30),
                number(request, "rate_limit_qpm", 60),
                text(request, "created_by", "system"));
        return one("SELECT * FROM chatbi_model_providers WHERE provider_id = ?", providerId);
    }

    @Override
    public List<Map<String, Object>> modelVersions() {
        return rows("SELECT model_id, provider_id, model_name, context_window, max_output_tokens, fallback_order, status, created_at, updated_at FROM chatbi_model_versions ORDER BY provider_id, fallback_order, model_id");
    }

    @Override
    public Map<String, Object> saveModelVersion(Map<String, Object> request) {
        String modelId = text(request, "model_id", UUID.randomUUID().toString());
        jdbcTemplate.update("INSERT INTO chatbi_model_versions(model_id, provider_id, model_name, context_window, max_output_tokens, fallback_order, status, updated_at) " +
                        "VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP) " +
                        "ON CONFLICT (model_id) DO UPDATE SET provider_id = EXCLUDED.provider_id, model_name = EXCLUDED.model_name, context_window = EXCLUDED.context_window, max_output_tokens = EXCLUDED.max_output_tokens, fallback_order = EXCLUDED.fallback_order, status = EXCLUDED.status, updated_at = CURRENT_TIMESTAMP",
                modelId,
                text(request, "provider_id", "openai_compatible"),
                text(request, "model_name", modelId),
                number(request, "context_window", 32000),
                number(request, "max_output_tokens", 4000),
                number(request, "fallback_order", 100),
                text(request, "status", "active"));
        return one("SELECT * FROM chatbi_model_versions WHERE model_id = ?", modelId);
    }

    @Override
    public Map<String, Object> testProvider(String providerId) {
        Map<String, Object> provider = one("SELECT provider_id, provider_name, provider_type, base_url, api_key_ref, status FROM chatbi_model_providers WHERE provider_id = ?", providerId);
        Map<String, Object> result = new LinkedHashMap<>();
        if (provider == null || provider.isEmpty()) {
            result.put("status", "not_found");
            result.put("provider_id", providerId);
            return result;
        }
        String apiKeyRef = String.valueOf(provider.get("api_key_ref") == null ? "" : provider.get("api_key_ref"));
        String key = apiKeyRef.length() == 0 ? "" : System.getenv(apiKeyRef);
        if (key == null) {
            key = "";
        }
        result.put("provider_id", providerId);
        result.put("provider_type", provider.get("provider_type"));
        result.put("base_url", provider.get("base_url"));
        result.put("api_key_ref", apiKeyRef);
        result.put("masked_key", mask(key));
        result.put("status", key.length() == 0 ? "unavailable" : "configured");
        result.put("message", key.length() == 0 ? "未配置环境变量：" + apiKeyRef + "，未执行真实模型连通性调用。" : "已发现环境变量，真实连通性调用将在 LLM Gateway 阶段执行。");
        return result;
    }

    @Override
    public List<Map<String, Object>> agents() {
        return rows("SELECT * FROM chatbi_agents ORDER BY agent_id");
    }

    @Override
    public List<Map<String, Object>> agentModelBindings() {
        return rows("SELECT * FROM chatbi_agent_model_bindings ORDER BY agent_id, node_type");
    }

    @Override
    public List<Map<String, Object>> agentModelBindings(String agentId) {
        return jdbcTemplate.queryForList("SELECT * FROM chatbi_agent_model_bindings WHERE agent_id = ? ORDER BY node_type", agentId);
    }

    @Override
    public Map<String, Object> saveAgentModelBinding(Map<String, Object> request) {
        String agentId = text(request, "agent_id", "default");
        String nodeType = text(request, "node_type", "answer_generation");
        String primaryModelId = text(request, "primary_model_id", "deepseek-chat");
        String fallbackModelIds = csvText(request.get("fallback_model_ids"), "glm-5.2,custom-model");
        String promptVersionId = text(request, "prompt_version_id", "default_prompt_v1");
        validateAgentModelBinding(agentId, primaryModelId, fallbackModelIds, promptVersionId);
        String bindingId = agentId + "_" + nodeType;
        jdbcTemplate.update("INSERT INTO chatbi_agent_model_bindings(binding_id, agent_id, node_type, primary_model_id, fallback_model_ids, prompt_version_id, temperature, max_output_tokens, timeout_seconds, enabled, created_by, updated_at) " +
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP) " +
                        "ON CONFLICT (binding_id) DO UPDATE SET primary_model_id = EXCLUDED.primary_model_id, fallback_model_ids = EXCLUDED.fallback_model_ids, prompt_version_id = EXCLUDED.prompt_version_id, temperature = EXCLUDED.temperature, max_output_tokens = EXCLUDED.max_output_tokens, timeout_seconds = EXCLUDED.timeout_seconds, enabled = EXCLUDED.enabled, updated_at = CURRENT_TIMESTAMP",
                bindingId,
                agentId,
                nodeType,
                primaryModelId,
                fallbackModelIds,
                promptVersionId,
                decimal(request, "temperature", "0.2"),
                number(request, "max_output_tokens", 1200),
                number(request, "timeout_seconds", 30),
                bool(request, "enabled", true),
                text(request, "created_by", "system"));
        return one("SELECT * FROM chatbi_agent_model_bindings WHERE binding_id = ?", bindingId);
    }

    @Override
    @SuppressWarnings("unchecked")
    public Map<String, Object> saveAgentModelBindings(String agentId, Map<String, Object> request) {
        Object value = request.get("bindings");
        if (!(value instanceof List)) {
            throw new IllegalArgumentException("bindings 必须是数组");
        }
        List<Map<String, Object>> saved = new ArrayList<>();
        for (Object item : (List<Object>) value) {
            if (!(item instanceof Map)) {
                throw new IllegalArgumentException("bindings 中每一项都必须是对象");
            }
            Map<String, Object> binding = new LinkedHashMap<>((Map<String, Object>) item);
            binding.put("agent_id", agentId);
            saved.add(saveAgentModelBinding(binding));
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("agent_id", agentId);
        result.put("binding_count", saved.size());
        result.put("bindings", saved);
        return result;
    }

    @Override
    public List<Map<String, Object>> prompts() {
        return rows("SELECT * FROM chatbi_prompt_versions ORDER BY prompt_id, version");
    }

    @Override
    public Map<String, Object> savePromptVersion(Map<String, Object> request) {
        String promptId = text(request, "prompt_id", "default_prompt");
        String version = text(request, "version", "v1");
        String promptVersionId = text(request, "prompt_version_id", promptId + "_" + version);
        jdbcTemplate.update("INSERT INTO chatbi_prompt_versions(prompt_version_id, prompt_id, version, status, system_prompt, task_prompt, output_schema, risk_rules, allowed_tools, change_note, created_by, updated_at) " +
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP) " +
                        "ON CONFLICT (prompt_version_id) DO UPDATE SET status = EXCLUDED.status, system_prompt = EXCLUDED.system_prompt, task_prompt = EXCLUDED.task_prompt, output_schema = EXCLUDED.output_schema, risk_rules = EXCLUDED.risk_rules, allowed_tools = EXCLUDED.allowed_tools, change_note = EXCLUDED.change_note, updated_at = CURRENT_TIMESTAMP",
                promptVersionId, promptId, version, text(request, "status", "draft"), text(request, "system_prompt", ""), text(request, "task_prompt", ""), text(request, "output_schema", ""), text(request, "risk_rules", ""), text(request, "allowed_tools", ""), text(request, "change_note", ""), text(request, "created_by", "system"));
        return one("SELECT * FROM chatbi_prompt_versions WHERE prompt_version_id = ?", promptVersionId);
    }

    @Override
    public Map<String, Object> publishPromptVersion(String promptId, String version, String userId) {
        jdbcTemplate.update("UPDATE chatbi_prompt_versions SET status = 'published', published_by = ?, published_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE prompt_id = ? AND version = ?",
                userId, promptId, version);
        return one("SELECT * FROM chatbi_prompt_versions WHERE prompt_id = ? AND version = ?", promptId, version);
    }

    @Override
    public List<Map<String, Object>> reportTemplates() {
        return rows("SELECT t.template_id, t.template_name, t.template_type, t.status, v.template_version_id, v.version, v.status AS version_status, v.format, v.published_at FROM chatbi_report_templates t LEFT JOIN chatbi_report_template_versions v ON t.template_id = v.template_id ORDER BY t.template_id, v.version");
    }

    @Override
    public Map<String, Object> saveReportTemplateVersion(Map<String, Object> request) {
        String templateId = text(request, "template_id", "default_report");
        String version = text(request, "version", "v1");
        String templateVersionId = text(request, "template_version_id", templateId + "_" + version);
        jdbcTemplate.update("INSERT INTO chatbi_report_templates(template_id, template_name, template_type, status, updated_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP) " +
                        "ON CONFLICT (template_id) DO UPDATE SET template_name = EXCLUDED.template_name, template_type = EXCLUDED.template_type, status = EXCLUDED.status, updated_at = CURRENT_TIMESTAMP",
                templateId, text(request, "template_name", templateId), text(request, "template_type", "research_report"), text(request, "template_status", "active"));
        jdbcTemplate.update("INSERT INTO chatbi_report_template_versions(template_version_id, template_id, version, status, format, sections, required_data, optional_data, style_config, change_note, created_by, updated_at) " +
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP) " +
                        "ON CONFLICT (template_version_id) DO UPDATE SET status = EXCLUDED.status, format = EXCLUDED.format, sections = EXCLUDED.sections, required_data = EXCLUDED.required_data, optional_data = EXCLUDED.optional_data, style_config = EXCLUDED.style_config, change_note = EXCLUDED.change_note, updated_at = CURRENT_TIMESTAMP",
                templateVersionId, templateId, version, text(request, "status", "draft"), text(request, "format", "markdown"), text(request, "sections", ""), text(request, "required_data", ""), text(request, "optional_data", ""), text(request, "style_config", ""), text(request, "change_note", ""), text(request, "created_by", "system"));
        return one("SELECT * FROM chatbi_report_template_versions WHERE template_version_id = ?", templateVersionId);
    }

    @Override
    public Map<String, Object> publishReportTemplateVersion(String templateId, String version, String userId) {
        jdbcTemplate.update("UPDATE chatbi_report_template_versions SET status = 'published', published_by = ?, published_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE template_id = ? AND version = ?",
                userId, templateId, version);
        return one("SELECT * FROM chatbi_report_template_versions WHERE template_id = ? AND version = ?", templateId, version);
    }

    private void createTables() {
        jdbcTemplate.execute("CREATE TABLE IF NOT EXISTS chatbi_model_providers (provider_id VARCHAR(64) PRIMARY KEY, provider_name VARCHAR(128) NOT NULL, provider_type VARCHAR(64) NOT NULL, base_url TEXT, api_key_ref VARCHAR(128), status VARCHAR(32) NOT NULL DEFAULT 'active', timeout_seconds INTEGER NOT NULL DEFAULT 30, rate_limit_qpm INTEGER NOT NULL DEFAULT 60, created_by VARCHAR(128), created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)");
        jdbcTemplate.execute("CREATE TABLE IF NOT EXISTS chatbi_model_versions (model_id VARCHAR(128) PRIMARY KEY, provider_id VARCHAR(64) NOT NULL REFERENCES chatbi_model_providers(provider_id) ON DELETE CASCADE, model_name VARCHAR(128) NOT NULL, context_window INTEGER, max_output_tokens INTEGER, cost_input_per_1k NUMERIC(18,8), cost_output_per_1k NUMERIC(18,8), fallback_order INTEGER NOT NULL DEFAULT 100, status VARCHAR(32) NOT NULL DEFAULT 'active', created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)");
        jdbcTemplate.execute("CREATE TABLE IF NOT EXISTS chatbi_agents (agent_id VARCHAR(64) PRIMARY KEY, agent_name VARCHAR(128) NOT NULL, agent_type VARCHAR(64) NOT NULL, default_model_id VARCHAR(128), fallback_model_ids TEXT, default_prompt_version_id VARCHAR(128), default_report_template_version_id VARCHAR(128), tool_scope TEXT, status VARCHAR(32) NOT NULL DEFAULT 'active', created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)");
        jdbcTemplate.execute("CREATE TABLE IF NOT EXISTS chatbi_agent_model_bindings (binding_id VARCHAR(128) PRIMARY KEY, agent_id VARCHAR(64) NOT NULL REFERENCES chatbi_agents(agent_id) ON DELETE CASCADE, node_type VARCHAR(64) NOT NULL, primary_model_id VARCHAR(128), fallback_model_ids TEXT, prompt_version_id VARCHAR(128), temperature NUMERIC(6,3) NOT NULL DEFAULT 0.2, max_output_tokens INTEGER NOT NULL DEFAULT 1200, timeout_seconds INTEGER NOT NULL DEFAULT 30, enabled BOOLEAN NOT NULL DEFAULT TRUE, created_by VARCHAR(128), created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)");
        jdbcTemplate.execute("CREATE TABLE IF NOT EXISTS chatbi_agent_tools (id BIGSERIAL PRIMARY KEY, agent_id VARCHAR(64) NOT NULL REFERENCES chatbi_agents(agent_id) ON DELETE CASCADE, tool_name VARCHAR(128) NOT NULL, enabled BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)");
        jdbcTemplate.execute("CREATE TABLE IF NOT EXISTS chatbi_prompt_versions (prompt_version_id VARCHAR(128) PRIMARY KEY, prompt_id VARCHAR(64) NOT NULL, version VARCHAR(32) NOT NULL, status VARCHAR(32) NOT NULL DEFAULT 'draft', system_prompt TEXT, task_prompt TEXT, output_schema TEXT, risk_rules TEXT, allowed_tools TEXT, change_note TEXT, created_by VARCHAR(128), published_by VARCHAR(128), published_at TIMESTAMP, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(prompt_id, version))");
        jdbcTemplate.execute("CREATE TABLE IF NOT EXISTS chatbi_report_templates (template_id VARCHAR(64) PRIMARY KEY, template_name VARCHAR(128) NOT NULL, template_type VARCHAR(64) NOT NULL DEFAULT 'research_report', status VARCHAR(32) NOT NULL DEFAULT 'active', created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)");
        jdbcTemplate.execute("CREATE TABLE IF NOT EXISTS chatbi_report_template_versions (template_version_id VARCHAR(128) PRIMARY KEY, template_id VARCHAR(64) NOT NULL REFERENCES chatbi_report_templates(template_id) ON DELETE CASCADE, version VARCHAR(32) NOT NULL, status VARCHAR(32) NOT NULL DEFAULT 'draft', format VARCHAR(32) NOT NULL DEFAULT 'markdown', sections TEXT, required_data TEXT, optional_data TEXT, style_config TEXT, change_note TEXT, created_by VARCHAR(128), published_by VARCHAR(128), published_at TIMESTAMP, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(template_id, version))");
        jdbcTemplate.execute("CREATE TABLE IF NOT EXISTS chatbi_render_logs (render_id VARCHAR(128) PRIMARY KEY, template_version_id VARCHAR(128), session_id VARCHAR(64), message_id VARCHAR(64), status VARCHAR(32) NOT NULL, error_message TEXT, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)");
    }

    private void seedDefaults() {
        saveModelProvider(row("provider_id", "deepseek", "provider_name", "DeepSeek", "provider_type", "deepseek", "base_url", "https://api.deepseek.com", "api_key_ref", "DEEPSEEK_API_KEY"));
        saveModelProvider(row("provider_id", "glm", "provider_name", "GLM", "provider_type", "glm", "base_url", "https://open.bigmodel.cn/api/paas/v4", "api_key_ref", "GLM_API_KEY"));
        saveModelProvider(row("provider_id", "openai_compatible", "provider_name", "OpenAI Compatible", "provider_type", "openai_compatible", "base_url", "", "api_key_ref", "OPENAI_COMPATIBLE_API_KEY"));
        saveModelVersion(row("model_id", "deepseek-chat", "provider_id", "deepseek", "model_name", "deepseek-chat", "context_window", 64000, "max_output_tokens", 4000, "fallback_order", 10));
        saveModelVersion(row("model_id", "glm-5.2", "provider_id", "glm", "model_name", "glm-5.2", "context_window", 128000, "max_output_tokens", 4000, "fallback_order", 20));
        saveModelVersion(row("model_id", "custom-model", "provider_id", "openai_compatible", "model_name", "custom-model", "context_window", 32000, "max_output_tokens", 4000, "fallback_order", 30));
        seedAgent("default", "总入口助手", "investment_research");
        seedAgent("supply_chain", "产业链助手", "supply_chain");
        seedAgent("stock_model", "选股助手", "stock_model");
        seedAgent("bond_model", "选债助手", "bond_model");
        seedAgent("report", "报告助手", "report");
        seedAgent("data_quality", "数据质量助手", "data_quality");
        savePromptVersion(row("prompt_id", "default_prompt", "version", "v1", "prompt_version_id", "default_prompt_v1", "status", "published", "system_prompt", "你是投研 ChatBI 助手，只能基于工具返回的数据回答。", "task_prompt", "请给出结论、数据口径、证据和限制说明。", "allowed_tools", "supply_chain_candidate_ranking,model_runs,report_export"));
        saveReportTemplateVersion(row("template_id", "default_report", "template_name", "默认投研报告", "version", "v1", "template_version_id", "default_report_v1", "status", "published", "sections", "结论,产业链位置,三高,证据链,风险,交易信号", "required_data", "company,chain,evidence,three_high"));
    }

    private void seedAgent(String agentId, String name, String type) {
        jdbcTemplate.update("INSERT INTO chatbi_agents(agent_id, agent_name, agent_type, default_model_id, fallback_model_ids, default_prompt_version_id, default_report_template_version_id, tool_scope, status, updated_at) VALUES (?, ?, ?, 'deepseek-chat', 'glm-5.2,custom-model', 'default_prompt_v1', 'default_report_v1', ?, 'active', CURRENT_TIMESTAMP) ON CONFLICT (agent_id) DO NOTHING",
                agentId, name, type, type);
        String[] nodeTypes = new String[] {"intent_recognition", "query_planning", "data_query_assist", "evidence_extraction", "answer_generation", "report_generation"};
        for (String nodeType : nodeTypes) {
            String primaryModelId = "evidence_extraction".equals(nodeType) || "report_generation".equals(nodeType) ? "glm-5.2" : "deepseek-chat";
            String fallbackModelIds = "glm-5.2".equals(primaryModelId) ? "deepseek-chat,custom-model" : "glm-5.2,custom-model";
            saveAgentModelBinding(row("binding_id", agentId + "_" + nodeType, "agent_id", agentId, "node_type", nodeType, "primary_model_id", primaryModelId, "fallback_model_ids", fallbackModelIds, "prompt_version_id", "default_prompt_v1"));
        }
    }

    private long count(String table) {
        try {
            Long value = jdbcTemplate.queryForObject("SELECT count(*) FROM " + table, Long.class);
            return value == null ? 0 : value;
        } catch (Exception ex) {
            return 0;
        }
    }

    private List<Map<String, Object>> rows(String sql) {
        return jdbcTemplate.queryForList(sql);
    }

    private Map<String, Object> one(String sql, Object... args) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(sql, args);
        return rows.isEmpty() ? new LinkedHashMap<>() : rows.get(0);
    }

    private Map<String, Object> row(Object... values) {
        Map<String, Object> map = new LinkedHashMap<>();
        for (int i = 0; i + 1 < values.length; i += 2) {
            map.put(String.valueOf(values[i]), values[i + 1]);
        }
        return map;
    }

    private String text(Map<String, Object> request, String key, String defaultValue) {
        Object value = request.get(key);
        if (value == null || String.valueOf(value).trim().length() == 0) {
            return defaultValue;
        }
        return String.valueOf(value).trim();
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

    private BigDecimal decimal(Map<String, Object> request, String key, String defaultValue) {
        Object value = request.get(key);
        try {
            return new BigDecimal(value == null ? defaultValue : String.valueOf(value));
        } catch (Exception ex) {
            return new BigDecimal(defaultValue);
        }
    }

    private boolean bool(Map<String, Object> request, String key, boolean defaultValue) {
        Object value = request.get(key);
        return value == null ? defaultValue : Boolean.parseBoolean(String.valueOf(value));
    }

    private void validateAgentModelBinding(String agentId, String primaryModelId, String fallbackModelIds, String promptVersionId) {
        if (!exists("SELECT count(*) FROM chatbi_agents WHERE agent_id = ? AND status = 'active'", agentId)) {
            throw new IllegalArgumentException("智能体不存在或未启用：" + agentId);
        }
        validateModel(primaryModelId);
        if (fallbackModelIds != null && fallbackModelIds.trim().length() > 0) {
            String[] ids = fallbackModelIds.split(",");
            for (String id : ids) {
                String modelId = id.trim();
                if (modelId.length() > 0) {
                    validateModel(modelId);
                }
            }
        }
        if (!exists("SELECT count(*) FROM chatbi_prompt_versions WHERE prompt_version_id = ? AND status = 'published'", promptVersionId)) {
            throw new IllegalArgumentException("提示词版本不存在或未发布：" + promptVersionId);
        }
    }

    private void validateModel(String modelId) {
        if (!exists("SELECT count(*) FROM chatbi_model_versions WHERE model_id = ? AND status = 'active'", modelId)) {
            throw new IllegalArgumentException("模型不存在或未启用：" + modelId);
        }
    }

    private boolean exists(String sql, Object... args) {
        Long value = jdbcTemplate.queryForObject(sql, args, Long.class);
        return value != null && value > 0;
    }

    private String csvText(Object value, String defaultValue) {
        if (value == null) {
            return defaultValue;
        }
        if (value instanceof List) {
            StringBuilder builder = new StringBuilder();
            for (Object item : (List<?>) value) {
                String text = item == null ? "" : String.valueOf(item).trim();
                if (text.length() == 0) {
                    continue;
                }
                if (builder.length() > 0) {
                    builder.append(",");
                }
                builder.append(text);
            }
            return builder.length() == 0 ? defaultValue : builder.toString();
        }
        String text = String.valueOf(value).trim();
        return text.length() == 0 ? defaultValue : text;
    }

    private String mask(String key) {
        if (key == null || key.length() == 0) {
            return "";
        }
        if (key.length() <= 8) {
            return "***";
        }
        return key.substring(0, 3) + "***" + key.substring(key.length() - 4);
    }
}
