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
@TableName(value ="ai_agent_type_dify")
public class AiAgentType extends Model<AiAgentType> implements Serializable {

  @TableId(type = IdType.AUTO)
  private Long id;

  /**
   * 代理/智能体id
   */
  private String agentId;

  /**
   * 标题/名称
   */
  private String title;

  /**
   * 用户key
   */
  private String agentKey;

  /**
   * 类型——用于区分分词和提问
   */
  private String typeCode;

  /**
   * 类型——用于区分分词和提问
   */
  private String typeValue;

  /**
   * 请求路径-前缀
   */
  private String pathValue;

  /**
   * 状态
   */
  private String status;

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
   * 备注
   */
  private String remarks;

}



