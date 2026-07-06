package com.ds.cockpit.screen.system.service.chatbi;

import java.util.Map;

public interface ChatBILLMGatewayService {
    Map<String, Object> generate(Map<String, Object> request);
}

