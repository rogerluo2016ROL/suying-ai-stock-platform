package com.ds.cockpit.screen.system.service;

import com.ds.cockpit.screen.common.core.domain.AjaxResult;
import com.ds.cockpit.screen.common.core.domain.entity.AiAgentType;
import com.ds.cockpit.screen.common.core.domain.entity.vo.AiFeedbackRequestVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.AiHistoryAnswerNodeVO;
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
public interface GacAIDifySteamService {

    /**
     * 实际提问前的数据标识
     */
    AjaxResult createdDataUuid(GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO);

    /**
     * 无拦截直接提问(使用Dify-提问)
     */
    Flux<AjaxResult> messagesQuestionWithAIStream(GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO);

    /**
     * 权限验证与提问(使用Dify-提问)
     */
    Flux<AjaxResult> messagesQuestionWithAIStreamPermission(GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO);


    /**
     * 无拦截直接提问-test
     */
    Flux<AjaxResult> messagesQuestionWithAIStreamTest(GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO);

    /**
     * 用户实际提问前的问题分词与权限校验(使用Dify-分词)
     */
    AjaxResult splitWordsAndPermissionChat(HttpServletRequest request, GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO);

    /**
     * 用户提问问题分词(使用Dify-分词)
     */
    AjaxResult splitWordsByChat(HttpServletRequest request, GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO);

    void AISplitWordsRetryAnalysis();
    
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

    /**
     * AI问题节点耗时解析
     * @return
     */
    List<AiHistoryAnswerNodeVO> getAIAnswerNode(String startTime, String endTime);

    AjaxResult aiMonitor(HttpServletRequest request, GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO);
}
