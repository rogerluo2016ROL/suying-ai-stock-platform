package com.ds.cockpit.screen.system.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.ds.cockpit.screen.common.core.domain.entity.SystemUserDefaultAppEntity;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * @Author: ZhouHong 用户默认应用
 * @description 针对表【system_user_default_app】的数据库操作Mapper
* @createDate 2024-02-01
*/
@Mapper
public interface SystemUserDefaultAppMapper extends BaseMapper<SystemUserDefaultAppEntity> {

    SystemUserDefaultAppEntity getSystemUserDefaultApp(@Param("entity") SystemUserDefaultAppEntity entity);

    int insertEntity(SystemUserDefaultAppEntity systemUserDefaultAppEntity);

    int unAvailability(Long id);
}




