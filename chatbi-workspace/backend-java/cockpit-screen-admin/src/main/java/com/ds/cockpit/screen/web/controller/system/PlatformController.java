package com.ds.cockpit.screen.web.controller.system;

import com.ds.cockpit.screen.common.core.controller.BaseControllerNew;
import com.ds.cockpit.screen.common.core.domain.entity.vo.MenuEntity;
import com.ds.cockpit.screen.common.response.ApiResponse;
import com.ds.cockpit.screen.system.service.UserPermissionsService;
import io.swagger.annotations.ApiOperation;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/** 平台管家
 * @Author: ZhouHong
 * @Date: 2025-02-28 下午 03:57
 */
@RestController
@RequestMapping("/platform")
public class PlatformController  extends BaseControllerNew {

    @Autowired
    private UserPermissionsService userPermissionsService;

    @ApiOperation(value = "获取权限菜单")
    @GetMapping("/getPermissionList")
    public ApiResponse<List<MenuEntity>> getPermissionList(
            @RequestParam("accessToken") String accessToken,
            @RequestParam("timestamp") String timestamp,
            @RequestParam("terminalType") String terminalType
    ){
        List<MenuEntity> userMenuListBy = userPermissionsService.getUserMenuListBy(accessToken, timestamp, terminalType);
        return success(userMenuListBy);
    }
}
