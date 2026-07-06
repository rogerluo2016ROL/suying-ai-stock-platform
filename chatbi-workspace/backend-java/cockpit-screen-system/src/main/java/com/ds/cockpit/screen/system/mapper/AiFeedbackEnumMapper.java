package com.ds.cockpit.screen.system.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.ds.cockpit.screen.common.core.domain.entity.AiFeedbackEnumEntity;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

@Mapper
public interface AiFeedbackEnumMapper extends BaseMapper<AiFeedbackEnumEntity> {

     List<String> getFeedbackEnumQ();

     List<String> getFeedbackEnumA();
}
