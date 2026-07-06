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

// 流程节点
@Data
@TableName(value ="ai_flow_node")
public class AiFlowNodeEntity extends Model<AiFlowNodeEntity> implements Serializable {

  @TableId(type = IdType.AUTO)
  private Long id;

  /**
   * 类型(NODE)
   */
  private String types;

  /**
   * 节点名称
   */
  private String nodeName;

  /**
   * 节点名称（别名）
   */
  private String nickName;

  /**
   * 可用(可用节点-1，不可用节点-0)
   */
  private String availability;

  /**
   * 是否展示（展示-1，不展示-0）
   */
  private String isShow;

  /**
   * 排序
   */
  private int dictSort;

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

}



