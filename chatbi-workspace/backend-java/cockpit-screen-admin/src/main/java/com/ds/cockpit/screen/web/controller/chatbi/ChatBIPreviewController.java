package com.ds.cockpit.screen.web.controller.chatbi;

import com.ds.cockpit.screen.common.core.controller.BaseController;
import com.ds.cockpit.screen.common.core.domain.AjaxResult;
import com.ds.cockpit.screen.system.service.chatbi.ChatBIPreviewService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.Resource;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/chatbi")
public class ChatBIPreviewController extends BaseController {
    @Resource
    private ChatBIPreviewService chatBIPreviewService;

    @PostMapping("/preview")
    public AjaxResult preview(@RequestBody Map<String, Object> request) {
        return success(chatBIPreviewService.preview(request));
    }
}
