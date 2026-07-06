package com.ds.cockpit.screen.system.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.ds.cockpit.screen.common.core.domain.entity.GacEvaluationAnalysis;
import com.ds.cockpit.screen.common.core.domain.entity.SysDept;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

/**
 * @Author: ZhouHong
 * @Date: 2024-12-19 上午 11:46
 */
@Mapper
public interface GacEvaluationAnalysisMapper  extends BaseMapper<GacEvaluationAnalysis> {

    List<GacEvaluationAnalysis> selectListBy(GacEvaluationAnalysis gacEvaluationAnalysis);

    /**
     * 新增
     *
     * @param gacEvaluationAnalysis 信息
     * @return 结果
     */
    int insertGacEvaluationAnalysis(GacEvaluationAnalysis gacEvaluationAnalysis);

    GacEvaluationAnalysis selectById(String id);

    int updateAnalysis(GacEvaluationAnalysis gacEvaluationAnalysis);

}
