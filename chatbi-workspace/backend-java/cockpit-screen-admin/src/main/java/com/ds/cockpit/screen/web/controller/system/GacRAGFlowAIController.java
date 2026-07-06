package com.ds.cockpit.screen.web.controller.system;

import cn.hutool.core.lang.UUID;
import com.ds.cockpit.screen.common.core.controller.BaseController;
import com.ds.cockpit.screen.common.core.domain.AjaxResult;
import com.ds.cockpit.screen.common.core.domain.entity.vo.AiFeedbackRequestVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.ai.GacRAGFlowAIRequestVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.ai.SessionVO;
import com.ds.cockpit.screen.system.service.GacAIAgentSteamService;
import com.ds.cockpit.screen.system.utils.PreconditionsUtils;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

import javax.annotation.Resource;
import javax.servlet.http.HttpServletRequest;
import java.util.List;
import java.util.Map;

/** RAGFlow AI
 * @Author: ZhouHong
 * @Date: 2025-05-12 上午 10:18
 */
@RestController
@RequestMapping("/gac/ragflow/ai")
public class GacRAGFlowAIController extends BaseController {

    @Resource
    private GacAIAgentSteamService gacAIAgentSteamService;


    /**
     * AI首页top5 热门词汇
     */
    @PostMapping("/keyword/top")
    public AjaxResult keywordTop(){
        List<Map<String, Object>> listMap = gacAIAgentSteamService.keywordTop();
        return success(listMap);
    }

    /**
     * AI首页top5 热门话题 question
     */
    @PostMapping("/question/top")
    public AjaxResult questionTop(){
        List<Map<String, Object>> listMap = gacAIAgentSteamService.questionTop();
        return success(listMap);
    }

    /**
     * AI提问-问题提醒 question
     */
    @PostMapping("/question/key")
    public AjaxResult questionKeyTop(@RequestBody GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO){
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getQuestion(), "用户提问不能为空");
        List<Map<String, Object>> listMap = gacAIAgentSteamService.questionKeyTop(gacRAGFlowAIRequestVO.getQuestion());
        return success(listMap);
    }

    /**
     * 新开启一个会话（新构建一个会话id）
     */
    @PostMapping("/created/session")
    public AjaxResult createdSessionByUser(){
        SessionVO sessionVO = new SessionVO();
        sessionVO.setId(UUID.randomUUID().toString());
        return success(sessionVO);
    }

    /**
     * 用户实际提问前的问题分词与权限校验(返回json格式)
     */
    @PostMapping(value = "/splitWordsAndPermission")
    public AjaxResult splitWordsAndPermission(HttpServletRequest request, @RequestBody GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO){
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getQuestion(), "用户提问不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getUserId(), "用户信息不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getUserName(), "用户信息不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getSessionUuid(), "会话id不能为空");
        return gacAIAgentSteamService.splitWordsAndPermission(request, gacRAGFlowAIRequestVO);
    }

    /**
     * 用户实际提问前的问题分词与权限校验(返回string)
     */
    @PostMapping(value = "/split/permission/string")
    public AjaxResult splitWordsAndPermissionString(HttpServletRequest request, @RequestBody GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO){
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getQuestion(), "用户提问不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getUserId(), "用户信息不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getUserName(), "用户信息不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getSessionUuid(), "会话id不能为空");
        return gacAIAgentSteamService.splitWordsAndPermissionString(request, gacRAGFlowAIRequestVO);
    }

    /**
     * 用户实际提问前的问题分词与权限校验(分词)
     */
    @PostMapping(value = "/split/permission/chat")
    public AjaxResult splitWordsAndPermissionChat(HttpServletRequest request, @RequestBody GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO){
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getQuestion(), "用户提问不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getUserId(), "用户信息不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getUserName(), "用户信息不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getSessionUuid(), "会话id不能为空");
        return gacAIAgentSteamService.splitWordsAndPermissionChat(request, gacRAGFlowAIRequestVO);
    }

    /**
     * 无拦截直接提问
     */
    @PostMapping(value = "/send-stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<AjaxResult> askQuestionTOAIBySession(@RequestBody GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO){
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getQuestion(), "用户提问不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getUserId(), "用户信息不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getUserName(), "用户信息不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getId(), "标识符不能为空");
        return gacAIAgentSteamService.completionsQuestionWithAIStream( gacRAGFlowAIRequestVO );
    }

    /**
     * 无拦截直接提问(使用Dify-提问)
     */
    @PostMapping(value = "/chat-messages", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<AjaxResult> askQuestionTOAI(@RequestBody GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO){
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getQuestion(), "用户提问不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getUserId(), "用户信息不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getUserName(), "用户信息不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getId(), "标识符不能为空");
        return gacAIAgentSteamService.messagesQuestionWithAIStream( gacRAGFlowAIRequestVO );
    }

    /**
     * 用户问题针对性反馈/意见收集
     */
    @PostMapping(value = "/feedback")
    public AjaxResult feedback(@RequestBody AiFeedbackRequestVO aiFeedbackRequestVO){
        PreconditionsUtils.checkNotNull(aiFeedbackRequestVO.getId(), "标识符不能为空");
        return gacAIAgentSteamService.feedback( aiFeedbackRequestVO);
    }

    /**
     * 用户问题针对性反馈/意见收集——枚举-问题
     */
    @PostMapping(value = "/feedback/enum/q")
    public AjaxResult feedbackEnumQ(){
        return gacAIAgentSteamService.feedbackEnumQ();
    }

    /**
     * 用户问题针对性反馈/意见收集——枚举-问题
     */
    @PostMapping(value = "/feedback/enum/a")
    public AjaxResult feedbackEnumA(){
        return gacAIAgentSteamService.feedbackEnumA();
    }


}
