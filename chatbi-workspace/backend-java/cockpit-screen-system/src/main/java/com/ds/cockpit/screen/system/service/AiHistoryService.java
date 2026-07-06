package com.ds.cockpit.screen.system.service;

import com.ds.cockpit.screen.common.core.domain.entity.AiHistoryEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.AiHistoryRequestVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.AiHistoryResponseVo;

import java.util.List;

public interface AiHistoryService {

    //int getburyingpoint(BuryingPointRequestVO vo);

    //List<AiHistoryResponseVo> getHistoryrecord (AiHistoryRequestVO vo);

    List<AiHistoryEntity> getHistory (AiHistoryRequestVO vo);

    List<AiHistoryResponseVo> getHistoryRecordList(AiHistoryRequestVO vo);

    List<AiHistoryEntity> getHistoryDetailsList(AiHistoryRequestVO vo);
}
