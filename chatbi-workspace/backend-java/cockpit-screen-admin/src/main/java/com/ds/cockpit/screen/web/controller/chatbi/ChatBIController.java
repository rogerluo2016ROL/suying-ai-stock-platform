package com.ds.cockpit.screen.web.controller.chatbi;

import com.ds.cockpit.screen.common.core.controller.BaseController;
import com.ds.cockpit.screen.common.core.domain.AjaxResult;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ChatBIFeedbackRequest;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ChatBIRequest;
import com.ds.cockpit.screen.system.service.chatbi.ChatBIOrchestratorService;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

import javax.annotation.Resource;

@RestController
@RequestMapping("/api/v1/chatbi")
public class ChatBIController extends BaseController {
    @Resource
    private ChatBIOrchestratorService chatBIOrchestratorService;

    @PostMapping("/sessions")
    public AjaxResult createSession() {
        return success(chatBIOrchestratorService.createSession());
    }

    @GetMapping("/sessions")
    public AjaxResult sessions() {
        return success(chatBIOrchestratorService.sessions());
    }

    @GetMapping("/sessions/{sessionId}")
    public AjaxResult sessionDetail(@PathVariable("sessionId") String sessionId) {
        return chatBIOrchestratorService.sessionDetail(sessionId);
    }

    @PostMapping("/messages/prepare")
    public AjaxResult prepareMessage(@RequestBody ChatBIRequest request) {
        return chatBIOrchestratorService.prepareMessage(request);
    }

    @PostMapping(value = "/messages/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<AjaxResult> stream(@RequestBody ChatBIRequest request) {
        return chatBIOrchestratorService.stream(request);
    }

    @PostMapping("/feedback")
    public AjaxResult feedback(@RequestBody ChatBIFeedbackRequest request) {
        return chatBIOrchestratorService.feedback(request);
    }

    @GetMapping("/agents")
    public AjaxResult agents() {
        return success(chatBIOrchestratorService.agents());
    }
}
