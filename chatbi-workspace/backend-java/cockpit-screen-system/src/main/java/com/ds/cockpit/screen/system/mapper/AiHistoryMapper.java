package com.ds.cockpit.screen.system.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.ds.cockpit.screen.common.core.domain.entity.AiHistoryEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.AiHistoryRequestVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.AiHistoryResponseVo;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Map;

@Mapper
public interface AiHistoryMapper extends BaseMapper<AiHistoryEntity> {

     AiHistoryEntity selectById(Long id);

     Integer addHistoryRecord(AiHistoryEntity aiHistoryEntity);

     Integer updateHistoryRecord(AiHistoryEntity aiHistoryEntity);

     List<AiHistoryEntity> getHistory(@Param("vo") AiHistoryRequestVO vo);

     List<AiHistoryEntity> getAiHistoryList(AiHistoryEntity aiHistoryEntity);

     List<AiHistoryResponseVo> getHistoryRecordList(@Param("vo") AiHistoryRequestVO vo);

     List<AiHistoryResponseVo> getHistoryDetailsList(@Param("vo") AiHistoryRequestVO vo);

     List<AiHistoryEntity> getHistoryDetailsListNotNull(@Param("vo") AiHistoryRequestVO vo);

     List<Map<String,Object>> getKeyWordTOP();

     List<Map<String, Object>> getQuestionTop();

     List<Map<String, Object>> getQuestionKeyTop(@Param("question") String question);

    List<AiHistoryEntity> getAIAnswerNode(@Param("startTime")String startTime, @Param("endTime")String endTime);

    List<AiHistoryEntity> getAiHistoryNotSplitWordsList();
}
