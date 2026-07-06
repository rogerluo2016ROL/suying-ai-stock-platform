package com.ds.cockpit.screen.system.service.impl;

import cn.hutool.core.bean.BeanUtil;
import cn.hutool.http.Header;
import cn.hutool.http.HttpRequest;
import cn.hutool.http.HttpResponse;
import cn.hutool.http.HttpUtil;
import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONArray;
import com.alibaba.fastjson2.JSONObject;
import com.baomidou.mybatisplus.core.toolkit.CollectionUtils;
import com.ds.cockpit.screen.common.core.domain.AjaxResult;
import com.ds.cockpit.screen.common.core.domain.entity.AiAgentType;
import com.ds.cockpit.screen.common.core.domain.entity.AiHistoryEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.AiFeedbackRequestVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.ai.Agents;
import com.ds.cockpit.screen.common.core.domain.entity.vo.ai.AgentsSessions;
import com.ds.cockpit.screen.common.core.domain.entity.vo.ai.GacRAGFlowAIRequestVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.ai.SessionVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.ai.Sessions;
import com.ds.cockpit.screen.common.core.domain.entity.vo.dataperm.ColumnValue;
import com.ds.cockpit.screen.common.core.domain.entity.vo.dataperm.DataSourcePerms;
import com.ds.cockpit.screen.common.core.domain.entity.vo.dataperm.DataTablePerm;
import com.ds.cockpit.screen.common.core.domain.entity.vo.dataperm.RowPerm;
import com.ds.cockpit.screen.common.utils.StringUtils;
import com.ds.cockpit.screen.system.mapper.AiAgentTypeMapper;
import com.ds.cockpit.screen.system.mapper.AiFeedbackEnumMapper;
import com.ds.cockpit.screen.system.mapper.AiHistoryMapper;
import com.ds.cockpit.screen.system.service.GacAIAgentSteamService;
import com.ds.cockpit.screen.system.utils.HttpClientConfigNew;
import com.ds.cockpit.screen.system.utils.PreconditionsUtils;
import com.ds.cockpit.screen.system.utils.Subsidiary;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

import javax.annotation.Resource;
import javax.servlet.http.HttpServletRequest;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

/**
 * @Author: ZhouHong
 * @Date: 2025-05-08 下午 02:59
 */
@Slf4j
@Service
public class GacAIAgentSteamServiceImpl implements GacAIAgentSteamService {

    @Value("${ai.agents.list:/api/v1/agents}")
    private String url_agents;

    @Value("${ai.agents.list_select:/api/v1/agents?title=%s}")
    private String url_agents_select;

    @Value("${ai.agents.sessions:/api/v1/agents/%s/sessions}")
    private String url_sessions;

    @Value("${ai.agents.completions:/api/v1/agents/%s/completions}")
    private String url_completions;

    @Value("${ac.url:}")
    private String url;

    @Value("${ac.dataPerm:null}")
    private String dataPermURL;

    @Value("${ac.sourceId:0}")
    private Long sourceId;

    @Resource
    private AiHistoryMapper aiHistoryMapper;

    @Resource
    private AiAgentTypeMapper aiAgentTypeMapper;

    @Resource
    private AiFeedbackEnumMapper aiFeedbackEnumMapper;

    private Map<String,String> agentsMap = new HashMap<>();

    @Override
    public AjaxResult feedback(AiFeedbackRequestVO aiFeedbackRequestVO) {
        AiHistoryEntity aiHistoryEntity = aiHistoryMapper.selectById(aiFeedbackRequestVO.getId());
        if(aiHistoryEntity == null){
            return AjaxResult.error("标识符有误或不存在！");
        }
        aiHistoryEntity.setQuestionFeedback(aiFeedbackRequestVO.getQuestionFeedback());
        aiHistoryEntity.setAnswerFeedback(aiFeedbackRequestVO.getAnswerFeedback());
        aiHistoryEntity.setOpinionFeedback(aiFeedbackRequestVO.getOpinionFeedback());
        aiHistoryEntity.setUpdateTime(LocalDateTime.now());
        int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
        if(insert > 0){
            return AjaxResult.success();
        }else{
            log.error("Error-会话数据保存失败: " + aiHistoryEntity.toString());
            return AjaxResult.error("服务异常，请核查！");
        }
    }

    @Override
    public AjaxResult feedbackEnumQ() {
        List<String> listQ= aiFeedbackEnumMapper.getFeedbackEnumQ();
        if(CollectionUtils.isNotEmpty(listQ)){
            return AjaxResult.success(listQ);
        }else{
            return AjaxResult.error();
        }
    }

    @Override
    public AjaxResult feedbackEnumA() {
        List<String> listA= aiFeedbackEnumMapper.getFeedbackEnumA();
        if(CollectionUtils.isNotEmpty(listA)){
            return AjaxResult.success(listA);
        }else{
            return AjaxResult.error();
        }
    }

    @Override
    public List<Map<String, Object>> keywordTop() {
        return aiHistoryMapper.getKeyWordTOP();
    }

    @Override
    public List<Map<String, Object>> questionTop() {
        return aiHistoryMapper.getQuestionTop();
    }

    @Override
    public List<Map<String, Object>> questionKeyTop(String question) {
        return aiHistoryMapper.getQuestionKeyTop(question);
    }

    @Override
    @Deprecated
    public void getAgentsList(AiAgentType aiAgentType) {
        String authorization = "Bearer " + aiAgentType.getAgentKey();
        //step1： agents 查询列表
        String body = HttpRequest.get(aiAgentType.getPathValue() + url_agents)
                .header(Header.AUTHORIZATION, authorization)
                .header(Header.CONTENT_TYPE,"application/json")
                .execute().body();
        JSONObject parse = JSONObject.parseObject(body);
        int code = (int)parse.get("code");
        String[] agents_ids = new String[0];
        List<String> agentsList = new ArrayList<>();
        if(code == 0){
            JSONArray dataList = parse.getJSONArray("data");
            // System.out.println(dataList);
            if (dataList != null){
                List<Agents> datasetsList = JSON.parseArray(dataList.toJSONString(), Agents.class);
                for (Agents agents : datasetsList) {
                    System.out.println(agents.toString());
                    System.out.println(agents.getId());
                    agentsList.add(agents.getId());
                }
                agents_ids = agentsList.toArray(agents_ids);
            }else{
                System.out.println("UserMenu-msg: " +parse.getJSONObject("message"));
            }
        }
        System.out.println(agents_ids.length);

        String agent_id = agentsList.get(0);

    }

    protected Agents getAgentsByTitle(AiAgentType aiAgentType) {

        //step1： agents 查询列表
        String url_format = aiAgentType.getPathValue() + url_agents_select;
        String url_agents_select = String.format(url_format, aiAgentType.getTitle());
        String authorization = "Bearer " + aiAgentType.getAgentKey();
        String body = HttpRequest.get(url_agents_select)
                .header(Header.AUTHORIZATION, authorization)
                .header(Header.CONTENT_TYPE,"application/json")
                .execute().body();
        JSONObject parse = JSONObject.parseObject(body);
        int code = (int)parse.get("code");
        if(code == 0){
            JSONArray dataList = parse.getJSONArray("data");
            // log.info(dataList);
            if (dataList != null){
                List<Agents> agentsList = JSON.parseArray(dataList.toJSONString(), Agents.class);
                if(CollectionUtils.isNotEmpty(agentsList)){
                    for (Agents agents : agentsList) {
                        agentsMap.put(agents.getId(), agents.getTitle());
                    }
                    Agents agents = agentsList.get(0);
                    return agents;
                }
            }else{
                log.info("url_agents_select-error-msg: " +parse.getJSONObject("message"));
            }
        }
        return null;

    }


    @Override
    @Deprecated
    public void creatSessionsByAgents(AiAgentType aiAgentType) {

        String sessionsId = null;
        //可增加路径参数，查询指定代理
        String url_format = aiAgentType.getPathValue() + url_sessions;
        String url_sessions = String.format(url_format, aiAgentType.getAgentId());
        String authorization = "Bearer " + aiAgentType.getAgentKey();
        String body = HttpRequest.post(url_sessions)
                .header(Header.AUTHORIZATION, authorization)
                .header(Header.CONTENT_TYPE,"application/json")
                .execute().body();
        JSONObject parse = JSONObject.parseObject(body);
        int code = (int)parse.get("code");
        if(code == 0){
            JSONObject data = parse.getJSONObject("data");
            AgentsSessions agentsSessions = JSONObject.parseObject(data.toJSONString(), AgentsSessions.class);
            // System.out.println(data);
            // System.out.println(agentsSessions.getId());
            System.out.println(agentsSessions.getMessage()[0].getContent());
            sessionsId = agentsSessions.getId();
        }

    }


    @Override
    @Deprecated
    public SessionVO creatSessionsByAgentsAndCompletions(GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO, AiAgentType aiAgentType) {
        PreconditionsUtils.checkNotNull(aiAgentType.getTitle(), "Agents未指定");
        PreconditionsUtils.checkNotNull(aiAgentType.getAgentId(), "Agents未指定");
        // step 1: 先获取指定的agent的agentId
        /*Agents agents = getAgentsByTitle(gacRAGFlowAIRequestVO.getTitle());
        if(agents == null){
            throw new RuntimeException("会话代理获取失败！");
        }*/
        String agentsId = aiAgentType.getAgentId();
        // step 2: 获取用户指定的id
        String url_format = aiAgentType.getPathValue() + url_completions;
        String url_completions = String.format(url_format, agentsId);
        PreconditionsUtils.checkNotNull(gacRAGFlowAIRequestVO.getUserId(), "用户信息必填");
        Map<String, Object> bodyParam = new HashMap<>();
        // bodyParam.put("question", "");
        bodyParam.put("stream", false);
        bodyParam.put("user_id", gacRAGFlowAIRequestVO.getUserId());

        String authorization = "Bearer " + aiAgentType.getAgentKey();
        String body = HttpRequest.post(url_completions)
                .header(Header.AUTHORIZATION, authorization)
                .header(Header.CONTENT_TYPE,"application/json")
                .body(JSON.toJSONString(bodyParam))
                .execute().body();
        JSONObject parse = JSONObject.parseObject(body);
        int code = (int)parse.get("code");
        if(code == 0){
            JSONObject data = parse.getJSONObject("data");
            Sessions sessions = JSONObject.parseObject(data.toJSONString(), Sessions.class);
            log.info("creatSessionsByAgentsAndCompletions-{}", data.toString());
            log.info("creatSessionsByAgentsAndCompletions-session_id-{}",sessions.getSession_id());
            if(sessions != null){
                SessionVO sessionVO = new SessionVO();
                BeanUtil.copyProperties(sessions, sessionVO);
                sessionVO.setSessionId(sessions.getSession_id());
                sessionVO.setAgentId(agentsId);
                return sessionVO;
            }
        }
        return null;
    }

    @Override
    @Deprecated
    public String completionsQuestionWithAINotStream(GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO, AiAgentType aiAgentType, String sessionId) {
        System.out.println("开始分词处理");
        String url_format = aiAgentType.getPathValue() + url_completions;
        String url_completions = String.format(url_format, aiAgentType.getAgentId());

        Map<String, Object> bodyParam = new HashMap<>();
        bodyParam.put("question", gacRAGFlowAIRequestVO.getQuestion());
        bodyParam.put("stream", false);
        bodyParam.put("session_id", sessionId);
        bodyParam.put("user_id", gacRAGFlowAIRequestVO.getUserId());

        String authorization = "Bearer " + aiAgentType.getAgentKey();
        String body = HttpRequest.post(url_completions)
                .header(Header.AUTHORIZATION, authorization)
                .header(Header.CONTENT_TYPE,"application/json")
                .body(JSON.toJSONString(bodyParam))
                .setConnectionTimeout(90000)
                .setReadTimeout(90000)
                .execute().body();
        JSONObject parse = JSONObject.parseObject(body);
        System.out.println("分词返回- " + parse.toString());
        Object code = parse.get("code");
        if(code.equals(0)){
            JSONObject data = parse.getJSONObject("data");
            Sessions sessions = JSONObject.parseObject(data.toJSONString(), Sessions.class);
            System.out.println(data);
            System.out.println(sessions.getId());
            return sessions.getAnswer();
        }else{
            return null;
        }
    }

    // 获取问题分词
    public String getQuestionSplitWords(GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO, AiHistoryEntity aiHistoryEntity) {
        System.out.println("开始分词处理");
        List<AiAgentType> agentTypeQA = aiAgentTypeMapper.getAgentTypeQA();
        AiAgentType aiAgentType = agentTypeQA.get(0);
        String url_messages = aiAgentType.getPathValue();

        Map<String, Object> bodyParam = new HashMap<>();
        bodyParam.put("inputs", new HashMap<>());
        bodyParam.put("query", gacRAGFlowAIRequestVO.getQuestion());
        bodyParam.put("response_mode", "streaming");
        bodyParam.put("conversation_id", aiHistoryEntity.getFenciSessionId());
        bodyParam.put("user", gacRAGFlowAIRequestVO.getUserId());

        String authorization = "Bearer " + aiAgentType.getAgentKey();

        HttpResponse execute = HttpRequest.post(url_messages)
                .header(Header.AUTHORIZATION, authorization)
                .header(Header.CONTENT_TYPE, "application/json")
                .body(JSON.toJSONString(bodyParam))
                .execute();
        int status = execute.getStatus();
        String body = execute.body();
        System.out.println("分词返回- " + body);
        if(200 == status){
            JSONObject parse = JSONObject.parseObject(body);
            String answer = (String)parse.get("answer");
            System.out.println(answer);
            return answer;
        }else{
            return null;
        }
    }


    //获取用户数据权限(行权限)
    protected List<DataSourcePerms> getUserDataPerm(String accessToken, String timestamp, Long sourceId){
        System.out.println("开始请求用户行权限");
        PreconditionsUtils.checkNotNull(accessToken, "认证信息不能为空");
        PreconditionsUtils.checkNotNull(timestamp, "认证信息不能为空");
        PreconditionsUtils.checkNotNull(sourceId, "请确认数据源信息");
        log.info("token:{}",accessToken );
        Map<String, Object> param = new HashMap<>();
        param.put("accessToken", accessToken);
        param.put("timestamp", timestamp);
        param.put("sourceId", sourceId);
        log.info("UserMenuListURL:{}", url+ dataPermURL );
        String body = HttpUtil.createGet(url+ dataPermURL).form(param).execute().body();
        JSONObject parse = JSONObject.parseObject(body);
        Object code = parse.get("code");
        JSONObject data = parse.getJSONObject("data");
        log.info("data:{}",data);
        List<DataSourcePerms> dataSourcePermsList = new ArrayList<>();
        if (code.equals(200) && data != null){
            JSONArray dataSourcePerms = data.getJSONArray("dataSourcePerms");
            dataSourcePermsList = JSON.parseArray(dataSourcePerms.toJSONString(), DataSourcePerms.class);
        }else{
            log.error("UserMenu-msg:{}",parse.getJSONObject("msg"));
        }
        System.out.println("返回用户行权限");
        return dataSourcePermsList;
    }



    @Override
    public Flux<AjaxResult> completionsQuestionWithAIStream(GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO) {
        Long agId = null;
        try {
            AiHistoryEntity aiHistoryEntity = aiHistoryMapper.selectById(gacRAGFlowAIRequestVO.getId());
            // step1 ：先得获取分词可用的agent并开启会话-实际分词
            List<AiAgentType> agentTypeQA = null;
            int retryCount = 0;
            boolean success = false;
            while (retryCount < 10 && !success) {
                agentTypeQA = aiAgentTypeMapper.getAgentTypeQA();
                if (agentTypeQA != null && !agentTypeQA.isEmpty()) {
                    success = true;
                    break;  // 直接退出循环
                }
                TimeUnit.SECONDS.sleep(3);
                retryCount++;
            }
            if(success && CollectionUtils.isNotEmpty(agentTypeQA)){
                Random random = new Random();
                int randomIndex = random.nextInt(agentTypeQA.size());
                // 1、可用的Agent
                AiAgentType aiAgentType = agentTypeQA.get(randomIndex);
                // 占用
                aiAgentTypeMapper.updateAgentUnused(aiAgentType.getId());
                System.out.println("占用提问agent=" + aiAgentType.getTitle());
                aiHistoryEntity.setAgentId(aiAgentType.getAgentId());
                aiHistoryEntity.setAgentName(aiAgentType.getTitle());
                agId = aiAgentType.getId();
                // 2、获取sessionId
                System.out.println("获取提问会话");
                long starthh = System.currentTimeMillis();
                SessionVO sessionVO = this.creatSessionsByAgentsAndCompletions(gacRAGFlowAIRequestVO, aiAgentType);
                long endhh = (System.currentTimeMillis() - starthh);
                System.out.println("提问会话耗时-"+ endhh + "ms");
                if(sessionVO == null){
                    aiHistoryEntity.setDescriptions("AI提问错误-获取会话失败！");
                    int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                    return null;
                }
                // 3、对问题进行实际提问
                String sessionId = sessionVO.getSessionId();
                aiHistoryEntity.setConversationId(sessionId);
                System.out.println("获取提问结果");

                long start = System.currentTimeMillis();
                // step3 : 实际提问
                String url_format = aiAgentType.getPathValue() + url_completions;
                String url_completions = String.format(url_format, aiAgentType.getAgentId());

                Map<String, Object> bodyParam = new HashMap<>();
                bodyParam.put("question", gacRAGFlowAIRequestVO.getQuestion());
                bodyParam.put("stream", true);
                bodyParam.put("session_id", sessionId);
                bodyParam.put("user_id", gacRAGFlowAIRequestVO.getUserId());

                String authorization = "Bearer " + aiAgentType.getAgentKey();
                // 发送流式 POST 请求
                Flux<String> responseStream = HttpClientConfigNew.createWebClient().post()
                        .uri(url_completions)
                        .contentType(MediaType.APPLICATION_JSON)
                        .header(Header.AUTHORIZATION.getValue(), authorization)
                        .accept(MediaType.TEXT_EVENT_STREAM)  // 声明接收 SSE 流式数据:ml-citation{ref="1,7" data="citationList"}
                        .bodyValue(JSON.toJSONString(bodyParam))
                        .retrieve()
                        .bodyToFlux(String.class);
                List<String> items = new ArrayList<>();
                List<String> datasList = new ArrayList<>();
                StringBuffer sb = new StringBuffer();
                Long finalAgId = agId;
                return responseStream.map(chunk -> {
                    System.out.println(items.size());
                    //System.out.println(chunk);
                    JSONObject jsonChunk = JSONObject.parseObject(chunk);
                    Object code = jsonChunk.get("code");
                    if(!code.equals(0)){
                        Object message = jsonChunk.get("message");
                        log.error("Error: " + message);
                        System.out.println("流式提问请求出错-"+ message);
                        // return Flux.just(AjaxResult.error("AI提问错误-"+message.toString()));
                        return AjaxResult.error(message.toString());
                    }
                    Object data = jsonChunk.get("data");
                    Long seconds = null;
                    if(data instanceof JSONObject){
                        String datas = data.toString();
                        datasList.add(datas);
                        Sessions sessions = JSONObject.parseObject(datas, Sessions.class);
                        String newAnswer = sessions.getAnswer().replaceAll("[ ]+", "").replaceAll("(?<=\n)[ ]+", "");
                        sessions.setAnswer(newAnswer);
                        items.add(sessions.getAnswer());
                        if(items.size() > 1){
                            String appendStr = sessions.getAnswer().replace(items.get(items.size() - 2), "");
                            sb.append(appendStr);
                            //System.out.println(appendStr);
                            return AjaxResult.success(appendStr);
                        }else{
                            sb.append(sessions.getAnswer());
                            return AjaxResult.success(sessions.getAnswer());
                        }
                    }
                    if(data.equals(true)){
                        seconds = (System.currentTimeMillis() - start) / 1000;
                        // System.out.println("1234567890===1234567890");
                        System.out.println(sb.toString());
                        String answer = "";
                        if(items != null && items.size() >0){
                            answer = items.get(items.size() - 1);
                        }
                        String datasLast = datasList.get(datasList.size() - 1);
                        System.out.println(answer);
                        //将数据保存改为数据更新
                        String newa = answer.replaceAll("[ ]+", "").replaceAll("(?<=\n)[ ]+", "");
                        aiHistoryEntity.setAnswer(newa);
                        aiHistoryEntity.setAnswerAll(datasLast);
                        if(seconds != null){
                            aiHistoryEntity.setAnswerTime(seconds + "s");
                        }
                        aiHistoryEntity.setUpdateTime(LocalDateTime.now());
                        int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                        if(null != finalAgId){
                            aiAgentTypeMapper.updateAgentUsed(finalAgId);
                            System.out.println("解除占用提问agent=" + aiAgentType.getTitle());
                        }
                        if(insert > 0){
                            return AjaxResult.success("");
                        }else{
                            log.error("Error-会话数据保存失败: " + aiHistoryEntity.toString());
                        }
                    }
                    return AjaxResult.success("");
                })
                        .doOnError(e -> System.err.println("Error: " + e.getMessage()))
                        .onErrorReturn(AjaxResult.error("系统服务繁忙，请重新提问"));
            }else{
                aiHistoryEntity.setDescriptions("AI提问错误-服务繁忙！");
                int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                return Flux.just(AjaxResult.error("AI提问错误-服务繁忙！"));
            }
        }catch (Exception e){
            if(null != agId){
                aiAgentTypeMapper.updateAgentUsed(agId);
            }
            return Flux.just(AjaxResult.error("AI提问错误-系统错误！"));
        }finally {
            if(null != agId){
                aiAgentTypeMapper.updateAgentUsed(agId);
            }
        }
    }

    @Override
    public Flux<AjaxResult> messagesQuestionWithAIStream(GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO) {
        AiHistoryEntity aiHistoryEntity = aiHistoryMapper.selectById(gacRAGFlowAIRequestVO.getId());
        try {
            // step1 ：先得获取分词可用的agent并开启会话-实际分词
            String permission = aiHistoryEntity.getPermission();

            if(permission.equals("1")){
                AiHistoryEntity entity = new AiHistoryEntity();
                entity.setSessionUuid(aiHistoryEntity.getSessionUuid());
                List<AiHistoryEntity> aiHistoryList = aiHistoryMapper.getAiHistoryList(entity);
                if(CollectionUtils.isNotEmpty(aiHistoryList)){
                    List<AiHistoryEntity> collect = aiHistoryList.stream()
                            .filter(e -> StringUtils.isNotEmpty(e.getConversationId()))
                            .collect(Collectors.toList());
                    if(CollectionUtils.isNotEmpty(collect)){
                        String conversationId = aiHistoryList.get(0).getConversationId();
                        aiHistoryEntity.setConversationId(conversationId);
                    }
                }
                // 对问题进行实际提问
                System.out.println("获取提问结果");

                long start = System.currentTimeMillis();
                // step3 : 实际提问
                List<AiAgentType> agentTypeQA = aiAgentTypeMapper.getAgentTypeQA();
                AiAgentType aiAgentType = agentTypeQA.get(0);
                String url_completions = aiAgentType.getPathValue();

                Map<String, Object> bodyParam = new HashMap<>();
                bodyParam.put("inputs", new HashMap<>());
                bodyParam.put("query", gacRAGFlowAIRequestVO.getQuestion());
                bodyParam.put("response_mode", "streaming");
                bodyParam.put("conversation_id", aiHistoryEntity.getConversationId());
                bodyParam.put("user", gacRAGFlowAIRequestVO.getUserId());

                String authorization = "Bearer " + aiAgentType.getAgentKey();
                // 发送流式 POST 请求
                Flux<String> responseStream = HttpClientConfigNew.createWebClient().post()
                        .uri(url_completions)
                        .contentType(MediaType.APPLICATION_JSON)
                        .header(Header.AUTHORIZATION.getValue(), authorization)
                        .accept(MediaType.TEXT_EVENT_STREAM)
                        .bodyValue(JSON.toJSONString(bodyParam))
                        .retrieve()
                        .bodyToFlux(String.class);
                List<String> items = new ArrayList<>();
                List<String> datasList = new ArrayList<>();
                // StringBuffer sb = new StringBuffer();
                return responseStream.map(chunk -> {
                    System.out.println(items.size());
                    System.out.println(chunk);
                    datasList.add(chunk);
                    JSONObject jsonChunk = JSONObject.parseObject(chunk);
                    String answer = (String)jsonChunk.getOrDefault("answer", "");
                    String conversationId = (String)jsonChunk.getOrDefault("conversation_id", "");
                    aiHistoryEntity.setConversationId(conversationId);
                    items.add(answer);
                    System.out.println(answer);
                    return AjaxResult.success(answer);
                })
                        .doOnTerminate(() ->{
                            aiHistoryEntity.setAnswer(String.join("",items));
                            aiHistoryEntity.setAnswerAll(String.join("\\n",datasList));
                            Long seconds = (System.currentTimeMillis() - start) / 1000;
                            aiHistoryEntity.setAnswerTime(seconds + "s");
                            aiHistoryEntity.setUpdateTime(LocalDateTime.now());
                            int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                        })
                        .doOnError(e -> {
                            aiHistoryEntity.setDescriptions("AI提问错误-"+e.getMessage());
                            int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                            System.err.println("Error: " + e.getMessage());
                            AjaxResult.error("Error: " + e.getMessage());
                        })
                        .onErrorReturn(AjaxResult.error("系统服务繁忙，请重新提问"));
            }else{
                aiHistoryEntity.setDescriptions("AI提问错误-未通过权限校验！");
                int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                return Flux.just(AjaxResult.error("AI提问错误-未通过权限校验！"));
            }
        }catch (Exception e){
            aiHistoryEntity.setDescriptions("AI提问错误-"+e.getMessage());
            int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
            return Flux.just(AjaxResult.error("AI提问错误-系统错误！"));
        }
    }



    @Override
    public Flux<AjaxResult> messagesQuestionWithAIStreamTest(GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO) {
        AiHistoryEntity aiHistoryEntity = new AiHistoryEntity();
        aiHistoryEntity.setPermission("1");
        try {
            // step1 ：权限验证-并开启分词
            String permission = aiHistoryEntity.getPermission();

            if(permission.equals("1")){
                // 对问题进行实际提问
                System.out.println("获取提问结果");

                long start = System.currentTimeMillis();
                // step3 : 实际提问
                List<AiAgentType> agentTypeQA = aiAgentTypeMapper.getAgentTypeQA();
                AiAgentType aiAgentType = agentTypeQA.get(0);
                String url_completions = aiAgentType.getPathValue();

                Map<String, Object> bodyParam = new HashMap<>();
                bodyParam.put("inputs", new HashMap<>());
                bodyParam.put("query", gacRAGFlowAIRequestVO.getQuestion());
                bodyParam.put("response_mode", "streaming");
                bodyParam.put("conversation_id", aiHistoryEntity.getConversationId());
                bodyParam.put("user", gacRAGFlowAIRequestVO.getUserId());

                String authorization = "Bearer " + aiAgentType.getAgentKey();
                // 发送流式 POST 请求
                Flux<String> responseStream = HttpClientConfigNew.createWebClient().post()
                        .uri(url_completions)
                        .contentType(MediaType.APPLICATION_JSON)
                        .header(Header.AUTHORIZATION.getValue(), authorization)
                        .accept(MediaType.TEXT_EVENT_STREAM)
                        .bodyValue(JSON.toJSONString(bodyParam))
                        .retrieve()
                        .bodyToFlux(String.class);
                List<String> items = new ArrayList<>();
                List<String> datasList = new ArrayList<>();
                // StringBuffer sb = new StringBuffer();
                return responseStream.map(chunk -> {
                    System.out.println(items.size());
                    System.out.println(chunk);
                    datasList.add(chunk);
                    JSONObject jsonChunk = JSONObject.parseObject(chunk);
                    String answer = (String)jsonChunk.getOrDefault("answer", "");
                    items.add(answer);
                    System.out.println(answer);
                    return AjaxResult.success(answer);
                })
                        .doOnTerminate(() ->{
                            aiHistoryEntity.setAnswer(String.join("",items));
                            aiHistoryEntity.setAnswerAll(String.join("\\n",datasList));
                            Long seconds = (System.currentTimeMillis() - start) / 1000;
                            aiHistoryEntity.setAnswerTime(seconds + "s");
                            aiHistoryEntity.setUpdateTime(LocalDateTime.now());
                            System.out.println(aiHistoryEntity.toString());
                        })
                        .doOnError(e -> {
                            aiHistoryEntity.setDescriptions("AI提问错误-"+e.getMessage());
                            System.out.println(aiHistoryEntity.toString());
                            System.err.println("Error: " + e.getMessage());
                            AjaxResult.error("Error: " + e.getMessage());
                        })
                        .onErrorReturn(AjaxResult.error("系统服务繁忙，请重新提问"));
            }else{
                aiHistoryEntity.setDescriptions("AI提问错误-未通过权限校验！");
                System.out.println(aiHistoryEntity.toString());
                return Flux.just(AjaxResult.error("AI提问错误-未通过权限校验！"));
            }
        }catch (Exception e){
            aiHistoryEntity.setDescriptions("AI提问错误-"+e.getMessage());
            System.out.println(aiHistoryEntity.toString());
            return Flux.just(AjaxResult.error("AI提问错误-系统错误！"));
        }
    }


    @Override
    public AjaxResult splitWordsAndPermission(HttpServletRequest request,  GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO){
        AiHistoryEntity aiHistoryEntity = new AiHistoryEntity();
        aiHistoryEntity.setQuestion(gacRAGFlowAIRequestVO.getQuestion());
        // 待处理 是否修改为新问题
        aiHistoryEntity.setActualQuestion(gacRAGFlowAIRequestVO.getQuestion());
        aiHistoryEntity.setUserId(gacRAGFlowAIRequestVO.getUserId());
        aiHistoryEntity.setUserName(gacRAGFlowAIRequestVO.getUserName());
        aiHistoryEntity.setSessionUuid(gacRAGFlowAIRequestVO.getSessionUuid());

        Long agId = null;
        try {
            // step1 ：先得获取分词可用的agent并开启会话-实际分词
            List<AiAgentType> agentTypeFenci = null;
            int retryCount = 0;
            boolean success = false;
            while (retryCount < 10 && !success) {
                agentTypeFenci = aiAgentTypeMapper.getAgentTypeFenci();
                if (agentTypeFenci != null && !agentTypeFenci.isEmpty()) {
                    success = true;
                    break;  // 直接退出循环
                }
                TimeUnit.SECONDS.sleep(1);
                retryCount++;
            }
            String fenciNew = null;
            if(success && CollectionUtils.isNotEmpty(agentTypeFenci)){
                Random random = new Random();
                int randomIndex = random.nextInt(agentTypeFenci.size());
                // 1、可用的Agent
                AiAgentType aiAgentType = agentTypeFenci.get(randomIndex);
                // 占用
                aiAgentTypeMapper.updateAgentUnused(aiAgentType.getId());
                System.out.println("占用分词agent=" + aiAgentType.getTitle());
                agId = aiAgentType.getId();
                // 2、获取sessionId
                System.out.println("获取分词会话");
                long starthh = System.currentTimeMillis();
                SessionVO sessionVO = this.creatSessionsByAgentsAndCompletions(gacRAGFlowAIRequestVO, aiAgentType);
                long endhh = (System.currentTimeMillis() - starthh);
                System.out.println("分词会话耗时-"+ endhh + "ms");
                if(sessionVO == null){
                    aiHistoryEntity.setPermission("0");
                    aiHistoryEntity.setRemarks("AI分词错误-获取会话失败！");
                    int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                    return AjaxResult.error(444,"请联系管理员检查AI分词服务！");
                }
                // 3、对问题进行分词
                String sessionId = sessionVO.getSessionId();
                // 实际分词与结果
                System.out.println("获取分词结果");
                long startfc = System.currentTimeMillis();
                String fenci = this.completionsQuestionWithAINotStream(gacRAGFlowAIRequestVO, aiAgentType, sessionId);
                long endfc = (System.currentTimeMillis() - startfc);
                System.out.println("ai分词耗时-"+ endfc + "ms");
                // 解除占用
                aiAgentTypeMapper.updateAgentUsed(aiAgentType.getId());
                System.out.println("解除分词占用agent=" + aiAgentType.getTitle());
                if(StringUtils.isNotEmpty(fenci)){
                    String temp = fenci.replaceAll("，", ",");
                    fenciNew = temp.replaceAll("[\\t\\n]", "");
                    System.out.println(gacRAGFlowAIRequestVO.getQuestion());
                    System.out.println(fenciNew);
                    aiHistoryEntity.setSplitWords(fenciNew);
                    aiHistoryEntity.setFenciSessionId(sessionId);
                    aiHistoryEntity.setFenciAgentId(aiAgentType.getAgentId());
                    aiHistoryEntity.setFenciAgentName(aiAgentType.getTitle());
                }else{
                    aiHistoryEntity.setPermission("0");
                    aiHistoryEntity.setRemarks("AI分词错误-"+ gacRAGFlowAIRequestVO.toString());
                    int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                    return AjaxResult.error(444,"请联系管理员检查AI分词服务！");
                }
            }else{
                aiHistoryEntity.setPermission("0");
                aiHistoryEntity.setRemarks("AI分词错误-无可用服务");
                int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                return AjaxResult.error(444,"请联系管理员检查AI分词服务！");
            }

            // step2 : 权限关键词拦截
            // 先获取指定用户的权限（调用新平台管家数据权限接口-行权限）
            String accessToken = request.getHeader("Authorization");
            String timestamp= request.getHeader("Timestamp");
            System.out.println("获取用户权限");
            long startqx = System.currentTimeMillis();
            List<DataSourcePerms> dataSourcePermsList = this.getUserDataPerm(accessToken, timestamp, sourceId);
            long endqx = (System.currentTimeMillis() - startqx);
            System.out.println("用户权限获取及解析耗时-"+ endqx + "ms");
            if(CollectionUtils.isNotEmpty(dataSourcePermsList)){
                Map<String,List<Map<String, Set<String>>>> permissionMap = new HashMap<>();
                for (DataSourcePerms sourcePerms : dataSourcePermsList) {
                    List<DataTablePerm> dataTablePerms = sourcePerms.getDataTablePerms();
                    for (DataTablePerm dataTablePerm : dataTablePerms) {
                        String tableName = dataTablePerm.getTableName();
                        //目前仅限行权限
                        List<RowPerm> rowPerms = dataTablePerm.getRowPerms();
                        List columnList = new ArrayList();
                        for (RowPerm rowPerm : rowPerms) {
                            String columnName = rowPerm.getColumnName();
                            List<ColumnValue> columnValues = rowPerm.getColumnValues();
                            Set<String> collectSet = columnValues.stream().map(ColumnValue::getColumnValue).collect(Collectors.toSet());
                            Map<String, Set<String>> columnvalueMap = new HashMap<>();
                            columnvalueMap.put(columnName,collectSet);
                            columnList.add(columnvalueMap);
                        }
                        permissionMap.put(tableName, columnList);
                    }
                }
                if(CollectionUtils.isNotEmpty(permissionMap) && StringUtils.isNotEmpty(fenciNew)){
                    System.out.println("用户权限校验");
                    long startqxjy = System.currentTimeMillis();
                    //json 格式拆分存在不同
                    fenciNew = fenciNew.replaceAll("^```json|```$", "");
                    JSONObject answerJson = JSONObject.parseObject(fenciNew);
                    Map map = JSONObject.parseObject(answerJson.toJSONString(), Map.class);
                    String pinpai = (String)map.getOrDefault("汽车品牌", null);
                    String zhibiao = (String)map.getOrDefault("指标", null);

                    String[] pinpaiSplit = pinpai.split("\\s*,\\s*");
                    List<String> pinpaiList = Arrays.asList(pinpaiSplit);
                    //step1、先判断分词中是否包含企业，再通过企业判断后续字段与逻辑
                    // 判断是否包含任意元素
                    List<String> qyList = Subsidiary.getAllChineseNames();
                    boolean containsAny = pinpaiList.stream().anyMatch(qyList::contains);
                    //System.out.println("是否包含任意元素: " + containsAny);
                    if(containsAny){
                        // 获取共同元素（企业名称、行业）
                        List<String> pinpaiElements = pinpaiList.stream()
                                .filter(qyList::contains)
                                .collect(Collectors.toList());
                        // 获取指标（分词中的指标）
                        String[] zhibiaoSplit = zhibiao.split("\\s*,\\s*");
                        List<String> zbcollect = Arrays.asList(zhibiaoSplit);

                        //System.out.println("共同元素: " + commonElements);
                        if(pinpaiElements.size() > 0 && zbcollect.size() > 0){
                            List<String> commonElements = pinpaiElements;
                            //先判定分词中是否包含特殊的“行业”企业
                            boolean containsIndustry = pinpaiElements.contains("行业");
                            if(containsIndustry){
                                commonElements = pinpaiElements.stream()
                                        .filter(str -> !"行业".equals(str))
                                        .collect(Collectors.toList());
                                //全部放通
                                Set<String> qxAllSets = new HashSet<>();
                                for (String permission : permissionMap.keySet()) {
                                    List<Map<String, Set<String>>> listMap = permissionMap.getOrDefault(permission, null);
                                    if(listMap != null){
                                        //用户权限
                                        for (Map<String, Set<String>> stringSetMap : listMap) {
                                            for (String key : stringSetMap.keySet()) {
                                                Set<String> stringSet = stringSetMap.getOrDefault(key, null);
                                                if(stringSet != null  && stringSet.size() > 0){
                                                    qxAllSets.addAll(stringSet);
                                                }
                                            }
                                        }
                                    }
                                }
                                if(qxAllSets != null && qxAllSets.size() > 0 ){
                                    boolean hasqx = qxAllSets.contains("行业");
                                    if(hasqx){
                                        long endqxjy = (System.currentTimeMillis() - startqxjy);
                                        System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                        // 权限校验通过
                                        System.out.println("---权限校验通过---");
                                        aiHistoryEntity.setPermission("1");
                                        int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                        if(insert > 0){
                                            return AjaxResult.success("权限校验通过", aiHistoryEntity);
                                        }else{
                                            log.error("Error-会话数据保存失败: " + aiHistoryEntity.toString());
                                            return AjaxResult.error(444,"请联系管理员检查校验服务！");
                                        }
                                    }else{
                                        aiHistoryEntity.setPermission("0");
                                        aiHistoryEntity.setRemarks("用户提问有误【无行业指标权限】-"+ gacRAGFlowAIRequestVO.toString());
                                        int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                        return AjaxResult.error(444,"请联系管理员获取授权，无行业指标权限！");
                                    }
                                }else{
                                    long endqxjy = (System.currentTimeMillis() - startqxjy);
                                    System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                    aiHistoryEntity.setPermission("0");
                                    String temp = "; token-" + accessToken + "; timestamp-" + timestamp + "; sourceId-" + sourceId;
                                    aiHistoryEntity.setRemarks("行权限获取为空-"+ gacRAGFlowAIRequestVO.toString() + temp);
                                    int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                    return AjaxResult.error(444,"请联系管理员获取授权-行权限！");
                                }
                            }

                            //step1: 判断分词的指标里有没有超出本期范围外的，如果有直接打回
                            Set<String> zbAllSet = new HashSet<>();
                            // 处理企业的情况 1、有没有不可能出现的指标 2、出现的指标能不能全部覆盖
                            for (String commonElement : commonElements) {
                                if (commonElement.equals(Subsidiary.GAC_HYPER.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_HYPER));
                                }
                                if (commonElement.equals(Subsidiary.GAC_AION.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_AION));
                                }
                                if (commonElement.equals(Subsidiary.GAC_TRUMPCHI.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_TRUMPCHI));
                                }
                                if (commonElement.equals(Subsidiary.GAC_HONDA.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_HONDA));
                                }
                                if (commonElement.equals(Subsidiary.GAC_TOYOTA.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_TOYOTA));
                                }
                                if (commonElement.equals(Subsidiary.GAC_INTL.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_INTL));
                                }
                                if (commonElement.equals(Subsidiary.GAC_LEADWAY.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_LEADWAY));
                                }
                                if (commonElement.equals(Subsidiary.GAC_GROUP.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_GROUP));
                                }
                            }
                            // 获取分支中的指标元素与企业可用指标元素的-共同元素（如果可以覆盖全部，则表示所有指标均为有效指标）
                            List<String> gtzb = zbcollect.stream()
                                    .filter(zbAllSet::contains)
                                    .collect(Collectors.toList());
                            // 如果分词指标集合数量不等于 共同元素数量
                            if(gtzb == null && gtzb.size() == 0){
                                long endqxjy = (System.currentTimeMillis() - startqxjy);
                                System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                aiHistoryEntity.setPermission("0");
                                aiHistoryEntity.setRemarks("用户提问有误【超出指标范围】-"+ gacRAGFlowAIRequestVO.toString());
                                int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                return AjaxResult.error(444,"超出知识库指标范围，请重新发问！");
                            }
                            // step2: 判断用户权限是否可以
                            if(commonElements.size() > 1){
                                // 多企业判断
                                Set<String> indicatorSets = new HashSet<>();
                                for (String commonElement : commonElements) {
                                    String tableName = Subsidiary.getTableNameByChineseName(commonElement);
                                    if(tableName != null){
                                        List<Map<String, Set<String>>> permission = permissionMap.getOrDefault(tableName, null);
                                        if(permission != null){
                                            //用户权限
                                            for (Map<String, Set<String>> stringSetMap : permission) {
                                                for (String key : stringSetMap.keySet()) {
                                                    Set<String> stringSet = stringSetMap.getOrDefault(key, null);
                                                    if(stringSet != null  && stringSet.size() > 0){
                                                        indicatorSets.addAll(stringSet);
                                                    }
                                                }
                                            }
                                        }else{
                                            long endqxjy = (System.currentTimeMillis() - startqxjy);
                                            System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                            aiHistoryEntity.setPermission("0");
                                            aiHistoryEntity.setRemarks("用户提问有误【企业权限不足】-"+ gacRAGFlowAIRequestVO.toString());
                                            int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                            return AjaxResult.error(444,"超出权限范围，请重新提问！");
                                        }
                                    }else{
                                        long endqxjy = (System.currentTimeMillis() - startqxjy);
                                        System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                        aiHistoryEntity.setPermission("0");
                                        aiHistoryEntity.setRemarks("用户提问有误【企业信息有误】-"+ gacRAGFlowAIRequestVO.toString());
                                        int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                        return AjaxResult.error(444,"问题输入有误，请先明确企业范围！");
                                    }
                                }
                                if(indicatorSets != null && indicatorSets.size() > 0){
                                    // 共同指标权限
                                    List<String> gtzbqx = zbcollect.stream()
                                            .filter(indicatorSets::contains)
                                            .collect(Collectors.toList());
                                    // 如果分词指标集合数量不等于 共同元素数量
                                    if(zbcollect.size() != gtzbqx.size()){
                                        List<String> expcollect = zbcollect.stream()
                                                .filter(item -> !indicatorSets.contains(item))
                                                .collect(Collectors.toList());
                                        //权限校验不通过
                                        long endqxjy = (System.currentTimeMillis() - startqxjy);
                                        System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                        aiHistoryEntity.setPermission("0");
                                        aiHistoryEntity.setRemarks("用户提问【超出权限范围】-"+ gacRAGFlowAIRequestVO.toString());
                                        int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                        return AjaxResult.error(444,"【"+expcollect.toString()+"】超出权限范围，请重新提问！");
                                    }else{
                                        // 权限校验通过
                                        long endqxjy = (System.currentTimeMillis() - startqxjy);
                                        System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                        System.out.println("---权限校验通过---");
                                        aiHistoryEntity.setPermission("1");
                                        int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                        if(insert > 0){
                                            return AjaxResult.success("权限校验通过", aiHistoryEntity);
                                        }else{
                                            log.error("Error-会话数据保存失败: " + aiHistoryEntity.toString());
                                            return AjaxResult.error(444,"请联系管理员检查校验服务！");
                                        }
                                    }
                                }else{
                                    //权限校验不通过
                                    long endqxjy = (System.currentTimeMillis() - startqxjy);
                                    System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                    aiHistoryEntity.setPermission("0");
                                    aiHistoryEntity.setRemarks("用户提问【超出权限范围】-"+ gacRAGFlowAIRequestVO.toString());
                                    int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                    return AjaxResult.error(444,"超出权限范围，请重新提问！");
                                }
                            }else{
                                //单企业判断
                                String qyName = commonElements.get(0);
                                String tableName = Subsidiary.getTableNameByChineseName(qyName);
                                if(tableName != null){
                                    List<Map<String, Set<String>>> permission = permissionMap.getOrDefault(tableName, null);
                                    if(permission != null){
                                        Set<String> qxAllSets = new HashSet<>();
                                        //用户权限
                                        for (Map<String, Set<String>> stringSetMap : permission) {
                                            for (String key : stringSetMap.keySet()) {
                                                Set<String> stringSet = stringSetMap.getOrDefault(key, null);
                                                if(stringSet != null && stringSet.size() > 0){
                                                    qxAllSets.addAll(stringSet);
                                                }
                                            }
                                        }
                                        if(qxAllSets != null && qxAllSets.size() > 0){
                                            //权限
                                            List<String> gtzbqx = zbcollect.stream()
                                                    .filter(qxAllSets::contains)
                                                    .collect(Collectors.toList());
                                            // 如果分词指标集合数量不等于 共同元素数量
                                            if(zbcollect.size() != gtzbqx.size()){
                                                List<String> expcollect = zbcollect.stream()
                                                        .filter(item -> !qxAllSets.contains(item))
                                                        .collect(Collectors.toList());
                                                //权限校验不通过
                                                long endqxjy = (System.currentTimeMillis() - startqxjy);
                                                System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                                aiHistoryEntity.setPermission("0");
                                                aiHistoryEntity.setRemarks("用户提问【超出权限范围】-"+ gacRAGFlowAIRequestVO.toString());
                                                int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                                return AjaxResult.error(444,"【"+expcollect.toString()+"】超出权限范围，请重新提问！");
                                            }else{
                                                // 权限校验通过
                                                long endqxjy = (System.currentTimeMillis() - startqxjy);
                                                System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                                System.out.println("---权限校验通过---");
                                                aiHistoryEntity.setPermission("1");
                                                int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                                if(insert > 0){
                                                    return AjaxResult.success("权限校验通过", aiHistoryEntity);
                                                }else{
                                                    log.error("Error-会话数据保存失败: " + aiHistoryEntity.toString());
                                                    return AjaxResult.error(444,"请联系管理员检查校验服务！");
                                                }
                                            }
                                        }else{
                                            long endqxjy = (System.currentTimeMillis() - startqxjy);
                                            System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                            aiHistoryEntity.setPermission("0");
                                            aiHistoryEntity.setRemarks("用户提问有误【指标权限不足】-"+ gacRAGFlowAIRequestVO.toString());
                                            int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                            return AjaxResult.error(444,"超出权限范围，请重新提问！");
                                        }
                                    }else{
                                        long endqxjy = (System.currentTimeMillis() - startqxjy);
                                        System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                        aiHistoryEntity.setPermission("0");
                                        aiHistoryEntity.setRemarks("用户提问有误【企业权限不足】-"+ gacRAGFlowAIRequestVO.toString());
                                        int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                        return AjaxResult.error(444,"超出权限范围，请重新提问！");
                                    }
                                }else{
                                    long endqxjy = (System.currentTimeMillis() - startqxjy);
                                    System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                    aiHistoryEntity.setPermission("0");
                                    aiHistoryEntity.setRemarks("用户提问有误【企业信息有误】-"+ gacRAGFlowAIRequestVO.toString());
                                    int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                    return AjaxResult.error(444,"问题输入有误，请先明确企业范围！");
                                }
                            }
                        }else{
                            long endqxjy = (System.currentTimeMillis() - startqxjy);
                            System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                            aiHistoryEntity.setPermission("0");
                            aiHistoryEntity.setRemarks("用户提问有误【无指标信息】-"+ gacRAGFlowAIRequestVO.toString());
                            int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                            return AjaxResult.error(444,"问题输入有误，请先明确指标信息！");
                        }
                    }else{
                        long endqxjy = (System.currentTimeMillis() - startqxjy);
                        System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                        aiHistoryEntity.setPermission("0");
                        aiHistoryEntity.setRemarks("用户提问有误【无企业/行业信息】-"+ gacRAGFlowAIRequestVO.toString());
                        int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                        return AjaxResult.error(444,"问题输入有误，请先明确企业范围！");
                    }
                }else{
                    aiHistoryEntity.setPermission("0");
                    String temp = "; token-" + accessToken + "; timestamp-" + timestamp + "; sourceId-" + sourceId;
                    aiHistoryEntity.setRemarks("行权限获取为空-"+ gacRAGFlowAIRequestVO.toString() + temp);
                    int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                    return AjaxResult.error(444,"请联系管理员获取授权-行权限！");
                }
            }else{
                aiHistoryEntity.setPermission("0");
                String temp = "; token-" + accessToken + "; timestamp-" + timestamp + "; sourceId-" + sourceId;
                aiHistoryEntity.setRemarks("权限获取错误-"+ gacRAGFlowAIRequestVO.toString() + temp);
                int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                return AjaxResult.error(444,"请联系管理员获取授权/权限获取失败！");
            }
        }catch (Exception e){
            if(null != agId){
                aiAgentTypeMapper.updateAgentUsed(agId);
            }
            aiHistoryEntity.setPermission("0");
            aiHistoryEntity.setRemarks("分词及权限校验错误-"+ e.getMessage());
            int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
            return AjaxResult.error(444,"请联系管理员检查服务！");
        }
    }


    @Override
    public AjaxResult splitWordsAndPermissionString(HttpServletRequest request,  GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO){
        AiHistoryEntity aiHistoryEntity = new AiHistoryEntity();
        aiHistoryEntity.setQuestion(gacRAGFlowAIRequestVO.getQuestion());
        // 待处理 是否修改为新问题
        aiHistoryEntity.setActualQuestion(gacRAGFlowAIRequestVO.getQuestion());
        aiHistoryEntity.setUserId(gacRAGFlowAIRequestVO.getUserId());
        aiHistoryEntity.setUserName(gacRAGFlowAIRequestVO.getUserName());
        aiHistoryEntity.setSessionUuid(gacRAGFlowAIRequestVO.getSessionUuid());

        Long agId = null;
        try {
            // step1 ：先得获取分词可用的agent并开启会话-实际分词
            List<AiAgentType> agentTypeFenci = null;
            int retryCount = 0;
            boolean success = false;
            while (retryCount < 10 && !success) {
                agentTypeFenci = aiAgentTypeMapper.getAgentTypeFenci();
                if (agentTypeFenci != null && !agentTypeFenci.isEmpty()) {
                    success = true;
                    break;  // 直接退出循环
                }
                TimeUnit.SECONDS.sleep(1);
                retryCount++;
            }
            String fenciNew = null;
            if(success && CollectionUtils.isNotEmpty(agentTypeFenci)){
                Random random = new Random();
                int randomIndex = random.nextInt(agentTypeFenci.size());
                // 1、可用的Agent
                AiAgentType aiAgentType = agentTypeFenci.get(randomIndex);
                // 占用
                aiAgentTypeMapper.updateAgentUnused(aiAgentType.getId());
                System.out.println("占用分词agent=" + aiAgentType.getTitle());
                agId = aiAgentType.getId();
                // 2、获取sessionId
                System.out.println("获取分词会话");
                long starthh = System.currentTimeMillis();
                SessionVO sessionVO = this.creatSessionsByAgentsAndCompletions(gacRAGFlowAIRequestVO, aiAgentType);
                long endhh = (System.currentTimeMillis() - starthh);
                System.out.println("分词会话耗时-"+ endhh + "ms");
                if(sessionVO == null){
                    aiHistoryEntity.setPermission("0");
                    aiHistoryEntity.setRemarks("AI分词错误-获取会话失败！");
                    int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                    return AjaxResult.error(444,"请联系管理员检查AI分词服务！");
                }
                // 3、对问题进行分词
                String sessionId = sessionVO.getSessionId();
                // 实际分词与结果
                System.out.println("获取分词结果");
                long startfc = System.currentTimeMillis();
                String fenci = this.completionsQuestionWithAINotStream(gacRAGFlowAIRequestVO, aiAgentType, sessionId);
                long endfc = (System.currentTimeMillis() - startfc);
                System.out.println("ai分词耗时-"+ endfc + "ms");
                // 解除占用
                aiAgentTypeMapper.updateAgentUsed(aiAgentType.getId());
                System.out.println("解除分词占用agent=" + aiAgentType.getTitle());
                if(StringUtils.isNotEmpty(fenci)){
                    String temp = fenci.replaceAll("，", ",");
                    fenciNew = temp.replaceAll("[\\t\\n]", "");
                    System.out.println(gacRAGFlowAIRequestVO.getQuestion());
                    System.out.println(fenciNew);
                    aiHistoryEntity.setSplitWords(fenciNew);
                    aiHistoryEntity.setFenciSessionId(sessionId);
                    aiHistoryEntity.setFenciAgentId(aiAgentType.getAgentId());
                    aiHistoryEntity.setFenciAgentName(aiAgentType.getTitle());
                }else{
                    aiHistoryEntity.setPermission("0");
                    aiHistoryEntity.setRemarks("AI分词错误-"+ gacRAGFlowAIRequestVO.toString());
                    int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                    return AjaxResult.error(444,"请联系管理员检查AI分词服务！");
                }
            }else{
                aiHistoryEntity.setPermission("0");
                aiHistoryEntity.setRemarks("AI分词错误-无可用服务");
                int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                return AjaxResult.error(444,"请联系管理员检查AI分词服务！");
            }

            // step2 : 权限关键词拦截
            // 先获取指定用户的权限（调用新平台管家数据权限接口-行权限）
            String accessToken = request.getHeader("Authorization");
            String timestamp= request.getHeader("Timestamp");
            System.out.println("获取用户权限");
            long startqx = System.currentTimeMillis();
            List<DataSourcePerms> dataSourcePermsList = this.getUserDataPerm(accessToken, timestamp, sourceId);
            long endqx = (System.currentTimeMillis() - startqx);
            System.out.println("用户权限获取及解析耗时-"+ endqx + "ms");
            if(CollectionUtils.isNotEmpty(dataSourcePermsList)){
                Map<String,List<Map<String, Set<String>>>> permissionMap = new HashMap<>();
                for (DataSourcePerms sourcePerms : dataSourcePermsList) {
                    List<DataTablePerm> dataTablePerms = sourcePerms.getDataTablePerms();
                    for (DataTablePerm dataTablePerm : dataTablePerms) {
                        String tableName = dataTablePerm.getTableName();
                        //目前仅限行权限
                        List<RowPerm> rowPerms = dataTablePerm.getRowPerms();
                        List columnList = new ArrayList();
                        for (RowPerm rowPerm : rowPerms) {
                            String columnName = rowPerm.getColumnName();
                            List<ColumnValue> columnValues = rowPerm.getColumnValues();
                            Set<String> collectSet = columnValues.stream().map(ColumnValue::getColumnValue).collect(Collectors.toSet());
                            Map<String, Set<String>> columnvalueMap = new HashMap<>();
                            columnvalueMap.put(columnName,collectSet);
                            columnList.add(columnvalueMap);
                        }
                        permissionMap.put(tableName, columnList);
                    }
                }
                if(CollectionUtils.isNotEmpty(permissionMap) && StringUtils.isNotEmpty(fenciNew)){
                    System.out.println("用户权限校验");
                    long startqxjy = System.currentTimeMillis();
                    String[] fenciSplit = fenciNew.split("\\s*,\\s*");
                    List<String> fenciList = Arrays.asList(fenciSplit);
                    //step1、先判断分词中是否包含企业，再通过企业判断后续字段与逻辑
                    // 判断是否包含任意元素
                    List<String> qyList = Subsidiary.getAllChineseNames();
                    boolean containsAny = fenciList.stream().anyMatch(qyList::contains);
                    //System.out.println("是否包含任意元素: " + containsAny);
                    if(containsAny){
                        // 获取共同元素（企业名称）
                        List<String> commonElements = fenciList.stream()
                                .filter(qyList::contains)
                                .collect(Collectors.toList());
                        // 获取剩余元素（分词中的指标）
                        List<String> zbcollect = fenciList.stream()
                                .filter(item -> !commonElements.contains(item))
                                .collect(Collectors.toList());
                        //System.out.println("共同元素: " + commonElements);
                        if(commonElements.size() > 0 && zbcollect.size() > 0){
                            //step1: 先判断分词的指标里有没有超出本期范围外的，如果有直接打回
                            Set<String> zbAllSet = new HashSet<>();
                            // 处理企业的情况 1、有没有不可能出现的指标 2、出现的指标能不能全部覆盖
                            for (String commonElement : commonElements) {
                                if (commonElement.equals(Subsidiary.GAC_HYPER.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_HYPER));
                                }
                                if (commonElement.equals(Subsidiary.GAC_AION.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_AION));
                                }
                                if (commonElement.equals(Subsidiary.GAC_TRUMPCHI.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_TRUMPCHI));
                                }
                                if (commonElement.equals(Subsidiary.GAC_HONDA.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_HONDA));
                                }
                                if (commonElement.equals(Subsidiary.GAC_TOYOTA.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_TOYOTA));
                                }
                                if (commonElement.equals(Subsidiary.GAC_INTL.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_INTL));
                                }
                                if (commonElement.equals(Subsidiary.GAC_LEADWAY.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_LEADWAY));
                                }
                                if (commonElement.equals(Subsidiary.GAC_GROUP.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_GROUP));
                                }
                            }
                            // 获取分支中的指标元素与企业可用指标元素的-共同元素（如果可以覆盖全部，则表示所有指标均为有效指标）
                            List<String> gtzb = zbcollect.stream()
                                    .filter(zbAllSet::contains)
                                    .collect(Collectors.toList());
                            // 如果分词指标集合数量不等于 共同元素数量
                            if(gtzb == null && gtzb.size() == 0){
                                long endqxjy = (System.currentTimeMillis() - startqxjy);
                                System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                aiHistoryEntity.setPermission("0");
                                aiHistoryEntity.setRemarks("用户提问有误【超出指标范围】-"+ gacRAGFlowAIRequestVO.toString());
                                int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                return AjaxResult.error(444,"超出知识库指标范围，请重新发问！");
                            }
                            // step2: 判断用户权限是否可以
                            if(commonElements.size() > 1){
                                // 多企业判断
                                Set<String> indicatorSets = new HashSet<>();
                                for (String commonElement : commonElements) {
                                    String tableName = Subsidiary.getTableNameByChineseName(commonElement);
                                    if(tableName != null){
                                        List<Map<String, Set<String>>> permission = permissionMap.getOrDefault(tableName, null);
                                        if(permission != null){
                                            //用户权限
                                            for (Map<String, Set<String>> stringSetMap : permission) {
                                                for (String key : stringSetMap.keySet()) {
                                                    Set<String> stringSet = stringSetMap.getOrDefault(key, null);
                                                    if(stringSet != null  && stringSet.size() > 0){
                                                        indicatorSets.addAll(stringSet);
                                                    }
                                                }
                                            }
                                        }else{
                                            long endqxjy = (System.currentTimeMillis() - startqxjy);
                                            System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                            aiHistoryEntity.setPermission("0");
                                            aiHistoryEntity.setRemarks("用户提问有误【企业权限不足】-"+ gacRAGFlowAIRequestVO.toString());
                                            int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                            return AjaxResult.error(444,"超出权限范围，请重新提问！");
                                        }
                                    }else{
                                        long endqxjy = (System.currentTimeMillis() - startqxjy);
                                        System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                        aiHistoryEntity.setPermission("0");
                                        aiHistoryEntity.setRemarks("用户提问有误【企业信息有误】-"+ gacRAGFlowAIRequestVO.toString());
                                        int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                        return AjaxResult.error(444,"问题输入有误，请先明确企业范围！");
                                    }
                                }
                                if(indicatorSets != null && indicatorSets.size() > 0){
                                    // 共同指标权限
                                    List<String> gtzbqx = zbcollect.stream()
                                            .filter(indicatorSets::contains)
                                            .collect(Collectors.toList());
                                    // 如果分词指标集合数量不等于 共同元素数量
                                    if(zbcollect.size() != gtzbqx.size()){
                                        List<String> expcollect = zbcollect.stream()
                                                .filter(item -> !indicatorSets.contains(item))
                                                .collect(Collectors.toList());
                                        //权限校验不通过
                                        long endqxjy = (System.currentTimeMillis() - startqxjy);
                                        System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                        aiHistoryEntity.setPermission("0");
                                        aiHistoryEntity.setRemarks("用户提问【超出权限范围】-"+ gacRAGFlowAIRequestVO.toString());
                                        int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                        return AjaxResult.error(444,"【"+expcollect.toString()+"】超出权限范围，请重新提问！");
                                    }else{
                                        // 权限校验通过
                                        long endqxjy = (System.currentTimeMillis() - startqxjy);
                                        System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                        System.out.println("---权限校验通过---");
                                        aiHistoryEntity.setPermission("1");
                                        int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                        if(insert > 0){
                                            return AjaxResult.success("权限校验通过", aiHistoryEntity);
                                        }else{
                                            log.error("Error-会话数据保存失败: " + aiHistoryEntity.toString());
                                            return AjaxResult.error(444,"请联系管理员检查校验服务！");
                                        }
                                    }
                                }else{
                                    //权限校验不通过
                                    long endqxjy = (System.currentTimeMillis() - startqxjy);
                                    System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                    aiHistoryEntity.setPermission("0");
                                    aiHistoryEntity.setRemarks("用户提问【超出权限范围】-"+ gacRAGFlowAIRequestVO.toString());
                                    int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                    return AjaxResult.error(444,"超出权限范围，请重新提问！");
                                }
                            }else{
                                //单企业判断
                                String qyName = commonElements.get(0);
                                String tableName = Subsidiary.getTableNameByChineseName(qyName);
                                if(tableName != null){
                                    List<Map<String, Set<String>>> permission = permissionMap.getOrDefault(tableName, null);
                                    if(permission != null){
                                        Set<String> qxAllSets = new HashSet<>();
                                        //用户权限
                                        for (Map<String, Set<String>> stringSetMap : permission) {
                                            for (String key : stringSetMap.keySet()) {
                                                Set<String> stringSet = stringSetMap.getOrDefault(key, null);
                                                if(stringSet != null && stringSet.size() > 0){
                                                    qxAllSets.addAll(stringSet);
                                                }
                                            }
                                        }
                                        if(qxAllSets != null && qxAllSets.size() > 0){
                                            //权限
                                            List<String> gtzbqx = zbcollect.stream()
                                                    .filter(qxAllSets::contains)
                                                    .collect(Collectors.toList());
                                            // 如果分词指标集合数量不等于 共同元素数量
                                            if(zbcollect.size() != gtzbqx.size()){
                                                List<String> expcollect = zbcollect.stream()
                                                        .filter(item -> !qxAllSets.contains(item))
                                                        .collect(Collectors.toList());
                                                //权限校验不通过
                                                long endqxjy = (System.currentTimeMillis() - startqxjy);
                                                System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                                aiHistoryEntity.setPermission("0");
                                                aiHistoryEntity.setRemarks("用户提问【超出权限范围】-"+ gacRAGFlowAIRequestVO.toString());
                                                int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                                return AjaxResult.error(444,"【"+expcollect.toString()+"】超出权限范围，请重新提问！");
                                            }else{
                                                // 权限校验通过
                                                long endqxjy = (System.currentTimeMillis() - startqxjy);
                                                System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                                System.out.println("---权限校验通过---");
                                                aiHistoryEntity.setPermission("1");
                                                int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                                if(insert > 0){
                                                    return AjaxResult.success("权限校验通过", aiHistoryEntity);
                                                }else{
                                                    log.error("Error-会话数据保存失败: " + aiHistoryEntity.toString());
                                                    return AjaxResult.error(444,"请联系管理员检查校验服务！");
                                                }
                                            }
                                        }else{
                                            long endqxjy = (System.currentTimeMillis() - startqxjy);
                                            System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                            aiHistoryEntity.setPermission("0");
                                            aiHistoryEntity.setRemarks("用户提问有误【指标权限不足】-"+ gacRAGFlowAIRequestVO.toString());
                                            int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                            return AjaxResult.error(444,"超出权限范围，请重新提问！");
                                        }
                                    }else{
                                        long endqxjy = (System.currentTimeMillis() - startqxjy);
                                        System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                        aiHistoryEntity.setPermission("0");
                                        aiHistoryEntity.setRemarks("用户提问有误【企业权限不足】-"+ gacRAGFlowAIRequestVO.toString());
                                        int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                        return AjaxResult.error(444,"超出权限范围，请重新提问！");
                                    }
                                }else{
                                    long endqxjy = (System.currentTimeMillis() - startqxjy);
                                    System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                    aiHistoryEntity.setPermission("0");
                                    aiHistoryEntity.setRemarks("用户提问有误【企业信息有误】-"+ gacRAGFlowAIRequestVO.toString());
                                    int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                    return AjaxResult.error(444,"问题输入有误，请先明确企业范围！");
                                }
                            }
                        }else{
                            long endqxjy = (System.currentTimeMillis() - startqxjy);
                            System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                            aiHistoryEntity.setPermission("0");
                            aiHistoryEntity.setRemarks("用户提问有误【无指标信息】-"+ gacRAGFlowAIRequestVO.toString());
                            int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                            return AjaxResult.error(444,"问题输入有误，请先明确指标信息！");
                        }
                    }else{
                        //无企业信息的情况下，再判定分词中是否包含特殊的“行业”指标
                        boolean containsIndustry = fenciList.contains("行业");
                        if(containsIndustry){
                            //全部放通
                            Set<String> qxAllSets = new HashSet<>();
                            for (String permission : permissionMap.keySet()) {
                                List<Map<String, Set<String>>> listMap = permissionMap.getOrDefault(permission, null);
                                if(listMap != null){
                                    //用户权限
                                    for (Map<String, Set<String>> stringSetMap : listMap) {
                                        for (String key : stringSetMap.keySet()) {
                                            Set<String> stringSet = stringSetMap.getOrDefault(key, null);
                                            if(stringSet != null  && stringSet.size() > 0){
                                                qxAllSets.addAll(stringSet);
                                            }
                                        }
                                    }
                                }
                            }
                            if(qxAllSets != null && qxAllSets.size() > 0 ){
                                boolean hasqx = qxAllSets.contains("行业");
                                if(hasqx){
                                    long endqxjy = (System.currentTimeMillis() - startqxjy);
                                    System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                    // 权限校验通过
                                    System.out.println("---权限校验通过---");
                                    aiHistoryEntity.setPermission("1");
                                    int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                    if(insert > 0){
                                        return AjaxResult.success("权限校验通过", aiHistoryEntity);
                                    }else{
                                        log.error("Error-会话数据保存失败: " + aiHistoryEntity.toString());
                                        return AjaxResult.error(444,"请联系管理员检查校验服务！");
                                    }
                                }else{
                                    aiHistoryEntity.setPermission("0");
                                    aiHistoryEntity.setRemarks("用户提问有误【无行业指标权限】-"+ gacRAGFlowAIRequestVO.toString());
                                    int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                    return AjaxResult.error(444,"请联系管理员获取授权，无行业指标权限！");
                                }
                            }else{
                                long endqxjy = (System.currentTimeMillis() - startqxjy);
                                System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                aiHistoryEntity.setPermission("0");
                                String temp = "; token-" + accessToken + "; timestamp-" + timestamp + "; sourceId-" + sourceId;
                                aiHistoryEntity.setRemarks("行权限获取为空-"+ gacRAGFlowAIRequestVO.toString() + temp);
                                int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                return AjaxResult.error(444,"请联系管理员获取授权-行权限！");
                            }
                        }else{
                            long endqxjy = (System.currentTimeMillis() - startqxjy);
                            System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                            aiHistoryEntity.setPermission("0");
                            aiHistoryEntity.setRemarks("用户提问有误【无企业信息】-"+ gacRAGFlowAIRequestVO.toString());
                            int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                            return AjaxResult.error(444,"问题输入有误，请先明确企业范围！");
                        }
                    }
                }else{
                    aiHistoryEntity.setPermission("0");
                    String temp = "; token-" + accessToken + "; timestamp-" + timestamp + "; sourceId-" + sourceId;
                    aiHistoryEntity.setRemarks("行权限获取为空-"+ gacRAGFlowAIRequestVO.toString() + temp);
                    int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                    return AjaxResult.error(444,"请联系管理员获取授权-行权限！");
                }
            }else{
                aiHistoryEntity.setPermission("0");
                String temp = "; token-" + accessToken + "; timestamp-" + timestamp + "; sourceId-" + sourceId;
                aiHistoryEntity.setRemarks("权限获取错误-"+ gacRAGFlowAIRequestVO.toString() + temp);
                int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                return AjaxResult.error(444,"请联系管理员获取授权/权限获取失败！");
            }
        }catch (Exception e){
            if(null != agId){
                aiAgentTypeMapper.updateAgentUsed(agId);
            }
            aiHistoryEntity.setPermission("0");
            aiHistoryEntity.setRemarks("分词及权限校验错误-"+ e.getMessage());
            int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
            return AjaxResult.error(444,"请联系管理员检查服务！");
        }
    }


    @Override
    public AjaxResult splitWordsAndPermissionChat(HttpServletRequest request,  GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO){
        AiHistoryEntity aiHistoryEntity = new AiHistoryEntity();
        aiHistoryEntity.setQuestion(gacRAGFlowAIRequestVO.getQuestion());
        // 待处理 是否修改为新问题
        aiHistoryEntity.setActualQuestion(gacRAGFlowAIRequestVO.getQuestion());
        aiHistoryEntity.setUserId(gacRAGFlowAIRequestVO.getUserId());
        aiHistoryEntity.setUserName(gacRAGFlowAIRequestVO.getUserName());
        aiHistoryEntity.setSessionUuid(gacRAGFlowAIRequestVO.getSessionUuid());

        try {
            // step1 ：开启会话-实际分词
                // 实际分词与结果
                String fenciNew = null;
                System.out.println("获取分词结果");
                long startfc = System.currentTimeMillis();
                String fenci =  this.getQuestionSplitWords(gacRAGFlowAIRequestVO, new AiHistoryEntity());
                long endfc = (System.currentTimeMillis() - startfc);
                System.out.println("ai分词耗时-"+ endfc + "ms");
                if(StringUtils.isNotEmpty(fenci)){
                    String temp = fenci.replaceAll("，", ",");
                    fenciNew = temp.replaceAll("[\\t\\n]", "");
                    System.out.println(gacRAGFlowAIRequestVO.getQuestion());
                    System.out.println(fenciNew);
                    aiHistoryEntity.setSplitWords(fenciNew);
                }else{
                    aiHistoryEntity.setPermission("0");
                    aiHistoryEntity.setRemarks("AI分词错误-"+ gacRAGFlowAIRequestVO.toString());
                    int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                    return AjaxResult.error(444,"请联系管理员检查AI分词服务！");
                }

            // step2 : 权限关键词拦截
            // 先获取指定用户的权限（调用新平台管家数据权限接口-行权限）
            String accessToken = request.getHeader("Authorization");
            String timestamp= request.getHeader("Timestamp");
            System.out.println("获取用户权限");
            long startqx = System.currentTimeMillis();
            List<DataSourcePerms> dataSourcePermsList = this.getUserDataPerm(accessToken, timestamp, sourceId);
            long endqx = (System.currentTimeMillis() - startqx);
            System.out.println("用户权限获取及解析耗时-"+ endqx + "ms");
            if(CollectionUtils.isNotEmpty(dataSourcePermsList)){
                Map<String,List<Map<String, Set<String>>>> permissionMap = new HashMap<>();
                for (DataSourcePerms sourcePerms : dataSourcePermsList) {
                    List<DataTablePerm> dataTablePerms = sourcePerms.getDataTablePerms();
                    for (DataTablePerm dataTablePerm : dataTablePerms) {
                        String tableName = dataTablePerm.getTableName();
                        //目前仅限行权限
                        List<RowPerm> rowPerms = dataTablePerm.getRowPerms();
                        List columnList = new ArrayList();
                        for (RowPerm rowPerm : rowPerms) {
                            String columnName = rowPerm.getColumnName();
                            List<ColumnValue> columnValues = rowPerm.getColumnValues();
                            Set<String> collectSet = columnValues.stream().map(ColumnValue::getColumnValue).collect(Collectors.toSet());
                            Map<String, Set<String>> columnvalueMap = new HashMap<>();
                            columnvalueMap.put(columnName,collectSet);
                            columnList.add(columnvalueMap);
                        }
                        permissionMap.put(tableName, columnList);
                    }
                }
                if(CollectionUtils.isNotEmpty(permissionMap) && StringUtils.isNotEmpty(fenciNew)){
                    System.out.println("用户权限校验");
                    long startqxjy = System.currentTimeMillis();
                    String[] fenciSplit = fenciNew.split("\\s*,\\s*");
                    List<String> fenciList = Arrays.asList(fenciSplit);
                    //step1、先判断分词中是否包含企业，再通过企业判断后续字段与逻辑
                    // 判断是否包含任意元素
                    List<String> qyList = Subsidiary.getAllChineseNames();
                    boolean containsAny = fenciList.stream().anyMatch(qyList::contains);
                    //System.out.println("是否包含任意元素: " + containsAny);
                    if(containsAny){
                        // 获取共同元素（企业名称）
                        List<String> commonElements = fenciList.stream()
                                .filter(qyList::contains)
                                .collect(Collectors.toList());
                        // 获取剩余元素（分词中的指标）
                        List<String> zbcollect = fenciList.stream()
                                .filter(item -> !commonElements.contains(item))
                                .collect(Collectors.toList());
                        //System.out.println("共同元素: " + commonElements);
                        if(commonElements.size() > 0 && zbcollect.size() > 0){
                            //step1: 先判断分词的指标里有没有超出本期范围外的，如果有直接打回
                            Set<String> zbAllSet = new HashSet<>();
                            // 处理企业的情况 1、有没有不可能出现的指标 2、出现的指标能不能全部覆盖
                            for (String commonElement : commonElements) {
                                if (commonElement.equals(Subsidiary.GAC_HYPER.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_HYPER));
                                }
                                if (commonElement.equals(Subsidiary.GAC_AION.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_AION));
                                }
                                if (commonElement.equals(Subsidiary.GAC_TRUMPCHI.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_TRUMPCHI));
                                }
                                if (commonElement.equals(Subsidiary.GAC_HONDA.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_HONDA));
                                }
                                if (commonElement.equals(Subsidiary.GAC_TOYOTA.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_TOYOTA));
                                }
                                if (commonElement.equals(Subsidiary.GAC_INTL.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_INTL));
                                }
                                if (commonElement.equals(Subsidiary.GAC_LEADWAY.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_LEADWAY));
                                }
                                if (commonElement.equals(Subsidiary.GAC_GROUP.getChineseName())) {
                                    zbAllSet.addAll(Subsidiary.getSubsidiaryMetrics(Subsidiary.GAC_GROUP));
                                }
                            }
                            // 获取分支中的指标元素与企业可用指标元素的-共同元素（如果可以覆盖全部，则表示所有指标均为有效指标）
                            List<String> gtzb = zbcollect.stream()
                                    .filter(zbAllSet::contains)
                                    .collect(Collectors.toList());
                            // 如果分词指标集合数量不等于 共同元素数量
                            if(gtzb == null && gtzb.size() == 0){
                                long endqxjy = (System.currentTimeMillis() - startqxjy);
                                System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                aiHistoryEntity.setPermission("0");
                                aiHistoryEntity.setRemarks("用户提问有误【超出指标范围】-"+ gacRAGFlowAIRequestVO.toString());
                                int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                return AjaxResult.error(444,"超出知识库指标范围，请重新发问！");
                            }
                            // step2: 判断用户权限是否可以
                            if(commonElements.size() > 1){
                                // 多企业判断
                                Set<String> indicatorSets = new HashSet<>();
                                for (String commonElement : commonElements) {
                                    String tableName = Subsidiary.getTableNameByChineseName(commonElement);
                                    if(tableName != null){
                                        List<Map<String, Set<String>>> permission = permissionMap.getOrDefault(tableName, null);
                                        if(permission != null){
                                            //用户权限
                                            for (Map<String, Set<String>> stringSetMap : permission) {
                                                for (String key : stringSetMap.keySet()) {
                                                    Set<String> stringSet = stringSetMap.getOrDefault(key, null);
                                                    if(stringSet != null  && stringSet.size() > 0){
                                                        indicatorSets.addAll(stringSet);
                                                    }
                                                }
                                            }
                                        }else{
                                            long endqxjy = (System.currentTimeMillis() - startqxjy);
                                            System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                            aiHistoryEntity.setPermission("0");
                                            aiHistoryEntity.setRemarks("用户提问有误【企业权限不足】-"+ gacRAGFlowAIRequestVO.toString());
                                            int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                            return AjaxResult.error(444,"超出权限范围，请重新提问！");
                                        }
                                    }else{
                                        long endqxjy = (System.currentTimeMillis() - startqxjy);
                                        System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                        aiHistoryEntity.setPermission("0");
                                        aiHistoryEntity.setRemarks("用户提问有误【企业信息有误】-"+ gacRAGFlowAIRequestVO.toString());
                                        int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                        return AjaxResult.error(444,"问题输入有误，请先明确企业范围！");
                                    }
                                }
                                if(indicatorSets != null && indicatorSets.size() > 0){
                                    // 共同指标权限
                                    List<String> gtzbqx = zbcollect.stream()
                                            .filter(indicatorSets::contains)
                                            .collect(Collectors.toList());
                                    // 如果分词指标集合数量不等于 共同元素数量
                                    if(zbcollect.size() != gtzbqx.size()){
                                        List<String> expcollect = zbcollect.stream()
                                                .filter(item -> !indicatorSets.contains(item))
                                                .collect(Collectors.toList());
                                        //权限校验不通过
                                        long endqxjy = (System.currentTimeMillis() - startqxjy);
                                        System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                        aiHistoryEntity.setPermission("0");
                                        aiHistoryEntity.setRemarks("用户提问【超出权限范围】-"+ gacRAGFlowAIRequestVO.toString());
                                        int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                        return AjaxResult.error(444,"【"+expcollect.toString()+"】超出权限范围，请重新提问！");
                                    }else{
                                        // 权限校验通过
                                        long endqxjy = (System.currentTimeMillis() - startqxjy);
                                        System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                        System.out.println("---权限校验通过---");
                                        aiHistoryEntity.setPermission("1");
                                        int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                        if(insert > 0){
                                            return AjaxResult.success("权限校验通过", aiHistoryEntity);
                                        }else{
                                            log.error("Error-会话数据保存失败: " + aiHistoryEntity.toString());
                                            return AjaxResult.error(444,"请联系管理员检查校验服务！");
                                        }
                                    }
                                }else{
                                    //权限校验不通过
                                    long endqxjy = (System.currentTimeMillis() - startqxjy);
                                    System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                    aiHistoryEntity.setPermission("0");
                                    aiHistoryEntity.setRemarks("用户提问【超出权限范围】-"+ gacRAGFlowAIRequestVO.toString());
                                    int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                    return AjaxResult.error(444,"超出权限范围，请重新提问！");
                                }
                            }else{
                                //单企业判断
                                String qyName = commonElements.get(0);
                                String tableName = Subsidiary.getTableNameByChineseName(qyName);
                                if(tableName != null){
                                    List<Map<String, Set<String>>> permission = permissionMap.getOrDefault(tableName, null);
                                    if(permission != null){
                                        Set<String> qxAllSets = new HashSet<>();
                                        //用户权限
                                        for (Map<String, Set<String>> stringSetMap : permission) {
                                            for (String key : stringSetMap.keySet()) {
                                                Set<String> stringSet = stringSetMap.getOrDefault(key, null);
                                                if(stringSet != null && stringSet.size() > 0){
                                                    qxAllSets.addAll(stringSet);
                                                }
                                            }
                                        }
                                        if(qxAllSets != null && qxAllSets.size() > 0){
                                            //权限
                                            List<String> gtzbqx = zbcollect.stream()
                                                    .filter(qxAllSets::contains)
                                                    .collect(Collectors.toList());
                                            // 如果分词指标集合数量不等于 共同元素数量
                                            if(zbcollect.size() != gtzbqx.size()){
                                                List<String> expcollect = zbcollect.stream()
                                                        .filter(item -> !qxAllSets.contains(item))
                                                        .collect(Collectors.toList());
                                                //权限校验不通过
                                                long endqxjy = (System.currentTimeMillis() - startqxjy);
                                                System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                                aiHistoryEntity.setPermission("0");
                                                aiHistoryEntity.setRemarks("用户提问【超出权限范围】-"+ gacRAGFlowAIRequestVO.toString());
                                                int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                                return AjaxResult.error(444,"【"+expcollect.toString()+"】超出权限范围，请重新提问！");
                                            }else{
                                                // 权限校验通过
                                                long endqxjy = (System.currentTimeMillis() - startqxjy);
                                                System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                                System.out.println("---权限校验通过---");
                                                aiHistoryEntity.setPermission("1");
                                                int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                                if(insert > 0){
                                                    return AjaxResult.success("权限校验通过", aiHistoryEntity);
                                                }else{
                                                    log.error("Error-会话数据保存失败: " + aiHistoryEntity.toString());
                                                    return AjaxResult.error(444,"请联系管理员检查校验服务！");
                                                }
                                            }
                                        }else{
                                            long endqxjy = (System.currentTimeMillis() - startqxjy);
                                            System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                            aiHistoryEntity.setPermission("0");
                                            aiHistoryEntity.setRemarks("用户提问有误【指标权限不足】-"+ gacRAGFlowAIRequestVO.toString());
                                            int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                            return AjaxResult.error(444,"超出权限范围，请重新提问！");
                                        }
                                    }else{
                                        long endqxjy = (System.currentTimeMillis() - startqxjy);
                                        System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                        aiHistoryEntity.setPermission("0");
                                        aiHistoryEntity.setRemarks("用户提问有误【企业权限不足】-"+ gacRAGFlowAIRequestVO.toString());
                                        int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                        return AjaxResult.error(444,"超出权限范围，请重新提问！");
                                    }
                                }else{
                                    long endqxjy = (System.currentTimeMillis() - startqxjy);
                                    System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                    aiHistoryEntity.setPermission("0");
                                    aiHistoryEntity.setRemarks("用户提问有误【企业信息有误】-"+ gacRAGFlowAIRequestVO.toString());
                                    int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                    return AjaxResult.error(444,"问题输入有误，请先明确企业范围！");
                                }
                            }
                        }else{
                            long endqxjy = (System.currentTimeMillis() - startqxjy);
                            System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                            aiHistoryEntity.setPermission("0");
                            aiHistoryEntity.setRemarks("用户提问有误【无指标信息】-"+ gacRAGFlowAIRequestVO.toString());
                            int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                            return AjaxResult.error(444,"问题输入有误，请先明确指标信息！");
                        }
                    }else{
                        //无企业信息的情况下，再判定分词中是否包含特殊的“行业”指标
                        boolean containsIndustry = fenciList.contains("行业");
                        if(containsIndustry){
                            //全部放通
                            Set<String> qxAllSets = new HashSet<>();
                            for (String permission : permissionMap.keySet()) {
                                List<Map<String, Set<String>>> listMap = permissionMap.getOrDefault(permission, null);
                                if(listMap != null){
                                    //用户权限
                                    for (Map<String, Set<String>> stringSetMap : listMap) {
                                        for (String key : stringSetMap.keySet()) {
                                            Set<String> stringSet = stringSetMap.getOrDefault(key, null);
                                            if(stringSet != null  && stringSet.size() > 0){
                                                qxAllSets.addAll(stringSet);
                                            }
                                        }
                                    }
                                }
                            }
                            if(qxAllSets != null && qxAllSets.size() > 0 ){
                                boolean hasqx = qxAllSets.contains("行业");
                                if(hasqx){
                                    long endqxjy = (System.currentTimeMillis() - startqxjy);
                                    System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                    // 权限校验通过
                                    System.out.println("---权限校验通过---");
                                    aiHistoryEntity.setPermission("1");
                                    int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                    if(insert > 0){
                                        return AjaxResult.success("权限校验通过", aiHistoryEntity);
                                    }else{
                                        log.error("Error-会话数据保存失败: " + aiHistoryEntity.toString());
                                        return AjaxResult.error(444,"请联系管理员检查校验服务！");
                                    }
                                }else{
                                    aiHistoryEntity.setPermission("0");
                                    aiHistoryEntity.setRemarks("用户提问有误【无行业指标权限】-"+ gacRAGFlowAIRequestVO.toString());
                                    int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                    return AjaxResult.error(444,"请联系管理员获取授权，无行业指标权限！");
                                }
                            }else{
                                long endqxjy = (System.currentTimeMillis() - startqxjy);
                                System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                                aiHistoryEntity.setPermission("0");
                                String temp = "; token-" + accessToken + "; timestamp-" + timestamp + "; sourceId-" + sourceId;
                                aiHistoryEntity.setRemarks("行权限获取为空-"+ gacRAGFlowAIRequestVO.toString() + temp);
                                int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                                return AjaxResult.error(444,"请联系管理员获取授权-行权限！");
                            }
                        }else{
                            long endqxjy = (System.currentTimeMillis() - startqxjy);
                            System.out.println("用户权限校验耗时-"+ endqxjy + "ms");
                            aiHistoryEntity.setPermission("0");
                            aiHistoryEntity.setRemarks("用户提问有误【无企业信息】-"+ gacRAGFlowAIRequestVO.toString());
                            int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                            return AjaxResult.error(444,"问题输入有误，请先明确企业范围！");
                        }
                    }
                }else{
                    aiHistoryEntity.setPermission("0");
                    String temp = "; token-" + accessToken + "; timestamp-" + timestamp + "; sourceId-" + sourceId;
                    aiHistoryEntity.setRemarks("行权限获取为空-"+ gacRAGFlowAIRequestVO.toString() + temp);
                    int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                    return AjaxResult.error(444,"请联系管理员获取授权-行权限！");
                }
            }else{
                aiHistoryEntity.setPermission("0");
                String temp = "; token-" + accessToken + "; timestamp-" + timestamp + "; sourceId-" + sourceId;
                aiHistoryEntity.setRemarks("权限获取错误-"+ gacRAGFlowAIRequestVO.toString() + temp);
                int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                return AjaxResult.error(444,"请联系管理员获取授权/权限获取失败！");
            }
        }catch (Exception e){
            aiHistoryEntity.setPermission("0");
            aiHistoryEntity.setRemarks("分词及权限校验错误-"+ e.getMessage());
            int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
            return AjaxResult.error(444,"请联系管理员检查服务！");
        }
    }

}
