package com.ds.cockpit.screen.web.controller.chatbi;

import com.ds.cockpit.screen.common.core.controller.BaseController;
import com.ds.cockpit.screen.common.core.domain.AjaxResult;
import com.ds.cockpit.screen.system.service.chatbi.ChatBIConfigService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.Resource;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/chatbi")
public class ChatBIConfigController extends BaseController {
    @Resource
    private ChatBIConfigService chatBIConfigService;

    @GetMapping("/config/summary")
    public AjaxResult summary() {
        return success(chatBIConfigService.summary());
    }

    @GetMapping("/model-providers")
    public AjaxResult modelProviders() {
        return success(chatBIConfigService.modelProviders());
    }

    @PostMapping("/model-providers")
    public AjaxResult saveModelProvider(@RequestBody Map<String, Object> request) {
        return success(chatBIConfigService.saveModelProvider(request));
    }

    @PostMapping("/model-providers/{providerId}/test")
    public AjaxResult testProvider(@PathVariable("providerId") String providerId) {
        return success(chatBIConfigService.testProvider(providerId));
    }

    @GetMapping("/model-versions")
    public AjaxResult modelVersions() {
        return success(chatBIConfigService.modelVersions());
    }

    @PostMapping("/model-versions")
    public AjaxResult saveModelVersion(@RequestBody Map<String, Object> request) {
        return success(chatBIConfigService.saveModelVersion(request));
    }

    @GetMapping("/agents/config")
    public AjaxResult agents() {
        return success(chatBIConfigService.agents());
    }

    @GetMapping("/agent-model-bindings")
    public AjaxResult agentModelBindings() {
        return success(chatBIConfigService.agentModelBindings());
    }

    @PostMapping("/agent-model-bindings")
    public AjaxResult saveAgentModelBinding(@RequestBody Map<String, Object> request) {
        return success(chatBIConfigService.saveAgentModelBinding(request));
    }

    @GetMapping("/agents/{agentId}/model-bindings")
    public AjaxResult agentModelBindings(@PathVariable("agentId") String agentId) {
        return success(chatBIConfigService.agentModelBindings(agentId));
    }

    @PutMapping("/agents/{agentId}/model-bindings")
    public AjaxResult saveAgentModelBindings(@PathVariable("agentId") String agentId,
                                             @RequestBody Map<String, Object> request) {
        return success(chatBIConfigService.saveAgentModelBindings(agentId, request));
    }

    @GetMapping("/prompts")
    public AjaxResult prompts() {
        return success(chatBIConfigService.prompts());
    }

    @PostMapping("/prompts")
    public AjaxResult savePromptVersion(@RequestBody Map<String, Object> request) {
        return success(chatBIConfigService.savePromptVersion(request));
    }

    @PostMapping("/prompts/{promptId}/versions/{version}/publish")
    public AjaxResult publishPromptVersion(@PathVariable("promptId") String promptId,
                                           @PathVariable("version") String version,
                                           @RequestParam(value = "userId", defaultValue = "system") String userId) {
        return success(chatBIConfigService.publishPromptVersion(promptId, version, userId));
    }

    @GetMapping("/report-templates")
    public AjaxResult reportTemplates() {
        return success(chatBIConfigService.reportTemplates());
    }

    @PostMapping("/report-templates")
    public AjaxResult saveReportTemplateVersion(@RequestBody Map<String, Object> request) {
        return success(chatBIConfigService.saveReportTemplateVersion(request));
    }

    @PostMapping("/report-templates/{templateId}/versions/{version}/publish")
    public AjaxResult publishReportTemplateVersion(@PathVariable("templateId") String templateId,
                                                   @PathVariable("version") String version,
                                                   @RequestParam(value = "userId", defaultValue = "system") String userId) {
        return success(chatBIConfigService.publishReportTemplateVersion(templateId, version, userId));
    }
}
