package com.ds.cockpit.screen.system.service;

import com.ds.cockpit.screen.common.core.domain.entity.SystemUserDefaultAppEntity;

/**
 * @Author: ZhouHong 用户默认应用
 * @description 针对表【system_user_default_app】的数据库操作Service
 * @Date: 2024-02-01 下午 01:39
 */
public interface SystemUserDefaultAppService {

    SystemUserDefaultAppEntity getDefault(SystemUserDefaultAppEntity systemUserDefaultAppEntity);

    boolean setDefaultApp(SystemUserDefaultAppEntity systemUserDefaultAppEntity);
}
