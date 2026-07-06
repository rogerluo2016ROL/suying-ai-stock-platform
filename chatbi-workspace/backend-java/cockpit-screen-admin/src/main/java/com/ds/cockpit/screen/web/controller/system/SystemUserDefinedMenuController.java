package com.ds.cockpit.screen.web.controller.system;

import cn.hutool.http.HttpRequest;
import com.ds.cockpit.screen.common.core.controller.BaseControllerNew;
import com.ds.cockpit.screen.common.core.domain.entity.SystemUserDefinedMenuEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.DmUserMenuRequestVo;
import com.ds.cockpit.screen.common.core.domain.entity.vo.MenuEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.UserMenuPermVo;
import com.ds.cockpit.screen.common.response.ApiResponse;
import com.ds.cockpit.screen.system.service.SystemUserDefinedMenuService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import javax.servlet.http.HttpServletRequest;
import java.util.List;
import java.util.Map;

@Api(value = "指标卡管理", tags = "指标卡管理")
@ApiOperation(value = "指标卡管理")
@RestController
@RequestMapping("/index/menus")
public class SystemUserDefinedMenuController extends BaseControllerNew {

    @Autowired
    private SystemUserDefinedMenuService systemUserDefinedMenuService;

    @ApiOperation(value = "首页获取可添加的指标卡集合")
    @GetMapping("/getIndexMenuList")
    public ApiResponse<List<MenuEntity>> getIndexMenuList(
            @RequestParam("userId") String userId,
            @RequestParam("accessToken") String accessToken,
            @RequestParam("timestamp") String timestamp,
            @RequestParam("terminalType") String terminalType
            ) throws Throwable {
        UserMenuPermVo userMenuPermVo = new UserMenuPermVo();
        userMenuPermVo.setAccessToken(accessToken);
        userMenuPermVo.setTimestamp(timestamp);
        userMenuPermVo.setTerminalType(terminalType);
        List<MenuEntity> resultVo = systemUserDefinedMenuService.getIndexMenuList(userMenuPermVo, userId);
        return success(resultVo);
    }

    @ApiOperation(value = "添加指标卡")
    @PostMapping("/add")
    public ApiResponse<List<MenuEntity>> add(@RequestBody List<DmUserMenuRequestVo> vo) throws Throwable {
        return success(systemUserDefinedMenuService.add(vo));
    }

    @ApiOperation(value = "删除指标卡")
    @PostMapping("/delete")
    public ApiResponse<Boolean> delete(@RequestBody DmUserMenuRequestVo vo) throws Throwable {
        return success(systemUserDefinedMenuService.delete(vo));
    }


    @ApiOperation(value = "初始化用户指标卡菜单")
    @PostMapping("/getHomeMenuList")
    public ApiResponse<List<SystemUserDefinedMenuEntity>> getHomeMenuList(@RequestBody DmUserMenuRequestVo vo) throws Throwable {
        return success(systemUserDefinedMenuService.getHomeMenuList(vo));
    }

    @ApiOperation(value = "首页指标列表菜单")
    @GetMapping("/getMenu")
    public ApiResponse<List<SystemUserDefinedMenuEntity>> getMenu(@RequestParam("userId") String userId) throws Throwable {
        return success(systemUserDefinedMenuService.getMenu(userId));
    }


    @ApiOperation(value = "卡片管理指标列表菜单")
    @GetMapping("/getCardMenu")
    public ApiResponse<Map<String, List<SystemUserDefinedMenuEntity>>> getCardMenu(@RequestParam("userId") String userId) throws Throwable {
        return success(systemUserDefinedMenuService.getCardMenu(userId));
    }

    @ApiOperation(value = "模糊查询用户已拥有的指标卡")
    @GetMapping("/likeByName")
    public ApiResponse<List<SystemUserDefinedMenuEntity>> likeByName(@RequestParam("userId") String userId , @RequestParam("name") String name) throws Throwable {
        return success(systemUserDefinedMenuService.likeByName(userId,name));
    }

    @ApiOperation(value = "重置指标卡")
    @PostMapping("/reset")
    public ApiResponse<List<SystemUserDefinedMenuEntity>> reset(@RequestBody DmUserMenuRequestVo vo) throws Throwable {
        return success(systemUserDefinedMenuService.reset(vo));
    }
}
