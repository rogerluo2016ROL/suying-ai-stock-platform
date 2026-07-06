package com.ds.cockpit.screen.common.core.domain.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.baomidou.mybatisplus.extension.activerecord.Model;
import com.fasterxml.jackson.annotation.JsonFormat;
import lombok.Data;
import org.springframework.format.annotation.DateTimeFormat;

import java.time.LocalDateTime;
import java.util.Date;

/**
 * @Author: ZhouHong
 * @Date: 2024-12-18 下午 03:10
 */
@Data
@TableName("gac_evaluation_analysis")
public class GacEvaluationAnalysis extends Model<GacEvaluationAnalysis> {
    private static final long serialVersionUID = 1L;

    public static final String TABLE_NAME = "gac_evaluation_analysis";

    /**
     * 主键id
     */
    @TableId(type = IdType.AUTO)
    private Long id;

    /**
     * 一级模块
     */
    private String moduleLv1;

    /**
     * 二级模块
     */
    private String moduleLv2;

    /**
     * 三级模块
     */
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
     * 预留字段(暂未使用)
     */
    private String reserveColumn;

    /**
     * 时间维度（日周月年）
     */
    private String dataType;

    /**
     * 数据时间
     */
    private String dataTime;

    /**
     * 开始时间
     */
    @JsonFormat(timezone = "GMT+8", pattern = "yyyy-MM-dd")
    @DateTimeFormat(pattern = "yyyy-MM-dd")
    private Date startTime;

    /**
     * 结束时间
     */
    @JsonFormat(timezone = "GMT+8", pattern = "yyyy-MM-dd")
    @DateTimeFormat(pattern = "yyyy-MM-dd")
    private Date endTime;

    /**
     * 状态-是否删除（0正常 1停用）-暂未启用该字段
     */
    private Boolean deleted;

    /**
     * 描述
     */
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
     * 创建者-nickname
     */
    private String createBy;

    /**
     * 创建者-工号-编码
     */
    private String createCode;

    /**
     * 创建时间
     */
    @JsonFormat(timezone = "GMT+8", pattern = "yyyy-MM-dd HH:mm:ss")
    @DateTimeFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime createTime;

    /**
     * 上传文件原始名称(多个用,分割)
     */
    private String originalFilenames;

    /**
     * 上传文件存储时的实际名称（多个用,分割）
     */
    private String newFileNames;

    /**
     * 保存、提交（1、保存；2、提交）
     */
    private String status;

}
