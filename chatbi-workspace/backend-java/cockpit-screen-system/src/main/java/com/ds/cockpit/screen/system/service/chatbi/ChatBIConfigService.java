package com.ds.cockpit.screen.system.service.chatbi;

import java.util.List;
import java.util.Map;

public interface ChatBIConfigService {
    Map<String, Object> summary();

    List<Map<String, Object>> modelProviders();

    Map<String, Object> saveModelProvider(Map<String, Object> request);

    List<Map<String, Object>> modelVersions();

    Map<String, Object> saveModelVersion(Map<String, Object> request);

    Map<String, Object> testProvider(String providerId);

    List<Map<String, Object>> agents();

    List<Map<String, Object>> agentModelBindings();

    List<Map<String, Object>> agentModelBindings(String agentId);

    Map<String, Object> saveAgentModelBinding(Map<String, Object> request);

    Map<String, Object> saveAgentModelBindings(String agentId, Map<String, Object> request);

    List<Map<String, Object>> prompts();

    Map<String, Object> savePromptVersion(Map<String, Object> request);

    Map<String, Object> publishPromptVersion(String promptId, String version, String userId);

    List<Map<String, Object>> reportTemplates();

    Map<String, Object> saveReportTemplateVersion(Map<String, Object> request);

    Map<String, Object> publishReportTemplateVersion(String templateId, String version, String userId);
}
