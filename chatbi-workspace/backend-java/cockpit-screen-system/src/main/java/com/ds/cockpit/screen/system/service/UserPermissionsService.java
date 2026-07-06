package com.ds.cockpit.screen.system.service;

import com.ds.cockpit.screen.common.core.domain.entity.vo.MenuEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.UserMenuPermVo;

import java.util.List;

public interface UserPermissionsService {

    List<MenuEntity> getUserMenuListByUserId(String userId , UserMenuPermVo userMenuPermVo);

    List<MenuEntity> getUserMenuListBy(String accessToken, String timestamp, String terminalType);

    //String getToken(String userId);

}
