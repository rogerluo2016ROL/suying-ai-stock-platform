package com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi;

import lombok.Data;

import java.util.List;
import java.util.Map;

@Data
public class ChatBIRequest {
    private Long id;
    private String messageId;
    private String question;
    private String query;
    private String userId;
    private String userName;
    private String sessionId;
    private String sessionUuid;
    private String answerMode;
    private Long agentId;
    private String agentCode;
    private String templateId;
    private List<String> attachments;
    private Map<String, Object> context;

    public String normalizedQuestion() {
        if (question != null && question.trim().length() > 0) {
            return question.trim();
        }
        return query == null ? "" : query.trim();
    }

    public String normalizedSessionId() {
        if (sessionId != null && sessionId.trim().length() > 0) {
            return sessionId.trim();
        }
        return sessionUuid == null ? "" : sessionUuid.trim();
    }

    public String normalizedAnswerMode() {
        if ("deep".equalsIgnoreCase(answerMode) || "深度思考".equals(answerMode)) {
            return "deep";
        }
        return "quick";
    }
}
