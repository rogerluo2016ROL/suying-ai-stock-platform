package com.ds.cockpit.screen.system.service.impl;

import com.baomidou.mybatisplus.core.toolkit.CollectionUtils;
import com.ds.cockpit.screen.common.core.domain.AjaxResult;
import com.ds.cockpit.screen.common.core.domain.entity.AiAgentType;
import com.ds.cockpit.screen.system.mapper.AiAgentTypeMapper;
import com.ds.cockpit.screen.system.service.AiAgentTypeDifyService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.util.ArrayList;
import java.util.List;

/**
 * @Author: ZhouHong
 * @Date: 2025/7/30 09:43
 */
@Slf4j
@Service
public class AiAgentTypeDifyServiceImpl implements AiAgentTypeDifyService {

    @Resource
    private AiAgentTypeMapper aiAgentTypeMapper;

    @Override
    public AjaxResult getListQAndA() {
        log.info("获取用户AI问答模型列表");
        List<AiAgentType> agentTypeQA = aiAgentTypeMapper.getAgentTypeQA();
        if(CollectionUtils.isNotEmpty(agentTypeQA)){
            List<AiAgentType> qa = new ArrayList<>();
            for (AiAgentType aiAgentType : agentTypeQA) {
                AiAgentType type = new AiAgentType();
                type.setTitle(aiAgentType.getTitle());
                type.setId(aiAgentType.getId());
                qa.add(type);
            }
            return AjaxResult.success(qa);
        }else{
            return AjaxResult.error();
        }
    }

    @Override
    public AjaxResult getAgentQAndAById(Long id) {
        AiAgentType agentTypeQAById = aiAgentTypeMapper.getAgentTypeQAById(id);
        return AjaxResult.success(agentTypeQAById);
    }
}
