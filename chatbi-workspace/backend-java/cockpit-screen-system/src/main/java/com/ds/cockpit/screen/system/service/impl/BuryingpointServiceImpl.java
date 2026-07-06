package com.ds.cockpit.screen.system.service.impl;

import com.alibaba.fastjson2.JSON;
import com.baomidou.mybatisplus.core.toolkit.CollectionUtils;
import com.ds.cockpit.screen.common.core.domain.entity.AiHistoryEntity;
import com.ds.cockpit.screen.common.core.domain.entity.SystemBuryingPointRecordEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.BuryingPointExportVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.BuryingPointRequestVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.BuryingResponseVo;
import com.ds.cockpit.screen.common.core.domain.entity.vo.ai.GacDifyData;
import com.ds.cockpit.screen.common.utils.StringUtils;
import com.ds.cockpit.screen.system.mapper.SystemBuryingPointMapper;
import com.ds.cockpit.screen.system.service.BuryingpointService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

@Service
public class BuryingpointServiceImpl implements BuryingpointService {

    //@Autowired
    @Resource
    private SystemBuryingPointMapper systemBuryingPointMapper;

    @Override
    public int  getburyingpoint(BuryingPointRequestVO vo) {
        /*SystemBuryingPointRecordEntity result = systemBuryingPointMapper.getDetailsBy(vo);;
         if(result != null){
             return systemBuryingPointMapper.updateEntity(vo);
         }else{
             return systemBuryingPointMapper.insertEntity(vo);
         }*/
        return systemBuryingPointMapper.insertEntity(vo);
    }

    @Override
    public List<BuryingResponseVo> getBuryingHits(BuryingPointRequestVO vo) {

        return systemBuryingPointMapper.getBuryingHits(vo);
    }

    @Override
    public List<BuryingPointExportVO> exportBuryingpoint(String startTime, String endTime, String environment) {

        List<BuryingPointExportVO> data = new ArrayList();
        List<SystemBuryingPointRecordEntity> buryingpointList = systemBuryingPointMapper.getBuryingpointBy(startTime, endTime, environment);
        if(CollectionUtils.isNotEmpty(buryingpointList)){
            for (SystemBuryingPointRecordEntity buryingPointRecord : buryingpointList) {
                BuryingPointExportVO buryingPointExportVO = new BuryingPointExportVO();
                buryingPointExportVO.setUserId(buryingPointRecord.getUserId());
                buryingPointExportVO.setName(buryingPointRecord.getName());
                buryingPointExportVO.setEnvironment(buryingPointRecord.getEnvironment());
                buryingPointExportVO.setLengthOfStay(buryingPointRecord.getLengthOfStay());
                buryingPointExportVO.setDim(buryingPointRecord.getDim());
                buryingPointExportVO.setHomePage(buryingPointRecord.getHomePage());
                buryingPointExportVO.setFieldPage(buryingPointRecord.getFieldPage());
                buryingPointExportVO.setIndicatorPage(buryingPointRecord.getIndicatorPage());
                buryingPointExportVO.setDates(buryingPointRecord.getDates());
                buryingPointExportVO.setInsertTime(buryingPointRecord.getInsertTime());
                buryingPointExportVO.setDepartment(buryingPointRecord.getDepartment());
                buryingPointExportVO.setNumbers(buryingPointRecord.getNumbers());
                data.add(buryingPointExportVO);
            }
        }
        return data;
    }

}
