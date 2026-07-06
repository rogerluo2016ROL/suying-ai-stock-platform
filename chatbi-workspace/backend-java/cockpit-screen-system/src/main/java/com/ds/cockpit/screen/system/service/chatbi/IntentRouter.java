package com.ds.cockpit.screen.system.service.chatbi;

import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.IntentResult;

public interface IntentRouter {
    IntentResult route(String question);
}
