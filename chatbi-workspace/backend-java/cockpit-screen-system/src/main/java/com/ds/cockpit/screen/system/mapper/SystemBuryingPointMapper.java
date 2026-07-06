package com.ds.cockpit.screen.system.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.ds.cockpit.screen.common.core.domain.entity.SystemBuryingPointRecordEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.BuryingPointRequestVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.BuryingResponseVo;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

@Mapper
public interface SystemBuryingPointMapper extends BaseMapper<SystemBuryingPointRecordEntity> {

     int insertEntity(@Param("vo") BuryingPointRequestVO vo);

     int updateEntity(@Param("vo") BuryingPointRequestVO vo);

     SystemBuryingPointRecordEntity getDetailsBy(@Param("vo") BuryingPointRequestVO vo);

     Integer getDetails();

     List<BuryingResponseVo> getBurying(@Param("vo") BuryingPointRequestVO vo);

     List<BuryingResponseVo> getBuryingHits(@Param("vo") BuryingPointRequestVO vo);

     List<SystemBuryingPointRecordEntity> getBuryingpointBy(@Param("startTime")String startTime, @Param("endTime")String endTime, @Param("environment")String environment);

}
