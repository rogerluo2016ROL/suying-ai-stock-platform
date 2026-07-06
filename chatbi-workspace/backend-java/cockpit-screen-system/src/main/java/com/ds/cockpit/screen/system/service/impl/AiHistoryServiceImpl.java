package com.ds.cockpit.screen.system.service.impl;

import com.ds.cockpit.screen.common.core.domain.entity.AiHistoryEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.AiHistoryRequestVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.AiHistoryResponseVo;
import com.ds.cockpit.screen.system.mapper.AiHistoryMapper;
import com.ds.cockpit.screen.system.service.AiHistoryService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.util.List;

@Slf4j
@Service
public class AiHistoryServiceImpl implements AiHistoryService {

    @Resource
    private AiHistoryMapper aiHistoryMapper;

    /**
     * 获取指定用户历史会话信息
     * @param vo
     * @return
     */
    @Override
    public List<AiHistoryResponseVo> getHistoryRecordList(AiHistoryRequestVO vo) {
        log.info("获取指定用户历史会话信息(简要版)");
        return aiHistoryMapper.getHistoryRecordList(vo);
    }

    @Override
    public List<AiHistoryEntity> getHistoryDetailsList(AiHistoryRequestVO vo) {
        log.info("获取指定时间历史会话信息(反馈版)");
        return aiHistoryMapper.getHistoryDetailsListNotNull(vo);
    }

    /**
     * 获取指定用户指定会话全部问答信息
     * @param vo
     * @return
     */
    @Override
    public List<AiHistoryEntity> getHistory(AiHistoryRequestVO vo) {
        log.info("获取指定用户指定会话全部问答信息");
        return aiHistoryMapper.getHistory(vo);

    }

}
