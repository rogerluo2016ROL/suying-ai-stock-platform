package com.ds.cockpit.screen.common.core.domain.entity.vo;

import cn.hutool.core.annotation.Alias;
import com.ds.cockpit.screen.common.annotation.Excel;
import com.fasterxml.jackson.annotation.JsonFormat;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.experimental.Accessors;
import org.springframework.format.annotation.DateTimeFormat;

import java.time.LocalDateTime;

/**
 * @Author: ZhouHong
 * @Date: 2025-07-07 上午 09:37
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
public class AiHistoryAnswerNodeVO {

    @Excel(name = "序号")
    @Alias("序号")
    private Long id;

    @Excel(name = "用户ID")
    @Alias("用户ID")
    private String userId;

    @Excel(name = "用户姓名")
    @Alias("用户姓名")
    private String userName;

    @Excel(name = "问题")
    @Alias("问题")
    private String question;

    @Excel(name = "AI回答")
    @Alias("AI回答")
    private String answer;

    //@Excel(name = "节点-开始")
    //private String nodeStart;

    @Excel(name = "问题识别")
    @Alias("问题识别")
    private String nodeProblemIdentification;

    @Excel(name = "知识检索")
    @Alias("知识检索")
    private String nodeKnowledgeRetrieval;

    @Excel(name = "关键数据检索（ AI 生成 SQL 语句）")
    @Alias("关键数据检索（ AI 生成 SQL 语句）")
    private String nodeAISQL;

    @Excel(name = "数据获取（SQL 语句查询获取数据）")
    @Alias("数据获取（SQL 语句查询获取数据）")
    private String nodeDataAcquisition;

    @Excel(name = "重复关键数据检索（AI 修正重写 SQL ）")
    @Alias("重复关键数据检索（AI 修正重写 SQL ）")
    private String nodeAISQL2;

    @Excel(name = "重复数据获取（第二次 SQL 语句查询获取数据）")
    @Alias("重复数据获取（第二次 SQL 语句查询获取数据）")
    private String nodeDataAcquisition2;

    @Excel(name = "数据口径说明（大模型写数据口径）")
    @Alias("数据口径说明（大模型写数据口径）")
    private String nodeDataCaliber;

    @Excel(name = "数据解读（问数和分析判断）")
    @Alias("数据解读（问数和分析判断）")
    private String nodeDataInterpretation;

    @Excel(name = "生成完成")
    @Alias("生成完成")
    private String nodeEnd;

    @Excel(name = "回答耗时")
    @Alias("回答耗时")
    private String answerTime;

    @JsonFormat(timezone = "GMT+8", pattern = "yyyy-MM-dd HH:mm:ss")
    @DateTimeFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    @Excel(name = "创建时间")
    @Alias("创建时间")
    private LocalDateTime createTime;

    @JsonFormat(timezone = "GMT+8", pattern = "yyyy-MM-dd HH:mm:ss")
    @DateTimeFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    @Excel(name = "更新时间")
    @Alias("更新时间")
    private LocalDateTime updateTime;

}
