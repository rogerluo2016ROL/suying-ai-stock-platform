package com.ds.cockpit.screen.web.controller.system;

import com.ds.cockpit.screen.common.core.controller.BaseController;
import com.ds.cockpit.screen.common.core.domain.AjaxResult;
import com.ds.cockpit.screen.system.service.AiAgentTypeDifyService;
import io.swagger.annotations.Api;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.Resource;

/**
 * @Author: ZhouHong
 * @Date: 2025/7/30 09:19
 */
@Api(tags = "历史会话回溯")
@RestController
@RequestMapping("/ai/agent/type/dify")
public class AiAgentTypeDifyController  extends BaseController {

    @Resource
    private AiAgentTypeDifyService aiAgentTypeDifyService;

    /**
     * 获取用户AI问答模型列表
     * @return
     */
    @PostMapping("/list/q/a")
    public AjaxResult getListQAndA(){
        return aiAgentTypeDifyService.getListQAndA();
    }


    //@PostMapping("/get/q/a")
    public AjaxResult getAgentQAndA(@RequestParam("id") Long id){
        return aiAgentTypeDifyService.getAgentQAndAById(id);
    }

}
