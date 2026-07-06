package com.ds.cockpit.screen.web.controller.system;

import com.ds.cockpit.screen.common.core.controller.BaseControllerNew;
import com.ds.cockpit.screen.common.core.domain.entity.vo.SystemUserNoviceGuideVo;
import com.ds.cockpit.screen.common.response.ApiResponse;
import com.ds.cockpit.screen.system.service.SystemUserNoviceGuideService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Api(value = "系统用户新手指引信息", tags = "系统用户新手指引信息")
@RestController
@RequestMapping("/system/user/novice/guide")
public class SystemUserNoviceGuideController extends BaseControllerNew {

    @Autowired
    private SystemUserNoviceGuideService systemUserNoviceGuideService;

    @ApiOperation(value = "系统用户初次登录验证")
    @PostMapping("/loginFirst")
    public ApiResponse<Boolean> loginFirst(@RequestBody SystemUserNoviceGuideVo systemUserNoviceGuideVo ) {
        return success(systemUserNoviceGuideService.loginFirst(systemUserNoviceGuideVo));
    }

    @ApiOperation(value = "重置新手指引")
    @PostMapping("/resetLogin")
    public ApiResponse<Boolean> resetLogin(@RequestBody SystemUserNoviceGuideVo systemUserNoviceGuideVo ) {
        return success(systemUserNoviceGuideService.resetLogin(systemUserNoviceGuideVo));
    }


}
