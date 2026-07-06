package com.ds.cockpit.screen.system.service;

import com.ds.cockpit.screen.common.core.domain.entity.GacEvaluationAnalysis;
import com.ds.cockpit.screen.system.domain.vo.SSOUserInfoResVo;

import javax.servlet.http.HttpServletRequest;
import java.util.List;

/**
 * 评价分析 业务层
 * 
 * @author ruoyi
 */
public interface IGacEvaluationAnalysisService
{
    /**
     * 根据条件查询数据列表
     * @param gacEvaluationAnalysis
     * @return
     */
    List<GacEvaluationAnalysis> selectListBy(HttpServletRequest request, GacEvaluationAnalysis gacEvaluationAnalysis);

    /**
     * 新增评价分析
     * @param gacEvaluationAnalysis
     * @return
     */
    int addEvaluationAnalysis(HttpServletRequest request, GacEvaluationAnalysis gacEvaluationAnalysis);

    SSOUserInfoResVo checkArgument(HttpServletRequest request) throws Exception;

    int deleteFiles(HttpServletRequest request, String id);
}
