package com.ds.cockpit.screen.system.service.chatbi;

import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ChatBIFeedbackRequest;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ChatBIRequest;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ChatBISessionVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ChatBIStreamEvent;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ToolCallResponse;

import java.util.List;

public interface ChatBIConversationStore {
    ChatBISessionVO saveSession(ChatBISessionVO session, ChatBIRequest request);

    ChatBISessionVO findSession(String sessionId);

    List<ChatBISessionVO> listSessions();

    void savePreparedMessage(String sessionId, String messageId, ChatBIRequest request);

    void saveCompletedMessage(String sessionId, String messageId, String answer, String intent);

    void saveEvent(String sessionId, String messageId, int eventSeq, ChatBIStreamEvent event);

    void saveToolCall(String sessionId, String messageId, String intent, ToolCallResponse response);

    void saveFeedback(ChatBIFeedbackRequest request);
}

