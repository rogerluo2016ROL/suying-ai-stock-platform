package com.ds.cockpit.screen.common.core.domain.entity;

import com.baomidou.mybatisplus.annotation.TableName;
import com.baomidou.mybatisplus.extension.activerecord.Model;
import lombok.Data;

import java.io.Serializable;

@Data
@TableName(value ="system_burying_point_record")
public class SystemBuryingPointRecordEntity extends Model<SystemBuryingPointRecordEntity> implements Serializable {

  /**
   * 维度：0：首页，1：指标卡，2：详细页面
   */
  private String dim;

  /**
   * 用户编码
   */
  private String userId;

  /**
   * 姓名
   */
  private String name;

  /**
   * 日期 yyyy-MM-dd
   */
  private String dates;

  /**
   * 部门
   */
  private String department;

  /**
   * 次数
   */
  private String numbers;

  /**
   * 环境类别：0：企微移动，8：大屏
   */
  private String environment;

  /**
   * 停留时长
   */
  private String lengthOfStay;

  /**
   * 首页
   */
  private String homePage;

  /**
   * 领域
   */
  private String fieldPage;

  /**
   * dim=1:指标卡，dim=2：详细页面
   */
  private String indicatorPage;

  // private String detailedPage;

  /**
   * 插入时间
   */
  private String insertTime;

  /**
   * 领域
   */
  private String domain;
}



