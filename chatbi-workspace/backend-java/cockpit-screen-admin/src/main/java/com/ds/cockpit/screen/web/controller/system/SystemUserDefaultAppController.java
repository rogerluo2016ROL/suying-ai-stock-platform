package com.ds.cockpit.screen.web.controller.system;

import com.ds.cockpit.screen.common.core.controller.BaseControllerNew;
import com.ds.cockpit.screen.common.core.domain.entity.SystemUserDefaultAppEntity;
import com.ds.cockpit.screen.common.response.ApiResponse;
import com.ds.cockpit.screen.system.service.SystemUserDefaultAppService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Api(value = "系统用户默认应用管理", tags = "系统用户默认应用管理")
@RestController
@RequestMapping("/system/user/default/app")
public class SystemUserDefaultAppController extends BaseControllerNew {

    @Autowired
    private SystemUserDefaultAppService systemUserDefaultAppService;

    @ApiOperation(value = "系统用户默认应用查询")
    @PostMapping("/getDefaultApp")
    public ApiResponse<SystemUserDefaultAppEntity> getDefault(@RequestBody SystemUserDefaultAppEntity systemUserDefaultAppEntity ) {
        return success(systemUserDefaultAppService.getDefault(systemUserDefaultAppEntity));
    }

    @ApiOperation(value = "系统用户默认应用设置")
    @PostMapping("/setDefaultApp")
    public ApiResponse<Boolean> setDefaultApp(@RequestBody SystemUserDefaultAppEntity systemUserDefaultAppEntity ) {
        return success(systemUserDefaultAppService.setDefaultApp(systemUserDefaultAppEntity));
    }

}
