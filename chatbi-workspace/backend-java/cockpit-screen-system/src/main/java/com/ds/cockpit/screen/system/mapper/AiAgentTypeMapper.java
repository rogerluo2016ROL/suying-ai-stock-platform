package com.ds.cockpit.screen.system.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.ds.cockpit.screen.common.core.domain.entity.AiAgentType;
import com.ds.cockpit.screen.common.core.domain.entity.vo.AiHistoryRequestVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.AiHistoryResponseVo;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Map;

@Mapper
public interface AiAgentTypeMapper extends BaseMapper<AiAgentType> {

     AiAgentType selectById(Long id);

     Integer updateAgentUnused(Long id);

     Integer updateAgentUsed(Long id);

     List<AiAgentType> getAgentTypeFenci();

     List<AiAgentType> getAgentTypeQA();

     AiAgentType getAgentTypeQAById(Long id);

     AiAgentType getAgentTypeMonitor();

}
