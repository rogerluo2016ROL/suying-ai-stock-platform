package com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi;

import lombok.Data;

@Data
public class ChatBIFeedbackRequest {
    private Long id;
    private String sessionId;
    private String messageId;
    private String rating;
    private String reason;
    private String comment;
    private String userId;
}
