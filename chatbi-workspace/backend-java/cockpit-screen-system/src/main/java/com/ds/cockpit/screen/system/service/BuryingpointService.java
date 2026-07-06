package com.ds.cockpit.screen.system.service;

import com.ds.cockpit.screen.common.core.domain.entity.vo.BuryingPointExportVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.BuryingPointRequestVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.BuryingResponseVo;

import java.util.List;

public interface BuryingpointService {

    int getburyingpoint(BuryingPointRequestVO vo);

    List<BuryingResponseVo> getBuryingHits (BuryingPointRequestVO vo);

    List<BuryingPointExportVO> exportBuryingpoint(String startTime, String endTime, String environment);
}
