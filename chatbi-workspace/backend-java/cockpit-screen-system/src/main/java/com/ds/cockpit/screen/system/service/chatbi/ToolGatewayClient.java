package com.ds.cockpit.screen.system.service.chatbi;

import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ToolCallResponse;

public interface ToolGatewayClient {
    ToolCallResponse callByIntent(String intent, String question);
}
