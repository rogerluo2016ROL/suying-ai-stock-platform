package com.ds.cockpit.screen.common.core.domain.entity.vo;

import com.fasterxml.jackson.annotation.JsonFormat;
import io.swagger.annotations.ApiModelProperty;
import lombok.Data;
import org.springframework.format.annotation.DateTimeFormat;

import java.io.Serializable;
import java.time.LocalDateTime;

@Data
public class AiHistoryResponseVo implements Serializable {
    private Long id;
    @ApiModelProperty("用户姓名")
    private String userName;
    @ApiModelProperty("用户姓名")
    private String userId;
    @ApiModelProperty("会话ID")
    private String conversationId;
    @ApiModelProperty("会话唯一ID")
    private String sessionUuid;
    @ApiModelProperty("问题")
    private String question;
    @ApiModelProperty("回答内容")
    private String answer;
    @ApiModelProperty("0=不满意,1=满意")
    private String isGood;
    @ApiModelProperty("时间戳")
    private String timestamp;
    @ApiModelProperty("创建时间")
    @JsonFormat(timezone = "GMT+8", pattern = "yyyy-MM-dd HH:mm:ss")
    @DateTimeFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime createTime;

    /**
     * 回答耗时
     */
    private String answerTime;

    /**
     * 问题反馈/建议(提问)
     */
    private String questionFeedback;

    /**
     * 问题反馈/建议(回答)
     */
    private String answerFeedback;

    /**
     * 问题反馈/建议(补充)
     */
    private String opinionFeedback;

}
