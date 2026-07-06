package com.ds.cockpit.screen.system.service.chatbi;

import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.PlatformUserBinding;

import java.util.List;
import java.util.Map;

public interface PlatformIdentityService {
    PlatformUserBinding bind(Map<String, Object> request);

    Map<String, Object> resolve(Map<String, Object> request);

    List<PlatformUserBinding> bindings(String platform, String tenantId);
}
