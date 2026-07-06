package com.ds.cockpit.screen.web.controller.system;

import com.ds.cockpit.screen.common.core.controller.BaseControllerNew;
import com.ds.cockpit.screen.common.core.domain.entity.SystemVersionsEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.SystemVersionsVo;
import com.ds.cockpit.screen.common.response.ApiResponse;
import com.ds.cockpit.screen.system.service.SystemVersionsService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.servlet.http.HttpServletRequest;
import java.util.List;

@Api(value = "版本管理", tags = "版本管理")
@RestController
@RequestMapping("/system/versions")
public class SystemVersionsController extends BaseControllerNew {

    @Autowired
    private SystemVersionsService systemVersionsService;

    @ApiOperation(value = "版本列表")
    @PostMapping("/getVersions")
    public ApiResponse<List<SystemVersionsEntity>> getVersions(@RequestBody SystemVersionsVo systemVersionsVo ) {
        return success(systemVersionsService.getVersions(systemVersionsVo));
    }

    @ApiOperation(value = "新增版本信息")
    @PostMapping("/add")
    public ApiResponse<Boolean> add(HttpServletRequest request, @RequestBody SystemVersionsVo systemVersionsVo ) throws Exception {
        return success(systemVersionsService.add(request, systemVersionsVo));
    }

    @ApiOperation(value = "编辑版本信息/版本发布、撤回")
    @PostMapping("/update")
    public ApiResponse<Boolean> update(HttpServletRequest request, @RequestBody SystemVersionsVo systemVersionsVo ) throws Exception {
        return success(systemVersionsService.update(request, systemVersionsVo));
    }

    @ApiOperation(value = "发布版本信息")
    @PostMapping("/released")
    public ApiResponse<Boolean> released(@RequestBody SystemVersionsVo systemVersionsVo ) {
        return success(systemVersionsService.released(systemVersionsVo));
    }

    @ApiOperation(value = "撤回版本信息")
    @PostMapping("/recall")
    public ApiResponse<Boolean> recall(@RequestBody SystemVersionsVo systemVersionsVo ) {
        return success(systemVersionsService.recall(systemVersionsVo));
    }

    @ApiOperation(value = "删除版本信息")
    @PostMapping("/delete")
    public ApiResponse<Boolean> delete(@RequestBody SystemVersionsVo systemVersionsVo ) {
        return success(systemVersionsService.delete(systemVersionsVo));
    }

}
