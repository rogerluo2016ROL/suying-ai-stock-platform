package com.ds.cockpit.screen.system.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.ds.cockpit.screen.common.core.domain.entity.AiFlowNodeEntity;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface AiFlowNodeMapper extends BaseMapper<AiFlowNodeEntity> {

     List<AiFlowNodeEntity> getAiFlowNodeList();

     List<AiFlowNodeEntity> getAiFlowNodeAllList();
}
