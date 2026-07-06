package com.ds.cockpit.screen.common.core.domain.entity.vo;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonIgnore;
import lombok.Data;
import org.springframework.format.annotation.DateTimeFormat;

import javax.validation.constraints.NotNull;
import java.util.Date;

/**
 * @Author: ZhouHong
 * @Date: 2024-12-18 下午 03:10
 */
@Data
public class GacEvaluationAnalysisVo {

    /**
     * 一级模块
     */
    @NotNull(message = "一级模块不能为空")
    private String moduleLv1;

    /**
     * 二级模块
     */
    @NotNull(message = "二级模块不能为空")
    private String moduleLv2;

    /**
     * 三级模块
     */
    @NotNull(message = "三级模块不能为空")
    private String moduleLv3;

    /**
     * 分析维度
     */
    private String analysisDimension;

    /**
     * 明细维度
     */
    private String detailDimension;

    /**
     * 预留字段(暂未使用)-urls
     */
    private String reserveColumn;

    /**
     * 时间维度（日周月年）
     */
    @NotNull(message = "时间维度不能为空")
    private String dataType;

    /**
     * 数据时间
     */
    @NotNull(message = "数据时间不能为空")
    private String dataTime;

    /**
     * 开始时间
     */
    @JsonFormat(timezone = "GMT+8", pattern = "yyyy-MM-dd")
    private Date startTime;

    /**
     * 结束时间
     */
    @JsonFormat(timezone = "GMT+8", pattern = "yyyy-MM-dd")
    private Date endTime;

    /**
     * 描述
     */
    //@JsonIgnore
    private String description;

    /**
     * 评价分析
     */
    private String evaluationAnalysis;

    /**
     * 评价文件上传地址(多个用,分割)【可用于下载、预览】
     */
    private String evaluationAnalysisFile;

    /**
     * 上传文件原始名称(多个用,分割)
     */
    private String originalFilenames;

    /**
     * 上传文件存储时的实际名称（多个用,分割）
     */
    private String newFileNames;

    /**
     * 保存、提交
     */
    private String status;

}
