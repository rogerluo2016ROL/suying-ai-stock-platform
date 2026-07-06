package com.ds.cockpit.screen.system.service.impl;

import cn.hutool.core.bean.BeanUtil;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.ds.cockpit.screen.common.core.domain.entity.SystemUserDefinedMenuEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.DmUserMenuRequestVo;
import com.ds.cockpit.screen.common.core.domain.entity.vo.MenuEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.UserMenuPermVo;
import com.ds.cockpit.screen.system.mapper.SystemUserDefinedMenuMapper;
import com.ds.cockpit.screen.system.service.SystemUserDefinedMenuService;
import com.ds.cockpit.screen.system.service.UserPermissionsService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.CollectionUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.beans.BeanUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
* @author 18771
* @description 针对表【system_user_defined_menu】的数据库操作Service实现
* @createDate 2023-12-15 14:47:29
*/
@Service
@Slf4j
public class SystemUserDefinedMenuServiceImpl extends ServiceImpl<SystemUserDefinedMenuMapper, SystemUserDefinedMenuEntity>
    implements SystemUserDefinedMenuService {


    @Autowired
    @Resource
    private SystemUserDefinedMenuMapper systemUserDefinedMenuMapper;

    @Autowired
    private UserPermissionsService userPermissionsService;

    private static String INDEX_PREMS  = "1";


    @Override
    @Transactional
    public boolean add(List<DmUserMenuRequestVo> vos) {
        // 指标卡 父子节点
        List<SystemUserDefinedMenuEntity> saveList = new ArrayList<>();
        for (DmUserMenuRequestVo vo : vos) {
            SystemUserDefinedMenuEntity entity = new SystemUserDefinedMenuEntity();
            BeanUtils.copyProperties(vo,entity);
            saveList.add(entity);
            Integer uId = vo.getUId();
            String userId = vo.getUserId();
            if(null != uId && null != userId){
                List<SystemUserDefinedMenuEntity> systemUserDefinedMenuEntities = systemUserDefinedMenuMapper.selectByParentIdAndUserId(uId,userId);
                if(null != systemUserDefinedMenuEntities){
                    for (SystemUserDefinedMenuEntity systemUserDefinedMenuEntity : systemUserDefinedMenuEntities) {
                        if(null != systemUserDefinedMenuEntity){
                            systemUserDefinedMenuEntity.setStatus(vo.getStatus());
                            saveList.add(systemUserDefinedMenuEntity);
                        }
                    }
                }
            }
        }
        int x = 0 ;
        for (SystemUserDefinedMenuEntity systemUserDefinedMenuEntity : saveList) {
            int y = systemUserDefinedMenuMapper.updateEntity(systemUserDefinedMenuEntity);
            x = x + y ;
        }
        if( x == saveList.size()){
            return true;
        }else{
            throw new RuntimeException("数据添加失败");
        }
    }

    @Override
    public boolean delete(DmUserMenuRequestVo vo) {
        return systemUserDefinedMenuMapper.deleteBatchByMenuCode(vo);
    }

    /**
     *  用户每次首次进入应用调用该接口初始化默认指标
     *  默认指标卡 status = 1
     *  未添加的指标卡 status = 0
     * @param vo
     * @return
     */
    @Override
    @Transactional
    public List<SystemUserDefinedMenuEntity> getHomeMenuList(DmUserMenuRequestVo vo) {
        String userId = vo.getUserId();
        // 获取用户权限菜单
        UserMenuPermVo userMenuPermVo = new UserMenuPermVo();
        userMenuPermVo.setAccessToken(vo.getAccessToken());
        userMenuPermVo.setTimestamp(vo.getTimestamp());
        userMenuPermVo.setTerminalType(vo.getTerminalType());
        List<MenuEntity> permissionsMenuList = this.getPermissionsMenuList(userMenuPermVo, userId);
        // 获取用户指标卡权限菜单
        List<MenuEntity> homeMenuList = this.getHomeMenuList(permissionsMenuList);

        // 判断用户是否初始化过 默认指标卡
        Long count = systemUserDefinedMenuMapper.selectCountByUserId(userId);
        List<SystemUserDefinedMenuEntity> initDefinedMenu = new ArrayList<>();
        if (count == null || count <= 0){
            // 初始化用户自定义菜单数据—— 未初始化，直接将数据中的所有选中并保存及返回
            initDefinedMenu = copyPropertiesByList(homeMenuList, new ArrayList<SystemUserDefinedMenuEntity>(), userId);
            systemUserDefinedMenuMapper.insertBatch(initDefinedMenu);
            return initDefinedMenu;
        }

        //  查询用户所有的指标卡菜单 (status=1 用于标识用户已添加)
        List<SystemUserDefinedMenuEntity> userDefinedList = systemUserDefinedMenuMapper.selectAllMenuByUserId(userId);
        if (CollectionUtils.isEmpty(userDefinedList) && !CollectionUtils.isEmpty(homeMenuList)) {
            // 非初始化逻辑
            List<SystemUserDefinedMenuEntity> userDefined = systemUserDefinedMenuMapper.selectByUserId(userId);
            // 检查需要删除的权限
            List<SystemUserDefinedMenuEntity> deleteList = userDefined.stream()
                    .filter(permissionsMenu -> !homeMenuList.stream().map(MenuEntity::getCode)
                            .collect(Collectors.toList()).contains(String.valueOf(permissionsMenu.getMenuCode())))
                    .collect(Collectors.toList());
            List<SystemUserDefinedMenuEntity> addList = new ArrayList<>();
            // 检查需要新增的权限
            for (MenuEntity permission : homeMenuList) {
                boolean found = false;
                for (SystemUserDefinedMenuEntity localPermission : userDefined) {
                    if (permission.getCode().equals(localPermission.getMenuCode())) {
                        found = true;
                        break;
                    }
                }
                if (!found) {
                    SystemUserDefinedMenuEntity entity = BeanUtil.toBean(permission, SystemUserDefinedMenuEntity.class);
                    entity.setUId(permission.getId());
                    entity.setUserId(userId);
                    // 有新增默认选中
                    entity.setStatus(1);
                    addList.add(entity);
                }
            }
            if (!CollectionUtils.isEmpty(deleteList)) {
                systemUserDefinedMenuMapper.deleteBatchUserIds(deleteList);
            }

            if (!CollectionUtils.isEmpty(addList)) {

                // 先筛选，已存权限数据在用户实际查询到的权限中进行匹配，取交集——赋值
                List<SystemUserDefinedMenuEntity> retentionList = userDefined.stream()
                        .filter(permissionsMenu -> homeMenuList.stream().map(MenuEntity::getCode)
                                .collect(Collectors.toList()).contains(String.valueOf(permissionsMenu.getMenuCode())))
                        .collect(Collectors.toList());
                if(!CollectionUtils.isEmpty(retentionList) && retentionList.size() >0){
                    // 获取不含-的菜单编码的权限数据
                    List<SystemUserDefinedMenuEntity> retentionMainMenu = retentionList.stream()
                            .filter((item) -> StringUtils.indexOfIgnoreCase(item.getMenuCode(), "-") < 0 && 1 == item.getStatus())
                            .sorted(Comparator.comparing(SystemUserDefinedMenuEntity::getOrderValue)).collect(Collectors.toList());

                    //再将已默认的下级进行默认
                    for (SystemUserDefinedMenuEntity addMenu : addList) {
                        for (SystemUserDefinedMenuEntity topList : retentionMainMenu) {
                            if (StringUtils.startsWith(addMenu.getMenuCode(),topList.getMenuCode())){
                                addMenu.setStatus(UserDefinedEnum.ADD.getStatus());
                            }
                        }
                    }
                }else{
                    // 用户权限与已存权限数据完全无交叉
                    // 直接保存即可

                }
                systemUserDefinedMenuMapper.insertBatch(addList);
            }
            return userDefinedList;
        }
        return userDefinedList;
    }

    @Override
    public List<SystemUserDefinedMenuEntity> reset(DmUserMenuRequestVo vo){
        String userId = vo.getUserId();
        boolean del = false;
        if(StringUtils.isNoneBlank(userId)){
            // 先删除再初始化
            del = systemUserDefinedMenuMapper.deleteBatchByUserId(userId);
        }else{
            throw new RuntimeException("恢复默认值失败,未查询到用户信息,请联系管理员");
        }
        if(del){
            // 再初始化
            return getHomeMenuList(vo);
        }else{
            throw new RuntimeException("恢复默认值失败,请联系管理员");
        }
    }

    /**
     * 首页->管理 用户可添加的指标卡
     * @param userId
     * @return
     */
    @Override
    public List<MenuEntity> getIndexMenuList(UserMenuPermVo userMenuPermVo, String userId) {
        log.info("获取指标卡列表====>>>>,当前用户Id:[{}],当前token相关参数:[{}]", userId, userMenuPermVo.toString());
        // 1.调用平台管家权限接口
        List<MenuEntity> permissionsMenuList = getPermissionsMenuList(userMenuPermVo, userId);
        List<SystemUserDefinedMenuEntity> userMenuList = systemUserDefinedMenuMapper.selectByUserId(userId);
        // 2.判断当前用户是否已经添加过指标卡菜单
        List<MenuEntity> resultList;
        if (!CollectionUtils.isEmpty(userMenuList)) {
            // 如果有 则求两个集合的差集
            List<SystemUserDefinedMenuEntity> finalUserMenuList = userMenuList;
            resultList = permissionsMenuList.stream()
                    .filter(permissionsMenu -> !finalUserMenuList.stream().map(SystemUserDefinedMenuEntity::getMenuCode)
                            .collect(Collectors.toList()).contains(String.valueOf(permissionsMenu.getCode())))
                    //.filter(MenuEntity::getHasAuthority)
                    .filter(menuEntity -> INDEX_PREMS.equals(menuEntity.getPerms()))
                    .collect(Collectors.toList());

        } else {
            resultList = permissionsMenuList.stream()
                    //.filter(MenuEntity::getHasAuthority)
                    .filter(menuEntity -> INDEX_PREMS.equals(menuEntity.getPerms())).collect(Collectors.toList());
        }
        return resultList;
    }


    private List<SystemUserDefinedMenuEntity> copyPropertiesByList(List<MenuEntity> defaultMenu, List<SystemUserDefinedMenuEntity> entityList, String userId) {
        defaultMenu.stream().forEach(defaultMenuEntity->{
            SystemUserDefinedMenuEntity entity = new SystemUserDefinedMenuEntity();
            //BeanUtils.copyProperties(defaultMenuEntity,entity);
            entity.setMenuCode(defaultMenuEntity.getCode());
            entity.setName(defaultMenuEntity.getName());
            entity.setOrderValue(defaultMenuEntity.getOrderBy());
            entity.setPluginPath(defaultMenuEntity.getUrl());
            entity.setParentId(defaultMenuEntity.getPId().toString());
            entity.setUId(defaultMenuEntity.getId());
            entity.setUserId(userId);
            entity.setStatus(UserDefinedEnum.ADD.getStatus());
            entityList.add(entity);
        });
        return entityList;
    }

    private List<SystemUserDefinedMenuEntity> copyPropertiesAndSetStatusByList(List<MenuEntity> defaultMenu, List<SystemUserDefinedMenuEntity> entityList, String userId) {
        defaultMenu.stream().forEach(defaultMenuEntity->{
            SystemUserDefinedMenuEntity entity = new SystemUserDefinedMenuEntity();
            //BeanUtils.copyProperties(defaultMenuEntity,entity);
            entity.setMenuCode(defaultMenuEntity.getCode());
            entity.setName(defaultMenuEntity.getName());
            entity.setOrderValue(defaultMenuEntity.getOrderBy());
            entity.setPluginPath(defaultMenuEntity.getUrl());
            entity.setParentId(defaultMenuEntity.getPId().toString());
            entity.setUId(defaultMenuEntity.getId());
            entity.setUserId(userId);
            //entity.setStatus(1);
            entity.setStatus(UserDefinedEnum.ADD.getStatus());
            entityList.add(entity);
        });
        return entityList;
    }


    @Override
    public List<SystemUserDefinedMenuEntity> getMenu(String userId) {
        return systemUserDefinedMenuMapper.selectDefinedMenuByUserId(userId);
    }


    /**
     *  卡片管理指标卡菜单
     * @param userId
     * @return
     */
    @Override
    public Map<String, List<SystemUserDefinedMenuEntity>> getCardMenu(String userId) {
        List<String> menuNameList = Arrays.asList( "行业产销", "广汽产销", "传祺", "埃安", "昊铂","国际" );
        List<SystemUserDefinedMenuEntity> userDefinedList = systemUserDefinedMenuMapper.selectByUserId(userId);
        if (CollectionUtils.isEmpty(userDefinedList)){
            return new HashMap<>();
        }
        List<SystemUserDefinedMenuEntity> result = new ArrayList<>();
        userDefinedList.stream().forEach(userDefined ->{
            if (menuNameList.contains(userDefined.getParentName())){
                result.add(userDefined);
            }
        });
        return result.stream().collect(Collectors.groupingBy(SystemUserDefinedMenuEntity::getParentName));

    }



    private static List<SystemUserDefinedMenuEntity> buildMenuTree(List<SystemUserDefinedMenuEntity> menuEntities, String parentId) {
        List<SystemUserDefinedMenuEntity> menuList = new ArrayList<>();
        for (SystemUserDefinedMenuEntity menuEntity : menuEntities) {
            if (menuEntity.getParentId().equals(parentId)) {
                SystemUserDefinedMenuEntity menu = new SystemUserDefinedMenuEntity();
                // 设置菜单项的属性
                // ...

                // 递归构建子菜单
                List<SystemUserDefinedMenuEntity> children = buildMenuTree(menuEntities, menuEntity.getMenuCode());
//                menu.setChildMenu(children);

                menuList.add(menu);
            }
        }
        return menuList;
    }


    @Override
    public List<SystemUserDefinedMenuEntity> likeByName(String userId , String name) {
        return systemUserDefinedMenuMapper.selectLikeByName(userId,name);
    }


    /**
     * 获取首页菜单集合
     *
     * @param permissionsMenuList
     */
    private List<MenuEntity> getHomeMenuList(List<MenuEntity> permissionsMenuList) {
        if (CollectionUtils.isEmpty(permissionsMenuList)) {
           return new ArrayList<>();
        }
        List<MenuEntity> menuList = permissionsMenuList.stream()
                //.filter(MenuEntity::getHasAuthority)  // 筛选为 true 的
                .filter(menuEntity -> INDEX_PREMS.equals(menuEntity.getPerms())).collect(Collectors.toList()); // 筛选后端权限标识为 “1” 的

        return menuList.stream().sorted(Comparator.comparing(MenuEntity::getOrderBy)).collect(Collectors.toList());

    }

    private List<MenuEntity> getPermissionsMenuList(UserMenuPermVo userMenuPermVo , String userId) {
        // String token = userPermissionsService.getToken(userId);
        List<MenuEntity> menuEntityList = userPermissionsService.getUserMenuListByUserId(userId, userMenuPermVo);
        return menuEntityList;
    }

}




