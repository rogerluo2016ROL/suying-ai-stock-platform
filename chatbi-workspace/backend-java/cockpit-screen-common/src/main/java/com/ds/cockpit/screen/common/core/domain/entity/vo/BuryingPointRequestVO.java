package com.ds.cockpit.screen.common.core.domain.entity.vo;

import io.swagger.annotations.ApiModel;
import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

@Data
@ApiModel("埋点请求类")
public class BuryingPointRequestVO {

    @ApiModelProperty("数据类型")
    private String type;
    @ApiModelProperty("维度")
    private String dim;
    @ApiModelProperty("用户编号")
    private String userId;
    @ApiModelProperty("姓名")
    private String name;
    @ApiModelProperty("日期")
    private String dates;
    @ApiModelProperty("停留时间")
    private String lengthOfStay;
    @ApiModelProperty("部门")
    private String department;
    @ApiModelProperty("环境类别：0：生产，1：测试")
    private String environment;
    @ApiModelProperty("首页")
    private String homePage;
    @ApiModelProperty("页面")
    private String fieldPage;
    @ApiModelProperty("指标卡/详细页面")
    private String indicatorPage;
    //@ApiModelProperty("详细页面")
    //private String detailed_page;
    @ApiModelProperty("插入时间")
    private String insertTime;
    @ApiModelProperty("领域")
    private String domain;





}
