package com.ds.cockpit.screen.web.controller.system;

import com.ds.cockpit.screen.common.core.controller.BaseControllerNew;
import com.ds.cockpit.screen.common.core.domain.entity.SystemMessageEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.SystemMessageVo;
import com.ds.cockpit.screen.common.response.ApiResponse;
import com.ds.cockpit.screen.system.service.SystemMessageService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.servlet.http.HttpServletRequest;
import java.util.List;

@Api(value = "消息中心", tags = "消息中心")
@RestController
@RequestMapping("/system/message")
public class SystemMessageController extends BaseControllerNew {

    @Autowired
    private SystemMessageService systemMessageService;

    @ApiOperation(value = "消息列表/公告（sendUrgentNotice = 1）")
    @PostMapping("/getMessages")
    public ApiResponse<List<SystemMessageEntity>> getMessages(@RequestBody SystemMessageVo systemMessageVo ) {
        return success(systemMessageService.getMessages(systemMessageVo));
    }

    @ApiOperation(value = "发布公告")
    @PostMapping("/push")
    public ApiResponse<Boolean> pushNotice(@RequestBody SystemMessageVo systemMessageVo ) {
        return success(systemMessageService.pushNotice(systemMessageVo));
    }

    @ApiOperation(value = "关闭紧急公告/撤回")
    @PostMapping("/closeNotice")
    public ApiResponse<Boolean> closeNotice(@RequestBody SystemMessageVo systemMessageVo ) {
        return success(systemMessageService.closeNotice(systemMessageVo));
    }

    // 保存 & 发布
    @ApiOperation(value = "新增/编辑消息/公告")
    @PostMapping("/addAndEdit")
    public ApiResponse<Boolean> addAndEdit(HttpServletRequest request, @RequestBody SystemMessageVo systemMessageVo ) throws Exception {
        return success(systemMessageService.addAndEdit(request, systemMessageVo));
    }

    @ApiOperation(value = "删除消息列表/公告")
    @PostMapping("/delete")
    public ApiResponse<Boolean> delete(@RequestBody SystemMessageVo systemMessageVo ) {
        return success(systemMessageService.delete(systemMessageVo));
    }

}
