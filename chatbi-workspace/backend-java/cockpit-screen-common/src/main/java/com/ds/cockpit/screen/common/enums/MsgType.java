package com.ds.cockpit.screen.common.enums;

import com.fasterxml.jackson.annotation.JsonValue;

/**
 * @program: daily
 * @ClassName MsgType
 * @description:
 * @author: lukx
 * @create: 2022-05-19 11:39
 * @Version 1.0
 **/
public enum MsgType {
    /**
     * 消息类型
     */
    TEXT("text", "文本消息"),
    IMAGE("image", "图片消息"),
    VOICE("voice", "语音消息"),
    VIDEO("video", "视频消息"),
    FILE("file", "文件消息"),
    TEXTCARD("textcard", "文本卡片消息"),
    NEWS("news", "图文消息"),
    MPNEWS("mpnews", "图文消息"),
    MARKDOWN("markdown", "markdown消息"),
    MINIPROGRAM_NOTICE("miniprogram_notice", "小程序通知消息"),
    INTERACTIVE_TASK_CARD("interactive_taskcard", "任务卡片消息"),
    EVENT("event", "事件消息"),
    LOCATION("location", "位置消息"),
    LINK("link", "链接消息");

    @JsonValue
    private final String type;
    private final String description;


    MsgType(String type, String description) {
        this.type = type;
        this.description = description;
    }

    public String getType() {
        return type;
    }
}
