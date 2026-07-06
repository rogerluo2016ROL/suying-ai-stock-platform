package com.ds.cockpit.screen.common.core.domain.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.baomidou.mybatisplus.extension.activerecord.Model;
import com.fasterxml.jackson.annotation.JsonFormat;
import lombok.Data;
import org.springframework.format.annotation.DateTimeFormat;

import java.io.Serializable;
import java.time.LocalDateTime;

@Data
@TableName(value ="ai_history_message")
public class AiHistoryEntity extends Model<AiHistoryEntity> implements Serializable {

  @TableId(type = IdType.AUTO)
  private Long id;

  /**
   * 用户ID
   */
  private String userId;

  /**
   * 用户姓名
   */
  private String userName;

  /**
   * 会话ID(sessionId)
   */
  private String conversationId;

  /**
   * 智能体/代理ID
   */
  private String agentId;

  private String agentName;

  /**
   * 会话ID(sessionId)-fenci
   */
  private String fenciSessionId;

  /**
   * 智能体/代理ID-fenci
   */
  private String fenciAgentId;

  private String fenciAgentName;

  /**
   * 问题
   */
  private String question;

  /**
   * 实际问题
   */
  private String actualQuestion;

  /**
   * 问题分词
   */
  private String splitWords;

  /**
   * 回答
   */
  private String answer;

  /**
   * 回答
   */
  private String answerAll;

  /**
   * 权限-校验
   * 0=未校验通过,1=权限校验通过
   */
  private String permission;

  /**
   * 0=不深度思考,1=深度思考
   */
  private String isDeep;

  /**
   * 0=不满意,1=满意
   */
  private String isGood;

  /**
   * 回答耗时
   */
  private String answerTime;

  /**
   * 创建时间
   */
  @JsonFormat(timezone = "GMT+8", pattern = "yyyy-MM-dd HH:mm:ss")
  @DateTimeFormat(pattern = "yyyy-MM-dd HH:mm:ss")
  private LocalDateTime createTime;

  /**
   * 更新时间
   */
  @JsonFormat(timezone = "GMT+8", pattern = "yyyy-MM-dd HH:mm:ss")
  @DateTimeFormat(pattern = "yyyy-MM-dd HH:mm:ss")
  private LocalDateTime updateTime;

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

  private String remarks;

  /**
   * 说明、描述
   */
  private String descriptions;

  /**
   * 环境类别：0：企微移动，8：大屏
   */
  private String environment;

  /**
   * 单次会话
   */
  private String sessionUuid;
}



