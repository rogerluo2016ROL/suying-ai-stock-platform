package com.ds.cockpit.screen.system.service;

import com.ds.cockpit.screen.common.core.domain.AjaxResult;
import com.ds.cockpit.screen.common.core.domain.entity.AiAgentType;
import com.ds.cockpit.screen.common.core.domain.entity.vo.AiFeedbackRequestVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.ai.GacRAGFlowAIRequestVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.ai.SessionVO;
import reactor.core.publisher.Flux;

import javax.servlet.http.HttpServletRequest;
import java.util.List;
import java.util.Map;

/**
 * @Author: ZhouHong
 * @Date: 2025-05-08 下午 02:48
 */
public interface GacAIAgentSteamService {

    /**
     * RAGFlow - 获取指定条件的 agent
     * @param aiAgentType
     */
    @Deprecated
    void getAgentsList(AiAgentType aiAgentType);

    /**
     * RAGFlow - 获取指定agent的会话（无返回）
     * @param aiAgentType
     */
    @Deprecated
    void creatSessionsByAgents(AiAgentType aiAgentType);

    /**
     * RAGFlow - 获取指定agent的会话
     * @param gacRAGFlowAIRequestVO
     * @param aiAgentType
     * @return
     */
    @Deprecated
    SessionVO creatSessionsByAgentsAndCompletions(GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO, AiAgentType aiAgentType);

    /**
     * 无拦截直接提问-非流式处理
     */
    @Deprecated
    String completionsQuestionWithAINotStream(GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO, AiAgentType aiAgentType, String sessionId);

    /**
     * 无拦截直接提问-流式处理
     */
    Flux<AjaxResult> completionsQuestionWithAIStream(GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO);

    /**
     * 用户提问-提问分析
     * @param gacRAGFlowAIRequestVO
     * @return
     */
    Flux<AjaxResult> messagesQuestionWithAIStream(GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO);


    /**
     * 用户提问-提问分析-test
     * @param gacRAGFlowAIRequestVO
     * @return
     */
    Flux<AjaxResult> messagesQuestionWithAIStreamTest(GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO);

    /**
     * 用户实际提问前的问题分词与权限校验(返回json格式)
     */
    AjaxResult splitWordsAndPermission(HttpServletRequest request, GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO);

    /**
     * 用户实际提问前的问题分词与权限校验(返回string)
     */
    AjaxResult splitWordsAndPermissionString(HttpServletRequest request, GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO);

    /**
     * 用户实际提问前的问题分词与权限校验(分词)
     */
    AjaxResult splitWordsAndPermissionChat(HttpServletRequest request, GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO);

    /**
     * 用户问题针对性反馈/意见收集
     */
    AjaxResult feedback(AiFeedbackRequestVO aiFeedbackRequestVO);

    /**
     * 用户问题针对性反馈/意见收集——枚举-问题
     */
    AjaxResult feedbackEnumQ();

    /**
     * 用户问题针对性反馈/意见收集——枚举-回答
     */
    AjaxResult feedbackEnumA();

    /**
     * AI首页top5 热门词汇
     */
    List<Map<String, Object>> keywordTop();

    /**
     * AI首页top5 热门话题 question
     */
    List<Map<String, Object>> questionTop();

    /**
     * AI提问-问题提醒 question
     */
    List<Map<String, Object>> questionKeyTop(String question);
}
