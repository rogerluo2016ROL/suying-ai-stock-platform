package com.ds.cockpit.screen.web.controller.chatbi;

import com.ds.cockpit.screen.common.core.controller.BaseController;
import com.ds.cockpit.screen.common.core.domain.AjaxResult;
import com.ds.cockpit.screen.system.service.chatbi.PlatformIdentityService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.Resource;
import java.util.LinkedHashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/chatbi/platform")
public class PlatformIdentityController extends BaseController {
    @Resource
    private PlatformIdentityService platformIdentityService;

    @PostMapping("/bindings")
    public AjaxResult bind(@RequestBody Map<String, Object> request) {
        return success(platformIdentityService.bind(request));
    }

    @GetMapping("/bindings")
    public AjaxResult bindings(@RequestParam(value = "platform", required = false) String platform,
                               @RequestParam(value = "tenantId", required = false) String tenantId) {
        return success(platformIdentityService.bindings(platform, tenantId));
    }

    @PostMapping("/identity/resolve")
    public AjaxResult resolve(@RequestBody Map<String, Object> request) {
        return success(platformIdentityService.resolve(request));
    }

    @GetMapping("/identity/current")
    public AjaxResult current(@RequestParam(value = "platform", defaultValue = "feishu") String platform,
                              @RequestParam(value = "platformUserId", required = false) String platformUserId,
                              @RequestParam(value = "tenantId", required = false) String tenantId) {
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("platform", platform);
        request.put("platform_user_id", platformUserId);
        request.put("tenant_id", tenantId);
        return success(platformIdentityService.resolve(request));
    }
}
