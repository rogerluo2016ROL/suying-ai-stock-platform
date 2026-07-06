package com.ds.cockpit.screen.web.controller.chatbi;

import com.ds.cockpit.screen.common.core.controller.BaseController;
import com.ds.cockpit.screen.common.core.domain.AjaxResult;
import com.ds.cockpit.screen.system.service.chatbi.ChatBILLMGatewayService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.Resource;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/chatbi/llm")
public class ChatBILLMController extends BaseController {
    @Resource
    private ChatBILLMGatewayService chatBILLMGatewayService;

    @PostMapping("/generate")
    public AjaxResult generate(@RequestBody Map<String, Object> request) {
        return success(chatBILLMGatewayService.generate(request));
    }
}

