package com.ds.cockpit.screen.system.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.ds.cockpit.screen.common.core.domain.entity.SystemUserDefinedMenuEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.DmUserMenuRequestVo;
import com.ds.cockpit.screen.common.core.domain.entity.vo.MenuEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.UserMenuPermVo;

import java.util.List;
import java.util.Map;

/**
* @author 18771
* @description 针对表【system_user_defined_menu】的数据库操作Service
* @createDate 2023-12-15 14:47:29
*/
public interface SystemUserDefinedMenuService extends IService<SystemUserDefinedMenuEntity> {

    boolean add(List<DmUserMenuRequestVo> vo);

    boolean delete(DmUserMenuRequestVo vo);

    List<SystemUserDefinedMenuEntity> getHomeMenuList(DmUserMenuRequestVo vo);

    List<MenuEntity> getIndexMenuList(UserMenuPermVo userMenuPermVo, String userId);

    List<SystemUserDefinedMenuEntity> getMenu(String userId);

    Map<String, List<SystemUserDefinedMenuEntity>> getCardMenu(String userId);

    List<SystemUserDefinedMenuEntity> likeByName(String userId, String name);

    List<SystemUserDefinedMenuEntity> reset(DmUserMenuRequestVo vo);
}
