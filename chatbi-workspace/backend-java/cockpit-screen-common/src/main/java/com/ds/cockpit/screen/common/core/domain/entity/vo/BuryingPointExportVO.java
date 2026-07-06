package com.ds.cockpit.screen.common.core.domain.entity.vo;

import cn.hutool.core.annotation.Alias;
import com.ds.cockpit.screen.common.annotation.Excel;
import io.swagger.annotations.ApiModel;
import io.swagger.annotations.ApiModelProperty;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.experimental.Accessors;

@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
public class BuryingPointExportVO {

    /**
     * 用户编码
     */
    @Excel(name = "用户ID")
    @Alias("用户ID")
    private String userId;

    /**
     * 姓名
     */
    @Excel(name = "姓名")
    @Alias("姓名")
    private String name;

    /**
     * 环境类别：0：企微移动，8：大屏
     */
    @Excel(name = "环境类别/应用终端")
    @Alias("环境类别/应用终端")
    private String environment;

    /**
     * 停留时长
     */
    @Excel(name = "停留时长")
    @Alias("停留时长")
    private String lengthOfStay;

    /**
     * 维度：0：首页，1：指标卡，2：详细页面
     */
    @Excel(name = "维度")
    @Alias("维度")
    private String dim;

    /**
     * 首页
     */
    @Excel(name = "首页")
    @Alias("首页")
    private String homePage;

    /**
     * 领域
     */
    @Excel(name = "领域")
    @Alias("领域")
    private String fieldPage;

    /**
     * dim=1:指标卡，dim=2：详细页面
     */
    @Excel(name = "详细页面")
    @Alias("详细页面")
    private String indicatorPage;

    /**
     * 日期 yyyy-MM-dd
     */
    @Excel(name = "日期")
    @Alias("日期")
    private String dates;

    /**
     * 插入时间
     */
    @Excel(name = "时间")
    @Alias("时间")
    private String insertTime;

    /**
     * 部门
     */
    @Excel(name = "部门")
    @Alias("部门")
    private String department;

    /**
     * 次数
     */
    @Excel(name = "访问次数")
    @Alias("访问次数")
    private String numbers;

}
