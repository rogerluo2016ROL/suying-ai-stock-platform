package com.ds.cockpit.screen.system.service.chatbi;

import com.ds.cockpit.screen.common.core.domain.AjaxResult;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ChatBIAgentVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ChatBIFeedbackRequest;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ChatBIRequest;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ChatBISessionVO;
import reactor.core.publisher.Flux;

import java.util.List;

public interface ChatBIOrchestratorService {
    ChatBISessionVO createSession();

    AjaxResult prepareMessage(ChatBIRequest request);

    Flux<AjaxResult> stream(ChatBIRequest request);

    AjaxResult feedback(ChatBIFeedbackRequest request);

    List<ChatBIAgentVO> agents();

    List<ChatBISessionVO> sessions();

    AjaxResult sessionDetail(String sessionId);
}
