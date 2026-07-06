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
@TableName(value ="ai_feedback_enum")
public class AiFeedbackEnumEntity extends Model<AiFeedbackEnumEntity> implements Serializable {

  @TableId(type = IdType.AUTO)
  private Long id;

  /**
   * 类型(Q&A)
   */
  private String types;

  /**
   * 评价值
   */
  private String nameValue;

  /**
   * 可用
   */
  private String availability;

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



