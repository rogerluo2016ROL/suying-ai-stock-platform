package com.ds.cockpit.screen.common.core.domain.entity.vo;

import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

import java.io.Serializable;

@Data
public class BuryingResponseVo implements Serializable {
    @ApiModelProperty("使用人次")
    private Integer numbers;
    @ApiModelProperty("比例")
    private String rate;
    @ApiModelProperty("日期")
    private String date;
    @ApiModelProperty("名字")
    private String name;
    @ApiModelProperty("部门")
    private String department;
    @ApiModelProperty("页面")
    private String field;
    @ApiModelProperty("dim=1:指标卡，dim=2：详细页面")
    private String indicators;
    @ApiModelProperty("停留时长")
    private String lengthofstay;
    @ApiModelProperty("首页停留时长")
    private String lengthofstay1;
    @ApiModelProperty("详细页面停留时长")
    private String lengthofstay2;

    @ApiModelProperty("领域")
    private String domain;

}
