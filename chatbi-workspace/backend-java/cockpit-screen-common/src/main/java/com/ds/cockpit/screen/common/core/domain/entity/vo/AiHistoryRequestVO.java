package com.ds.cockpit.screen.common.core.domain.entity.vo;

import io.swagger.annotations.ApiModel;
import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

@Data
@ApiModel("AI历史记录请求类")
public class AiHistoryRequestVO {
    @ApiModelProperty("用户ID")
    private String userId;
    @ApiModelProperty("用户姓名")
    private String userName;
    @ApiModelProperty("会话ID")
    private String conversationId;
    @ApiModelProperty("会话唯一ID")
    private String sessionUuid;
    @ApiModelProperty("问题")
    private String question;
    @ApiModelProperty("回答内容")
    private String answer;
    @ApiModelProperty("0=不深度思考,1=深度思考")
    private String isDeep;
    @ApiModelProperty("0=不满意,1=满意")
    private String isGood;
    @ApiModelProperty("回答耗时")
    private String answerTime;
    @ApiModelProperty("创建时间:yyyy-mm-dd hh:mm:ss")
    private String createTime;

    @ApiModelProperty("创建时间:yyyy-mm")
    private String times;


}
