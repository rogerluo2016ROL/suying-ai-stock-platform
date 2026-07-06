package com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi;

import lombok.Data;

@Data
public class ToolCallResponse {
    private boolean success;
    private String sourceStatus;
    private String message;
    private String rawBody;

    public static ToolCallResponse unavailable(String message) {
        ToolCallResponse response = new ToolCallResponse();
        response.setSuccess(false);
        response.setSourceStatus("unavailable");
        response.setMessage(message);
        return response;
    }

    public static ToolCallResponse ready(String rawBody) {
        ToolCallResponse response = new ToolCallResponse();
        response.setSuccess(true);
        response.setSourceStatus("ready");
        response.setRawBody(rawBody);
        return response;
    }
}
