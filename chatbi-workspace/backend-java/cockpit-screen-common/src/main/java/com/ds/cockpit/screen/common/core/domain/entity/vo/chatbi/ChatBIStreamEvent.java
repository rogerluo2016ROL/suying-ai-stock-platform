package com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi;

import lombok.Data;

import java.util.Map;

@Data
public class ChatBIStreamEvent {
    private String type;
    private String node;
    private String times;
    private String message;
    private String isShow;
    private String sessionId;
    private String messageId;
    private Map<String, Object> payload;

    public static ChatBIStreamEvent of(String type, String node, String times, String message, String isShow) {
        ChatBIStreamEvent event = new ChatBIStreamEvent();
        event.setType(type);
        event.setNode(node);
        event.setTimes(times);
        event.setMessage(message);
        event.setIsShow(isShow);
        return event;
    }
}
