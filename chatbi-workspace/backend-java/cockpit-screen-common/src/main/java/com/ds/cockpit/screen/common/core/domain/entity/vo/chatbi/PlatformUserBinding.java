package com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi;

import lombok.Data;

import java.util.List;

@Data
public class PlatformUserBinding {
    private String bindingId;
    private String platform;
    private String platformUserId;
    private String tenantId;
    private String internalUserId;
    private String displayName;
    private List<String> roles;
    private List<String> permissions;
    private String status;
}
