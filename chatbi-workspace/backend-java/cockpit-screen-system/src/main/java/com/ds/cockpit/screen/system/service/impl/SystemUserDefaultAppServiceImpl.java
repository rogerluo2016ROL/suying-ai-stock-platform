package com.ds.cockpit.screen.system.service.impl;

import com.ds.cockpit.screen.common.core.domain.entity.SystemUserDefaultAppEntity;
import com.ds.cockpit.screen.system.mapper.SystemUserDefaultAppMapper;
import com.ds.cockpit.screen.system.service.SystemUserDefaultAppService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

/**
* @author zhouhong 用户默认应用
* @description 针对表【system_user_default_app】的数据库操作Service实现
* @createDate 2024-02-01 下午 01:39
*/
@Service
public class SystemUserDefaultAppServiceImpl implements SystemUserDefaultAppService {

    @Autowired
    private SystemUserDefaultAppMapper systemUserDefaultAppMapper;

    @Override
    public SystemUserDefaultAppEntity getDefault(SystemUserDefaultAppEntity systemUserDefaultAppEntity) {
        return systemUserDefaultAppMapper.getSystemUserDefaultApp(systemUserDefaultAppEntity);
    }

    @Override
    public boolean setDefaultApp(SystemUserDefaultAppEntity systemUserDefaultAppEntity) {
        SystemUserDefaultAppEntity systemUserDefaultApp = systemUserDefaultAppMapper.getSystemUserDefaultApp(systemUserDefaultAppEntity);
        if(systemUserDefaultApp != null){
            int updateById = systemUserDefaultAppMapper.unAvailability(systemUserDefaultApp.getId());
        }
        int insert = systemUserDefaultAppMapper.insertEntity(systemUserDefaultAppEntity);
        if(insert > 0){
            return true;
        }
        return false;
    }
}




