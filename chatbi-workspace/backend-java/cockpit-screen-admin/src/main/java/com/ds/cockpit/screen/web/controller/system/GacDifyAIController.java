package com.ds.cockpit.screen.web.controller.system;

import cn.hutool.core.lang.UUID;
import com.ds.cockpit.screen.common.core.controller.BaseController;
import com.ds.cockpit.screen.common.core.domain.AjaxResult;
import com.ds.cockpit.screen.common.core.domain.entity.vo.AiFeedbackRequestVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.AiHistoryAnswerNodeVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.ai.GacRAGFlowAIRequestVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ChatBIFeedbackRequest;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ChatBIRequest;
import com.ds.cockpit.screen.common.utils.poi.ExcelExportUtils;
import com.ds.cockpit.screen.common.utils.poi.ExcelUtil;
import com.ds.cockpit.screen.system.service.GacAIDifySteamService;
import com.ds.cockpit.screen.system.service.chatbi.ChatBIOrchestratorService;
import com.ds.cockpit.screen.system.utils.PreconditionsUtils;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

import javax.annotation.Resource;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** Dify AI
 * @Author: ZhouHong
 * @Date: 2025-05-12 上午 10:18
 */
@RestController
@RequestMapping("/gac/dify/ai")
public class GacDifyAIController extends BaseController {

    @Resource
    private GacAIDifySteamService gacAIDifySteamService;

    @Resource
    private ChatBIOrchestratorService chatBIOrchestratorService;


    /**
     * AI首页top5 热门词汇
     */
    @PostMapping("/keyword/top")
    public AjaxResult keywordTop(){
        List<Map<String, Object>> listMap = gacAIDifySteamService.keywordTop();
        return success(listMap);
    }

    /**
     * AI首页top5 热门话题 question
     */
    @PostMapping("/question/top")
    public AjaxResult questionTop(){
        List<Map<String, Object>> listMap = gacAIDifySteamService.questionTop();
        return success(listMap);
    }

    /**
     * AI提问-问题提醒 question
     */
    @PostMapping("/question/key")
    public AjaxResult questionKeyTop(@RequestBody GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO){
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getQuestion(), "用户提问不能为空");
        List<Map<String, Object>> listMap = gacAIDifySteamService.questionKeyTop(gacRAGFlowAIRequestVO.getQuestion());
        return success(listMap);
    }

    /**
     * 新开启一个会话（新构建一个会话id）
     */
    @PostMapping("/created/session")
    public AjaxResult createdSessionByUser(){
        return success(chatBIOrchestratorService.createSession());
    }

    /**
     * 新开启一个问题（新构建一个问题的唯一标识）
     */
    @PostMapping("/created/data/uuid")
    public AjaxResult createdDataUuid(@RequestBody GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO){
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getQuestion(), "用户提问不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getUserId(), "用户信息不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getUserName(), "用户信息不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getSessionUuid(), "会话id不能为空");
        return chatBIOrchestratorService.prepareMessage(toChatBIRequest(gacRAGFlowAIRequestVO));
    }

    /**
     * 用户实际提问前的问题【分词与权限校验】(使用Dify-分词)
     */
    @PostMapping(value = "/split/permission/chat")
    public AjaxResult splitWordsAndPermissionChat(HttpServletRequest request, @RequestBody GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO){
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getQuestion(), "用户提问不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getUserId(), "用户信息不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getUserName(), "用户信息不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getSessionUuid(), "会话id不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getId(), "唯一标识不能为空");
        return gacAIDifySteamService.splitWordsAndPermissionChat(request, gacRAGFlowAIRequestVO);
    }

    /**
     * 问题分词(使用Dify-分词)【无权限验证】
     */
    @PostMapping(value = "/split/words/chat")
    public AjaxResult splitWordsByChat(HttpServletRequest request, @RequestBody GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO){
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getQuestion(), "用户提问不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getUserId(), "用户信息不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getUserName(), "用户信息不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getSessionUuid(), "会话id不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getId(), "唯一标识不能为空");
        return gacAIDifySteamService.splitWordsByChat(request, gacRAGFlowAIRequestVO);
    }

    /**
     * 权限验证与提问(使用Dify-提问)
     */
    @PostMapping(value = "/permission/chat-messages", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<AjaxResult> permissionAskQuestionTOAI(@RequestBody GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO){
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getQuestion(), "用户提问不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getUserId(), "用户信息不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getUserName(), "用户信息不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getId(), "标识符不能为空");
        return gacAIDifySteamService.messagesQuestionWithAIStreamPermission( gacRAGFlowAIRequestVO );
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
        return chatBIOrchestratorService.stream(toChatBIRequest(gacRAGFlowAIRequestVO));
    }

    /**
     * 无拦截直接提问-test
     */
    //@PostMapping(value = "/chat-messages/test", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<AjaxResult> askQuestionTOAITest(@RequestBody GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO){
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getQuestion(), "用户提问不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getUserId(), "用户信息不能为空");
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getUserName(), "用户信息不能为空");
        return gacAIDifySteamService.messagesQuestionWithAIStreamTest( gacRAGFlowAIRequestVO );
    }

    @GetMapping(value = "/export/getAIAnswerNode/{start}/{end}")
    public void getAIAnswerNode(HttpServletResponse response, @PathVariable("start") String startTime,
                                @PathVariable("end") String endTime, boolean include) throws Exception {
        PreconditionsUtils.checkNotNull(startTime, "数据开始时间不能为空（yyyy-MM-dd）");
        PreconditionsUtils.checkNotNull(endTime, "数据结束时间不能为空（yyyy-MM-dd）");
        List<AiHistoryAnswerNodeVO> data = new ArrayList();
        data = gacAIDifySteamService.getAIAnswerNode(startTime, endTime);
        //返回文件
        if(include){
            response.setCharacterEncoding("UTF-8");
            try {
                // 2. 处理大字段
                data.forEach(e -> {
                    e.setAnswer(ExcelExportUtils.safeField(e.getAnswer()));
                });
                // 3. 执行导出
                ExcelExportUtils.exportAllData(response, "全量数据导出", data);
            } catch (IOException e) {
                throw new RuntimeException("导出失败：" + e.getMessage());
            }
        }else{
            for (AiHistoryAnswerNodeVO datum : data) {
                datum.setAnswer(null);
            }
            ExcelUtil<AiHistoryAnswerNodeVO> util = new ExcelUtil<AiHistoryAnswerNodeVO>(AiHistoryAnswerNodeVO.class);
            util.exportExcel(response, data,"AI问题节点耗时分析" );
        }

    }

    /**
     * 用户问题针对性反馈/意见收集
     */
    @PostMapping(value = "/feedback")
    public AjaxResult feedback(@RequestBody AiFeedbackRequestVO aiFeedbackRequestVO){
        PreconditionsUtils.checkNotNull(aiFeedbackRequestVO.getId(), "标识符不能为空");
        ChatBIFeedbackRequest request = new ChatBIFeedbackRequest();
        request.setId(aiFeedbackRequestVO.getId());
        request.setMessageId(String.valueOf(aiFeedbackRequestVO.getId()));
        request.setRating("legacy");
        return chatBIOrchestratorService.feedback(request);
    }

    /**
     * 用户问题针对性反馈/意见收集——枚举-问题
     */
    @PostMapping(value = "/feedback/enum/q")
    public AjaxResult feedbackEnumQ(){
        return gacAIDifySteamService.feedbackEnumQ();
    }

    /**
     * 用户问题针对性反馈/意见收集——枚举-回答
     */
    @PostMapping(value = "/feedback/enum/a")
    public AjaxResult feedbackEnumA(){
        return gacAIDifySteamService.feedbackEnumA();
    }

    /**
     * AI监控用非流式请求，验证流程可用性及数据非空
     */
    @PostMapping(value = "/monitor")
    public AjaxResult aiMonitor(HttpServletRequest request, @RequestBody GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO){
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getQuestion(), "用户提问不能为空");
        gacRAGFlowAIRequestVO.setUserId("AI-QYWX-MONITOR");
        gacRAGFlowAIRequestVO.setUserName("Ai服务监控");
        gacRAGFlowAIRequestVO.setSessionUuid(UUID.randomUUID().toString());
        return gacAIDifySteamService.aiMonitor(request, gacRAGFlowAIRequestVO);
    }

    private ChatBIRequest toChatBIRequest(GacRAGFlowAIRequestVO source) {
        ChatBIRequest request = new ChatBIRequest();
        request.setId(source.getId());
        request.setQuestion(source.getQuestion());
        request.setUserId(source.getUserId());
        request.setUserName(source.getUserName());
        request.setSessionUuid(source.getSessionUuid());
        request.setSessionId(source.getSessionUuid());
        request.setAgentId(source.getAgentId());
        return request;
    }

}
