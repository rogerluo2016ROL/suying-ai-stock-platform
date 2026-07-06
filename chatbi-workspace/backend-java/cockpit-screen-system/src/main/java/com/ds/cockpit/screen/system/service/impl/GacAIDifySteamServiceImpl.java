package com.ds.cockpit.screen.system.service.impl;

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
import com.ds.cockpit.screen.common.core.domain.entity.AiFlowNodeEntity;
import com.ds.cockpit.screen.common.core.domain.entity.AiHistoryEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.AiFeedbackRequestVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.AiHistoryAnswerNodeVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.ai.GacDifyData;
import com.ds.cockpit.screen.common.core.domain.entity.vo.ai.GacRAGFlowAIRequestVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.dataperm.ColumnValue;
import com.ds.cockpit.screen.common.core.domain.entity.vo.dataperm.DataSourcePerms;
import com.ds.cockpit.screen.common.core.domain.entity.vo.dataperm.DataTablePerm;
import com.ds.cockpit.screen.common.core.domain.entity.vo.dataperm.RowPerm;
import com.ds.cockpit.screen.common.utils.StringUtils;
import com.ds.cockpit.screen.system.mapper.AiAgentTypeMapper;
import com.ds.cockpit.screen.system.mapper.AiFeedbackEnumMapper;
import com.ds.cockpit.screen.system.mapper.AiFlowNodeMapper;
import com.ds.cockpit.screen.system.mapper.AiHistoryMapper;
import com.ds.cockpit.screen.system.service.GacAIDifySteamService;
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
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * @Author: ZhouHong
 * @Date: 2025-05-08 下午 02:59
 */
@Slf4j
@Service
public class GacAIDifySteamServiceImpl implements GacAIDifySteamService {

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

    @Resource
    private AiFlowNodeMapper aiFlowNodeMapper;

    @Override
    public AjaxResult feedback(AiFeedbackRequestVO aiFeedbackRequestVO) {
        log.info("用户问题针对性反馈/意见收集");
        AiHistoryEntity aiHistoryEntity = aiHistoryMapper.selectById(aiFeedbackRequestVO.getId());
        if(aiHistoryEntity == null){
            log.info("用户问题标识符有误或不存在！");
            return AjaxResult.error("标识符有误或不存在！");
        }
        aiHistoryEntity.setQuestionFeedback(aiFeedbackRequestVO.getQuestionFeedback());
        aiHistoryEntity.setAnswerFeedback(aiFeedbackRequestVO.getAnswerFeedback());
        aiHistoryEntity.setOpinionFeedback(aiFeedbackRequestVO.getOpinionFeedback());
        aiHistoryEntity.setUpdateTime(LocalDateTime.now());
        log.info("用户问题针对性反馈/意见收集——保存更新");
        int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
        if(insert > 0){
            return AjaxResult.success();
        }else{
            log.info("Error-会话数据保存失败: " + aiHistoryEntity.toString());
            return AjaxResult.error("服务异常，请核查！");
        }
    }

    @Override
    public AjaxResult feedbackEnumQ() {
        log.info("用户问题针对性反馈/意见收集——枚举-问题");
        List<String> listQ= aiFeedbackEnumMapper.getFeedbackEnumQ();
        if(CollectionUtils.isNotEmpty(listQ)){
            return AjaxResult.success(listQ);
        }else{
            return AjaxResult.error();
        }
    }

    @Override
    public AjaxResult feedbackEnumA() {
        log.info("用户问题针对性反馈/意见收集——枚举-回答");
        List<String> listA= aiFeedbackEnumMapper.getFeedbackEnumA();
        if(CollectionUtils.isNotEmpty(listA)){
            return AjaxResult.success(listA);
        }else{
            return AjaxResult.error();
        }
    }

    @Override
    public List<Map<String, Object>> keywordTop() {
        log.info("AI首页top5 热门词汇");
        return aiHistoryMapper.getKeyWordTOP();
    }

    @Override
    public List<Map<String, Object>> questionTop() {
        log.info("AI首页top5 热门话题 question");
        return aiHistoryMapper.getQuestionTop();
    }

    @Override
    public List<Map<String, Object>> questionKeyTop(String question) {
        log.info("AI提问-问题提醒 question");
        return aiHistoryMapper.getQuestionKeyTop(question);
    }

    // 获取问题分词
    public String getQuestionSplitWords(GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO, AiHistoryEntity aiHistoryEntity) {
        log.info("开始分词处理");
        List<AiAgentType> agentTypeFenci = aiAgentTypeMapper.getAgentTypeFenci();
        AiAgentType aiAgentType = agentTypeFenci.get(0);
        String url_messages = aiAgentType.getPathValue();

        Map<String, Object> bodyParam = new HashMap<>();
        Map<String, Object> inputs = new HashMap<>();
        inputs.put("question",gacRAGFlowAIRequestVO.getQuestion());
        bodyParam.put("inputs",inputs);
        //bodyParam.put("conversation_id", aiHistoryEntity.getFenciSessionId());
        bodyParam.put("response_mode", "blocking");
        bodyParam.put("user", gacRAGFlowAIRequestVO.getUserId());

        String authorization = "Bearer " + aiAgentType.getAgentKey();
        aiHistoryEntity.setFenciAgentId(authorization);
        log.info("分词请求参数获取正确，开始实际请求啦！");
        HttpResponse execute = HttpRequest.post(url_messages)
                .header(Header.AUTHORIZATION, authorization)
                .header(Header.CONTENT_TYPE, "application/json")
                .body(JSON.toJSONString(bodyParam))
                .execute();
        log.info("分词请求返回——" + execute.toString());
        int status = execute.getStatus();
        log.info("分词请求返回——status——" + status);
        String body = execute.body();
        log.info("分词请求返回——body——" + body);
        if(200 == status){
            log.info("分词请求正常返回body");
            // 由于分词采用工作流没有上下文，需考虑优化后再处理
            // aiHistoryEntity.setAgentId(authorization);
            return body;
        }else{
            log.info("分词请求异常返回null");
            return null;
        }
    }


    //获取用户数据权限(行权限)
    protected List<DataSourcePerms> getUserDataPerm(String accessToken, String timestamp, Long sourceId){
        log.info("开始请求用户行权限");
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
        log.info("返回用户行权限");
        return dataSourcePermsList;
    }

    @Override
    public AjaxResult createdDataUuid(GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO) {
        log.info("新开启一个问题（新构建一个问题的唯一标识）");
        AiHistoryEntity aiHistoryEntity = new AiHistoryEntity();
        aiHistoryEntity.setQuestion(gacRAGFlowAIRequestVO.getQuestion());
        aiHistoryEntity.setUserId(gacRAGFlowAIRequestVO.getUserId());
        aiHistoryEntity.setUserName(gacRAGFlowAIRequestVO.getUserName());
        aiHistoryEntity.setSessionUuid(gacRAGFlowAIRequestVO.getSessionUuid());
        int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
        if(insert > 0){
            return AjaxResult.success(aiHistoryEntity);
        } else{
            log.info("新构建一个问题的唯一标识--ERROR--服务异常，请联系管理员！");
            return AjaxResult.error("服务异常，请联系管理员！");
        }

    }

    @Override
    public List<AiHistoryAnswerNodeVO> getAIAnswerNode(String startTime, String endTime){
        List<AiHistoryAnswerNodeVO> data = new ArrayList();
        List<AiHistoryEntity> aiHistoryEntityList = aiHistoryMapper.getAIAnswerNode(startTime, endTime);
        if(CollectionUtils.isNotEmpty(aiHistoryEntityList)){
            for (AiHistoryEntity aiHistoryEntity : aiHistoryEntityList) {
                AiHistoryAnswerNodeVO aiHistoryAnswerNodeVO = new AiHistoryAnswerNodeVO();
                aiHistoryAnswerNodeVO.setId(aiHistoryEntity.getId());
                aiHistoryAnswerNodeVO.setUserId(aiHistoryEntity.getUserId());
                aiHistoryAnswerNodeVO.setUserName(aiHistoryEntity.getUserName());
                aiHistoryAnswerNodeVO.setQuestion(aiHistoryEntity.getQuestion());
                aiHistoryAnswerNodeVO.setAnswerTime(aiHistoryEntity.getAnswerTime());
                aiHistoryAnswerNodeVO.setCreateTime(aiHistoryEntity.getCreateTime());
                aiHistoryAnswerNodeVO.setUpdateTime(aiHistoryEntity.getUpdateTime());

                String answer = aiHistoryEntity.getAnswer();
                StringBuffer answerFormt = new StringBuffer();
                if(StringUtils.isNotNull(answer) && !answer.startsWith("您的需求")){
                    if (StringUtils.isNotNull(answer)) {
                        List<GacDifyData> gacDifyData = JSON.parseArray(answer, GacDifyData.class);
                        if(CollectionUtils.isNotEmpty(gacDifyData)){
                            for (GacDifyData gacDifyDatum : gacDifyData) {
                                String node = gacDifyDatum.getNode();
                                String times = gacDifyDatum.getTimes();
                                if(StringUtils.isNotNull(node)){
                                    if(node.contains("问题识别")){
                                        aiHistoryAnswerNodeVO.setNodeProblemIdentification(times);
                                    }else
                                    if(node.contains("知识检索")){
                                        aiHistoryAnswerNodeVO.setNodeKnowledgeRetrieval(times);
                                    }else
                                    if(node.contains("关键数据检索")){
                                        aiHistoryAnswerNodeVO.setNodeAISQL(times);
                                    }else
                                    if(node.contains("数据获取")){
                                        aiHistoryAnswerNodeVO.setNodeDataAcquisition(times);
                                    }else
                                    if(node.contains("重复关键数据检索")){
                                        aiHistoryAnswerNodeVO.setNodeAISQL2(times);
                                    }else
                                    if(node.contains("重复数据获取")){
                                        aiHistoryAnswerNodeVO.setNodeDataAcquisition2(times);
                                    }else
                                    if(node.contains("数据口径说明")){
                                        aiHistoryAnswerNodeVO.setNodeDataCaliber(times);
                                    }else
                                    if(node.contains("数据解读")){
                                        aiHistoryAnswerNodeVO.setNodeDataInterpretation(times);
                                    }else
                                    if(node.contains("生成完成")){
                                        aiHistoryAnswerNodeVO.setNodeEnd(times);
                                    }
                                }else{
                                    String types = gacDifyDatum.getType();
                                    String message = gacDifyDatum.getMessage();
                                    if("message".equalsIgnoreCase(types) && StringUtils.isNotNull(message)){
                                        answerFormt.append(message);
                                    }
                                }


                            }
                        }
                    }
                }
                aiHistoryAnswerNodeVO.setAnswer(answerFormt.toString());
                data.add(aiHistoryAnswerNodeVO);
            }
        }
        return data;
    }

    @Override
    public Flux<AjaxResult> messagesQuestionWithAIStream(GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO) {
        log.info("开始AI提问——" + gacRAGFlowAIRequestVO.getQuestion());
        AiHistoryEntity aiHistoryEntity = aiHistoryMapper.selectById(gacRAGFlowAIRequestVO.getId());
        PreconditionsUtils.checkNotNull(aiHistoryEntity, "标识归属数据不能为空");
        long start = System.currentTimeMillis();
        List<GacDifyData> items = new ArrayList<>();
        List<String> datasList = new ArrayList<>();
        Map<String,Long> times = new LinkedHashMap<>();
        try {
            // step1 ：先得获取提问所需的会话id-实际提问
            log.info("AI提问——确认是否需要携带会话ID");
            AiAgentType aiAgentType = aiAgentTypeMapper.getAgentTypeQAById(gacRAGFlowAIRequestVO.getAgentId());
            log.info("AI提问——aiAgent——" + aiAgentType.getTitle() + "——" + aiAgentType.getAgentId());
            AiHistoryEntity entity = new AiHistoryEntity();
            entity.setSessionUuid(aiHistoryEntity.getSessionUuid());
            List<AiHistoryEntity> aiHistoryList = aiHistoryMapper.getAiHistoryList(entity);
            if(CollectionUtils.isNotEmpty(aiHistoryList)){
                List<AiHistoryEntity> collect = aiHistoryList.stream()
                        .filter(e -> StringUtils.isNotEmpty(e.getConversationId()))
                        .filter(e -> StringUtils.isNotEmpty(e.getAgentId()) && ("Bearer " + aiAgentType.getAgentKey()).equals(e.getAgentId()))
                        .collect(Collectors.toList());
                if(CollectionUtils.isNotEmpty(collect)){
                    String conversationId = aiHistoryList.get(0).getConversationId();
                    log.info("AI提问——确认携带会话ID——" + conversationId);
                    aiHistoryEntity.setConversationId(conversationId);
                }
            }
            // 对问题进行实际提问
            log.info("开始获取提问结果");
            // step3 : 实际提问
            String url_completions = aiAgentType.getPathValue();

            Map<String, Object> bodyParam = new HashMap<>();
            bodyParam.put("inputs", new HashMap<>());
            bodyParam.put("query", gacRAGFlowAIRequestVO.getQuestion());
            bodyParam.put("response_mode", "streaming");
            bodyParam.put("conversation_id", aiHistoryEntity.getConversationId());
            bodyParam.put("user", gacRAGFlowAIRequestVO.getUserId());
            aiHistoryEntity.setActualQuestion(gacRAGFlowAIRequestVO.getQuestion());

            String authorization = "Bearer " + aiAgentType.getAgentKey();
            aiHistoryEntity.setAgentId(authorization);
            aiHistoryEntity.setAgentName(aiAgentType.getTitle());
            log.info("提问参数设置正确，开始流式请求，获取提问结果");
            // 发送流式 POST 请求
            Flux<String> responseStream = HttpClientConfigNew.createWebClient().post()
                    .uri(url_completions)
                    .contentType(MediaType.APPLICATION_JSON)
                    .header(Header.AUTHORIZATION.getValue(), authorization)
                    .accept(MediaType.TEXT_EVENT_STREAM)
                    .bodyValue(JSON.toJSONString(bodyParam))
                    .retrieve()
                    .bodyToFlux(String.class);
            // StringBuffer sb = new StringBuffer();
            List<AiFlowNodeEntity> aiFlowNodeList = aiFlowNodeMapper.getAiFlowNodeList();
            List<String> nodeList = aiFlowNodeList.stream().map(AiFlowNodeEntity::getNodeName).collect(Collectors.toList());
            Map<String, String> nodeMap = new LinkedHashMap<>();
            for (AiFlowNodeEntity aiFlowNodeEntity : aiFlowNodeList) {
                nodeMap.put(aiFlowNodeEntity.getNodeName(),aiFlowNodeEntity.getNickName());
            }
            return responseStream.map(chunk -> {
                if(StringUtils.isNotEmpty(chunk)){
                    //log.info(items.size());
                    log.info(items.size() + " --- " + chunk);
                    datasList.add(chunk);
                    JSONObject jsonChunk = JSONObject.parseObject(chunk);
                    String event = (String)jsonChunk.getOrDefault("event", "");
                    if(StringUtils.isNotEmpty(event)){
                        Integer status = (Integer)jsonChunk.getOrDefault("status", 0);
                        if(status == 400){
                            log.info("提问反馈检测到异常返回——400，开始输出异常信息");
                            String message = (String)jsonChunk.getOrDefault("message", "");
                            log.info(message);
                            // return AjaxResult.error(status,message);
                            return AjaxResult.error(status,"服务异常，请重新提问！");
                        }else{
                            if(event.equals("workflow_started")){
                                log.info("工作流开始啦！");
                            }
                            if(event.equals("workflow_started")){
                                log.info("工作流结束啦！");
                            }
                            if(event.equals("message_end")){
                                GacDifyData gacDifyData = new GacDifyData();
                                gacDifyData.setType("message_end");
                                Long seconds = (System.currentTimeMillis() - start);
                                if(seconds < 1000 ){
                                    gacDifyData.setTimes(seconds + "ms");
                                }else{
                                    double result = (double)seconds / 1000;
                                    gacDifyData.setTimes(result + "s");
                                }
                                log.info("AI回答结束啦！");
                                return AjaxResult.success(gacDifyData);
                            }
                            // 可以继续解析节点的
                            // event == node_started\node_finished\message
                            if(event.equals("node_started")){
                                Object data = jsonChunk.getOrDefault("data", null);
                                if(data != null){
                                    GacDifyData gacDifyData = new GacDifyData();
                                    gacDifyData.setType("node_started");
                                    JSONObject jsonData = JSONObject.parseObject(data.toString());
                                    String title = (String)jsonData.getOrDefault("title", "");
                                    String conversationId = (String)jsonChunk.getOrDefault("conversation_id", "");
                                    aiHistoryEntity.setConversationId(conversationId);
                                    if(StringUtils.isNotEmpty(title)){
                                        long starts = System.currentTimeMillis();
                                        times.put("node_started_" + title, starts);
                                        String nick = nodeMap.getOrDefault(title, null);
                                        if(StringUtils.isNotEmpty(nick)){
                                            gacDifyData.setNode(nick);
                                        }else{
                                            gacDifyData.setNode(title);
                                        }
                                        boolean contains = nodeList.contains(title);
                                        if(contains){
                                            gacDifyData.setIsShow("1");
                                        }else{
                                            gacDifyData.setIsShow("0");
                                        }
                                        //String node = "<node>" + title + "</node>";
                                        items.add(gacDifyData);
                                        log.info("node_started——" + title);
                                        return AjaxResult.success(gacDifyData);
                                    }else{
                                        return AjaxResult.success("");
                                    }
                                }else{
                                    return AjaxResult.success("");
                                }

                            }
                            if(event.equals("node_finished")){
                                Object data = jsonChunk.getOrDefault("data", null);
                                if(data != null){
                                    GacDifyData gacDifyData = new GacDifyData();
                                    gacDifyData.setType("node_finished");
                                    JSONObject jsonData = JSONObject.parseObject(data.toString());
                                    String title = (String)jsonData.getOrDefault("title", "");
                                    String conversationId = (String)jsonChunk.getOrDefault("conversation_id", "");
                                    aiHistoryEntity.setConversationId(conversationId);
                                    if(StringUtils.isNotEmpty(title)){
                                        String nick = nodeMap.getOrDefault(title, null);
                                        if(StringUtils.isNotEmpty(nick)){
                                            gacDifyData.setNode(nick);
                                        }else{
                                            gacDifyData.setNode(title);
                                        }
                                        boolean contains = nodeList.contains(title);
                                        if(contains){
                                            gacDifyData.setIsShow("1");
                                        }else{
                                            gacDifyData.setIsShow("0");
                                        }
                                        //String node = "<node>" + title + "</node>";
                                        Long node_started_time = times.getOrDefault("node_started_" + title, null);
                                        if(node_started_time != null){
                                            //计算时间
                                            Long seconds = (System.currentTimeMillis() - node_started_time);
                                            if(seconds < 1000 ){
                                                gacDifyData.setTimes(seconds + "ms");
                                            }else{
                                                double result = (double)seconds / 1000;
                                                gacDifyData.setTimes(result + "s");
                                            }
                                        }
                                        items.add(gacDifyData);
                                        log.info(gacDifyData.toString());
                                        return AjaxResult.success(gacDifyData);
                                    }else{
                                        return AjaxResult.success("");
                                    }
                                }else{
                                    return AjaxResult.success("");
                                }

                            }
                            if(event.equals("message")){
                                GacDifyData gacDifyData = new GacDifyData();
                                gacDifyData.setType("message");
                                String answer = (String)jsonChunk.getOrDefault("answer", "");
                                String conversationId = (String)jsonChunk.getOrDefault("conversation_id", "");
                                aiHistoryEntity.setConversationId(conversationId);
                                gacDifyData.setMessage(answer);
                                items.add(gacDifyData);
                                log.info("提问反馈实际文本信息输出：");
                                log.info(answer);
                                return AjaxResult.success(gacDifyData);
                            }
                            return AjaxResult.success("");
                        }
                    }else{
                        log.info("流式数据返回输出格式有误或为空");
                        return AjaxResult.error("数据格式有误");
                    }
                }else{
                    log.info("流式数据返回为空");
                    return AjaxResult.success("");
                }
            })
            .doOnTerminate(() ->{
                log.info("流式请求结束，保存更新返回结果");
                aiHistoryEntity.setAnswer(JSONObject.toJSONString(items));
                aiHistoryEntity.setAnswerAll(JSONObject.toJSONString(datasList));
                Double seconds = (double)(System.currentTimeMillis() - start) / 1000;
                aiHistoryEntity.setAnswerTime(seconds + "s");
                aiHistoryEntity.setUpdateTime(LocalDateTime.now());
                int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
            })
            .doOnError(e -> {
                log.info("流式请求【异常】结束，保存更新返回结果");
                aiHistoryEntity.setAnswer(JSONObject.toJSONString(items));
                aiHistoryEntity.setAnswerAll(JSONObject.toJSONString(datasList));
                Double seconds = (double)(System.currentTimeMillis() - start) / 1000;
                aiHistoryEntity.setAnswerTime(seconds + "s");
                aiHistoryEntity.setUpdateTime(LocalDateTime.now());
                aiHistoryEntity.setDescriptions("AI提问出错-"+e.getMessage());
                int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                System.err.println("Error: " + e.getMessage());
                AjaxResult.error("Error: " + e.getMessage());
            }).doFinally(e ->{
                log.info("流式请求doFinally，保存更新返回结果");
                log.info("流式请求doFinally" + e.toString());
                aiHistoryEntity.setAnswer(JSONObject.toJSONString(items));
                aiHistoryEntity.setAnswerAll(JSONObject.toJSONString(datasList));
                Double seconds = (double)(System.currentTimeMillis() - start) / 1000;
                aiHistoryEntity.setAnswerTime(seconds + "s");
                aiHistoryEntity.setUpdateTime(LocalDateTime.now());
                aiHistoryEntity.setFenciSessionId("AI提问记录-"+e.toString());
                int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
            })
            .onErrorReturn(AjaxResult.error("系统服务繁忙，请重新提问"));
        }catch (Exception e){
            log.info("AI提问程序异常——" + e.getMessage());
            log.info(e.toString());
            aiHistoryEntity.setAnswer(JSONObject.toJSONString(items));
            aiHistoryEntity.setAnswerAll(JSONObject.toJSONString(datasList));
            Double seconds = (double)(System.currentTimeMillis() - start) / 1000;
            aiHistoryEntity.setAnswerTime(seconds + "s");
            aiHistoryEntity.setUpdateTime(LocalDateTime.now());
            aiHistoryEntity.setDescriptions("AI提问错误-"+e.getMessage());
            int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
            return Flux.just(AjaxResult.error("AI提问出错-系统错误！"));
        }
    }

    @Override
    public Flux<AjaxResult> messagesQuestionWithAIStreamPermission(GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO) {
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
                log.info("获取提问结果");

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
                    log.info(items.size() + "");
                    log.info(chunk);
                    datasList.add(chunk);
                    JSONObject jsonChunk = JSONObject.parseObject(chunk);
                    String answer = (String)jsonChunk.getOrDefault("answer", "");
                    String conversationId = (String)jsonChunk.getOrDefault("conversation_id", "");
                    aiHistoryEntity.setConversationId(conversationId);
                    items.add(answer);
                    log.info(answer);
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
                log.info("获取提问结果");

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
                    log.info(items.size() + "");
                    log.info(chunk);
                    datasList.add(chunk);
                    JSONObject jsonChunk = JSONObject.parseObject(chunk);
                    String answer = (String)jsonChunk.getOrDefault("answer", "");
                    items.add(answer);
                    log.info(answer);
                    return AjaxResult.success(answer);
                })
                        .doOnTerminate(() ->{
                            aiHistoryEntity.setAnswer(String.join("",items));
                            aiHistoryEntity.setAnswerAll(String.join("\\n",datasList));
                            Long seconds = (System.currentTimeMillis() - start) / 1000;
                            aiHistoryEntity.setAnswerTime(seconds + "s");
                            aiHistoryEntity.setUpdateTime(LocalDateTime.now());
                            log.info(aiHistoryEntity.toString());
                        })
                        .doOnError(e -> {
                            aiHistoryEntity.setDescriptions("AI提问错误-"+e.getMessage());
                            log.info(aiHistoryEntity.toString());
                            System.err.println("Error: " + e.getMessage());
                            AjaxResult.error("Error: " + e.getMessage());
                        })
                        .onErrorReturn(AjaxResult.error("系统服务繁忙，请重新提问"));
            }else{
                aiHistoryEntity.setDescriptions("AI提问错误-未通过权限校验！");
                log.info(aiHistoryEntity.toString());
                return Flux.just(AjaxResult.error("AI提问错误-未通过权限校验！"));
            }
        }catch (Exception e){
            aiHistoryEntity.setDescriptions("AI提问错误-"+e.getMessage());
            log.info(aiHistoryEntity.toString());
            return Flux.just(AjaxResult.error("AI提问错误-系统错误！"));
        }
    }

    @Override
    public AjaxResult splitWordsAndPermissionChat(HttpServletRequest request,  GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO){
        // 需要先查询，为了保持分词的上下文，还应该查询会话id
        AiHistoryEntity aiHistoryEntity = aiHistoryMapper.selectById(gacRAGFlowAIRequestVO.getId());
        if(aiHistoryEntity == null){
            return AjaxResult.error("请确认服务状态及数据唯一标识！");
        }
        try {
            // 待处理 是否修改为新问题
            aiHistoryEntity.setQuestion(gacRAGFlowAIRequestVO.getQuestion());
            aiHistoryEntity.setUserId(gacRAGFlowAIRequestVO.getUserId());
            aiHistoryEntity.setUserName(gacRAGFlowAIRequestVO.getUserName());
            aiHistoryEntity.setSessionUuid(gacRAGFlowAIRequestVO.getSessionUuid());

            AiHistoryEntity query = new AiHistoryEntity();
            query.setSessionUuid(gacRAGFlowAIRequestVO.getSessionUuid());
            List<AiHistoryEntity> aiHistoryList = aiHistoryMapper.getAiHistoryList(query);
            String fenciSessionId = "";
            if(CollectionUtils.isNotEmpty(aiHistoryList)){
                Set<String> set = aiHistoryList.stream().
                        filter(e -> StringUtils.isNotEmpty(e.getFenciSessionId()))
                        .map(AiHistoryEntity::getFenciSessionId)
                        .collect(Collectors.toSet());
                if(CollectionUtils.isNotEmpty(set)){
                    if(set.size() == 1){
                        List<String> list = new ArrayList<>(set);
                        fenciSessionId = list.get(0);
                        aiHistoryEntity.setFenciSessionId(fenciSessionId);
                    }
                }
            }
            // step1 ：开启会话-实际分词
                // 实际分词与结果
                log.info("获取分词结果");
                long startfc = System.currentTimeMillis();
                String fenci =  this.getQuestionSplitWords(gacRAGFlowAIRequestVO, aiHistoryEntity);
                long endfc = (System.currentTimeMillis() - startfc);
                log.info("ai分词耗时-"+ endfc + "ms");
                String fenciNew = null;
                if(StringUtils.isNotEmpty(fenci)){
                    Set<String> fc = new HashSet<>();
                    String temp = fenci.replaceAll("，", ",");
                    fenciNew = temp.replaceAll("[\\t\\n]", "");
                    log.info(gacRAGFlowAIRequestVO.getQuestion());
                    log.info(fenciNew);
                    Map bodyMap = JSONObject.parseObject(fenciNew, Map.class);
                    Object data = bodyMap.getOrDefault("data",null);
                    if(data != null){
                        Map dataMap = JSONObject.parseObject(data.toString(), Map.class);
                        Object outputs = dataMap.getOrDefault("outputs", null);
                        if(outputs != null){
                            Map outputsMap = JSONObject.parseObject(outputs.toString(), Map.class);
                            Object result = outputsMap.getOrDefault("data", null);
                            log.info(result.toString());
                            if(result != null){
                                Map resultMap = JSONObject.parseObject(result.toString(), Map.class);
                                String pinpai = (String)resultMap.getOrDefault("品牌标签", null);
                                String zhibiao = (String)resultMap.getOrDefault("指标标签", null);
                                log.info(pinpai);
                                log.info(zhibiao);
                                if(pinpai != null){
                                    fc.add(pinpai);
                                }
                                if(zhibiao != null){
                                    fc.add(zhibiao);
                                }
                            }
                        }
                    }
                    if(fc.size() > 0){
                        String fcStr = String.join(",", fc);
                        aiHistoryEntity.setSplitWords(fenciNew);
                    }
                    log.info(gacRAGFlowAIRequestVO.getQuestion());
                    aiHistoryEntity.setFenciAgentName(fenci);
                    int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                }else{
                    aiHistoryEntity.setPermission("0");
                    aiHistoryEntity.setRemarks("AI分词错误-"+ gacRAGFlowAIRequestVO.toString());
                    int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                    return AjaxResult.error(444,"请联系管理员检查AI分词服务！");
                }

            // step2 : 权限关键词拦截
            // 先获取指定用户的权限（调用新平台管家数据权限接口-行权限）
            String accessToken = request.getHeader("Authorization");
            String timestamp= request.getHeader("Timestamp");
            log.info("获取用户权限");
            long startqx = System.currentTimeMillis();
            List<DataSourcePerms> dataSourcePermsList = this.getUserDataPerm(accessToken, timestamp, sourceId);
            long endqx = (System.currentTimeMillis() - startqx);
            log.info("用户权限获取及解析耗时-"+ endqx + "ms");
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
                    log.info("用户权限校验");
                    long startqxjy = System.currentTimeMillis();
                    String[] fenciSplit = fenciNew.split("\\s*,\\s*");
                    List<String> fenciList = Arrays.asList(fenciSplit);
                    //step1、先判断分词中是否包含企业，再通过企业判断后续字段与逻辑
                    // 判断是否包含任意元素
                    List<String> qyList = Subsidiary.getAllChineseNames();
                    boolean containsAny = fenciList.stream().anyMatch(qyList::contains);
                    //log.info("是否包含任意元素: " + containsAny);
                    if(containsAny){
                        // 获取共同元素（企业名称）
                        List<String> commonElements = fenciList.stream()
                                .filter(qyList::contains)
                                .collect(Collectors.toList());
                        // 获取剩余元素（分词中的指标）
                        List<String> zbcollect = fenciList.stream()
                                .filter(item -> !commonElements.contains(item))
                                .collect(Collectors.toList());
                        //log.info("共同元素: " + commonElements);
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
                                log.info("用户权限校验耗时-"+ endqxjy + "ms");
                                aiHistoryEntity.setPermission("0");
                                aiHistoryEntity.setRemarks("用户提问有误【超出指标范围】-"+ gacRAGFlowAIRequestVO.toString());
                                int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
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
                                            log.info("用户权限校验耗时-"+ endqxjy + "ms");
                                            aiHistoryEntity.setPermission("0");
                                            aiHistoryEntity.setRemarks("用户提问有误【企业权限不足】-"+ gacRAGFlowAIRequestVO.toString());
                                            int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                                            return AjaxResult.error(444,"超出权限范围，请重新提问！");
                                        }
                                    }else{
                                        long endqxjy = (System.currentTimeMillis() - startqxjy);
                                        log.info("用户权限校验耗时-"+ endqxjy + "ms");
                                        aiHistoryEntity.setPermission("0");
                                        aiHistoryEntity.setRemarks("用户提问有误【企业信息有误】-"+ gacRAGFlowAIRequestVO.toString());
                                        int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
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
                                        log.info("用户权限校验耗时-"+ endqxjy + "ms");
                                        aiHistoryEntity.setPermission("0");
                                        aiHistoryEntity.setRemarks("用户提问【超出权限范围】-"+ gacRAGFlowAIRequestVO.toString());
                                        int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                                        return AjaxResult.error(444,"【"+expcollect.toString()+"】超出权限范围，请重新提问！");
                                    }else{
                                        // 权限校验通过
                                        long endqxjy = (System.currentTimeMillis() - startqxjy);
                                        log.info("用户权限校验耗时-"+ endqxjy + "ms");
                                        log.info("---权限校验通过---");
                                        aiHistoryEntity.setPermission("1");
                                        int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
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
                                    log.info("用户权限校验耗时-"+ endqxjy + "ms");
                                    aiHistoryEntity.setPermission("0");
                                    aiHistoryEntity.setRemarks("用户提问【超出权限范围】-"+ gacRAGFlowAIRequestVO.toString());
                                    int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
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
                                                log.info("用户权限校验耗时-"+ endqxjy + "ms");
                                                aiHistoryEntity.setPermission("0");
                                                aiHistoryEntity.setRemarks("用户提问【超出权限范围】-"+ gacRAGFlowAIRequestVO.toString());
                                                int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                                                return AjaxResult.error(444,"【"+expcollect.toString()+"】超出权限范围，请重新提问！");
                                            }else{
                                                // 权限校验通过
                                                long endqxjy = (System.currentTimeMillis() - startqxjy);
                                                log.info("用户权限校验耗时-"+ endqxjy + "ms");
                                                log.info("---权限校验通过---");
                                                aiHistoryEntity.setPermission("1");
                                                int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                                                if(insert > 0){
                                                    return AjaxResult.success("权限校验通过", aiHistoryEntity);
                                                }else{
                                                    log.error("Error-会话数据保存失败: " + aiHistoryEntity.toString());
                                                    return AjaxResult.error(444,"请联系管理员检查校验服务！");
                                                }
                                            }
                                        }else{
                                            long endqxjy = (System.currentTimeMillis() - startqxjy);
                                            log.info("用户权限校验耗时-"+ endqxjy + "ms");
                                            aiHistoryEntity.setPermission("0");
                                            aiHistoryEntity.setRemarks("用户提问有误【指标权限不足】-"+ gacRAGFlowAIRequestVO.toString());
                                            int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                                            return AjaxResult.error(444,"超出权限范围，请重新提问！");
                                        }
                                    }else{
                                        long endqxjy = (System.currentTimeMillis() - startqxjy);
                                        log.info("用户权限校验耗时-"+ endqxjy + "ms");
                                        aiHistoryEntity.setPermission("0");
                                        aiHistoryEntity.setRemarks("用户提问有误【企业权限不足】-"+ gacRAGFlowAIRequestVO.toString());
                                        int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                                        return AjaxResult.error(444,"超出权限范围，请重新提问！");
                                    }
                                }else{
                                    long endqxjy = (System.currentTimeMillis() - startqxjy);
                                    log.info("用户权限校验耗时-"+ endqxjy + "ms");
                                    aiHistoryEntity.setPermission("0");
                                    aiHistoryEntity.setRemarks("用户提问有误【企业信息有误】-"+ gacRAGFlowAIRequestVO.toString());
                                    int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                                    return AjaxResult.error(444,"问题输入有误，请先明确企业范围！");
                                }
                            }
                        }else{
                            long endqxjy = (System.currentTimeMillis() - startqxjy);
                            log.info("用户权限校验耗时-"+ endqxjy + "ms");
                            aiHistoryEntity.setPermission("0");
                            aiHistoryEntity.setRemarks("用户提问有误【无指标信息】-"+ gacRAGFlowAIRequestVO.toString());
                            int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
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
                                    log.info("用户权限校验耗时-"+ endqxjy + "ms");
                                    // 权限校验通过
                                    log.info("---权限校验通过---");
                                    aiHistoryEntity.setPermission("1");
                                    int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                                    if(insert > 0){
                                        return AjaxResult.success("权限校验通过", aiHistoryEntity);
                                    }else{
                                        log.error("Error-会话数据保存失败: " + aiHistoryEntity.toString());
                                        return AjaxResult.error(444,"请联系管理员检查校验服务！");
                                    }
                                }else{
                                    aiHistoryEntity.setPermission("0");
                                    aiHistoryEntity.setRemarks("用户提问有误【无行业指标权限】-"+ gacRAGFlowAIRequestVO.toString());
                                    int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                                    return AjaxResult.error(444,"请联系管理员获取授权，无行业指标权限！");
                                }
                            }else{
                                long endqxjy = (System.currentTimeMillis() - startqxjy);
                                log.info("用户权限校验耗时-"+ endqxjy + "ms");
                                aiHistoryEntity.setPermission("0");
                                String temp = "; token-" + accessToken + "; timestamp-" + timestamp + "; sourceId-" + sourceId;
                                aiHistoryEntity.setRemarks("行权限获取为空-"+ gacRAGFlowAIRequestVO.toString() + temp);
                                int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                                return AjaxResult.error(444,"请联系管理员获取授权-行权限！");
                            }
                        }else{
                            long endqxjy = (System.currentTimeMillis() - startqxjy);
                            log.info("用户权限校验耗时-"+ endqxjy + "ms");
                            aiHistoryEntity.setPermission("0");
                            aiHistoryEntity.setRemarks("用户提问有误【无企业信息】-"+ gacRAGFlowAIRequestVO.toString());
                            int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                            return AjaxResult.error(444,"问题输入有误，请先明确企业范围！");
                        }
                    }
                }else{
                    aiHistoryEntity.setPermission("0");
                    String temp = "; token-" + accessToken + "; timestamp-" + timestamp + "; sourceId-" + sourceId;
                    aiHistoryEntity.setRemarks("行权限获取为空-"+ gacRAGFlowAIRequestVO.toString() + temp);
                    int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                    return AjaxResult.error(444,"请联系管理员获取授权-行权限！");
                }
            }else{
                aiHistoryEntity.setPermission("0");
                String temp = "; token-" + accessToken + "; timestamp-" + timestamp + "; sourceId-" + sourceId;
                aiHistoryEntity.setRemarks("权限获取错误-"+ gacRAGFlowAIRequestVO.toString() + temp);
                int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                return AjaxResult.error(444,"请联系管理员获取授权/权限获取失败！");
            }
        }catch (Exception e){
            aiHistoryEntity.setPermission("0");
            aiHistoryEntity.setRemarks("分词及权限校验错误-"+ e.getMessage());
            int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
            return AjaxResult.error(444,"请联系管理员检查服务！");
        }
    }

    @Override
    public AjaxResult splitWordsByChat(HttpServletRequest request, GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO) {
        log.info("开始分词——"+ gacRAGFlowAIRequestVO.getQuestion());
        // 需要先查询，为了保持分词的上下文，还应该查询会话id
        AiHistoryEntity aiHistoryEntity = aiHistoryMapper.selectById(gacRAGFlowAIRequestVO.getId());
        if(aiHistoryEntity == null){
            log.info("分词处理错误——用户提问标识有误，查询无数据——" + gacRAGFlowAIRequestVO.getId());
            return AjaxResult.error("请确认服务状态及数据唯一标识！");
        }
        try {
            // 待处理 是否修改为新问题
            aiHistoryEntity.setQuestion(gacRAGFlowAIRequestVO.getQuestion());
            aiHistoryEntity.setUserId(gacRAGFlowAIRequestVO.getUserId());
            aiHistoryEntity.setUserName(gacRAGFlowAIRequestVO.getUserName());
            aiHistoryEntity.setSessionUuid(gacRAGFlowAIRequestVO.getSessionUuid());

            AiHistoryEntity query = new AiHistoryEntity();
            query.setSessionUuid(gacRAGFlowAIRequestVO.getSessionUuid());
            List<AiHistoryEntity> aiHistoryList = aiHistoryMapper.getAiHistoryList(query);
            String fenciSessionId = "";
            if(CollectionUtils.isNotEmpty(aiHistoryList)){
                Set<String> set = aiHistoryList.stream().
                        filter(e -> StringUtils.isNotEmpty(e.getFenciSessionId()))
                        .map(AiHistoryEntity::getFenciSessionId)
                        .collect(Collectors.toSet());
                if(CollectionUtils.isNotEmpty(set)){
                    if(set.size() == 1){
                        List<String> list = new ArrayList<>(set);
                        fenciSessionId = list.get(0);
                        aiHistoryEntity.setFenciSessionId(fenciSessionId);
                    }
                }
            }
            // step1 ：开启会话-实际分词
            // 实际分词与结果
            log.info("开始获取分词结果");
            long startfc = System.currentTimeMillis();
            String fenci =  this.getQuestionSplitWords(gacRAGFlowAIRequestVO, aiHistoryEntity);
            aiHistoryEntity.setFenciAgentName(fenci);
            long endfc = (System.currentTimeMillis() - startfc);
            log.info("分词结果——" + fenci);
            log.info("ai分词耗时-"+ endfc + "ms");
            if(StringUtils.isNotEmpty(fenci)){
                log.info("开始解析分词结果");
                Set<String> fc = new HashSet<>();
                String temp = fenci.replaceAll("，", ",");
                String fenciNew = temp.replaceAll("[\\t\\n]", "");
                log.info("分词格式化-" + fenciNew);
                Map bodyMap = JSONObject.parseObject(fenciNew, Map.class);
                Object data = bodyMap.getOrDefault("data",null);
                if(data != null){
                    Map dataMap = JSONObject.parseObject(data.toString(), Map.class);
                    Object outputs = dataMap.getOrDefault("outputs", null);
                    if(outputs != null){
                        Map outputsMap = JSONObject.parseObject(outputs.toString(), Map.class);
                        Object dataResult = outputsMap.getOrDefault("data", null);
                        if(dataResult != null){
                            Map dataResultMap = JSONObject.parseObject(dataResult.toString(), Map.class);
                            Object result = dataResultMap.getOrDefault("data", null);
                            log.info("分词解析后-" + result);
                            if(result != null){
                                Map resultMap = JSONObject.parseObject(result.toString(), Map.class);
                                String pinpai = (String)resultMap.getOrDefault("汽车品牌", null);
                                if(pinpai == null){
                                    pinpai = (String)resultMap.getOrDefault("品牌", null);
                                    if(pinpai == null){
                                        pinpai = (String)resultMap.getOrDefault("品牌标签", null);
                                    }
                                }
                                String zhibiao = (String)resultMap.getOrDefault("指标", null);
                                if(zhibiao == null){
                                    zhibiao = (String)resultMap.getOrDefault("指标标签", null);
                                }
                                log.info(pinpai);
                                log.info(zhibiao);
                                if(pinpai != null){
                                    fc.add(pinpai);
                                }
                                if(zhibiao != null){
                                    fc.add(zhibiao);
                                }
                            }
                        }
                    }
                }
                if(fc.size() > 0){
                    String fcStr = String.join(",", fc);
                    log.info("解析分词最终结果——" + fcStr);
                    aiHistoryEntity.setSplitWords(fcStr);
                }else{
                    log.info("解析分词出错——请检查分词内容与格式");
                }
                log.info(gacRAGFlowAIRequestVO.getQuestion());
                int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                return AjaxResult.success(aiHistoryEntity);
            }else{
                log.info("分词错误——空返回");
                aiHistoryEntity.setPermission("0");
                aiHistoryEntity.setRemarks("AI分词错误-"+ gacRAGFlowAIRequestVO.toString());
                int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                return AjaxResult.error(444,"请联系管理员检查AI分词服务！");
            }
        }catch (Exception e){
            log.info("分词错误——catch——返回");
            log.info("分词错误——catch——"+ e.getMessage());
            log.info(e.toString());
            aiHistoryEntity.setPermission("0");
            aiHistoryEntity.setRemarks("分词请求错误-"+ e.getMessage());
            int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
            return AjaxResult.error(444,"请联系管理员检查服务！");
        }
    }

    @Override
    public AjaxResult aiMonitor(HttpServletRequest request, GacRAGFlowAIRequestVO gacRAGFlowAIRequestVO) {
        log.info("开始Ai服务监控——"+ gacRAGFlowAIRequestVO.getQuestion());
        log.info("新开启一个问题（新构建一个问题的唯一标识）");
        AiHistoryEntity aiHistoryEntity = new AiHistoryEntity();
        aiHistoryEntity.setQuestion(gacRAGFlowAIRequestVO.getQuestion());
        aiHistoryEntity.setUserId(gacRAGFlowAIRequestVO.getUserId());
        aiHistoryEntity.setUserName(gacRAGFlowAIRequestVO.getUserName());
        aiHistoryEntity.setSessionUuid(gacRAGFlowAIRequestVO.getSessionUuid());
        int insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
        if(insert <= 0){
            log.info("新构建一个问题的唯一标识--ERROR--服务异常，请联系管理员！");
            return AjaxResult.error("服务异常，请联系管理员！");
        }
        try {
            // 非流式提问
            log.info("开始-Ai服务监控-非流式提问");
            AiAgentType aiAgentType = aiAgentTypeMapper.getAgentTypeMonitor();
            log.info("Ai服务监控——aiAgent——" + aiAgentType.getTitle() + "——" + aiAgentType.getAgentId());
            String url_completions = aiAgentType.getPathValue();
            // 参数设置
            Map<String, Object> bodyParam = new HashMap<>();
            bodyParam.put("inputs", new HashMap<>());
            bodyParam.put("query", gacRAGFlowAIRequestVO.getQuestion());
            bodyParam.put("response_mode", "blocking");
            bodyParam.put("user", gacRAGFlowAIRequestVO.getUserId());
            aiHistoryEntity.setActualQuestion(gacRAGFlowAIRequestVO.getQuestion());
            String authorization = "Bearer " + aiAgentType.getAgentKey();
            aiHistoryEntity.setAgentId(authorization);
            aiHistoryEntity.setAgentName(aiAgentType.getTitle());
            log.info("提问参数设置完成，开始流式请求，获取提问结果");
            long startfc = System.currentTimeMillis();
            HttpResponse execute = HttpRequest.post(url_completions)
                    .header(Header.AUTHORIZATION, authorization)
                    .header(Header.CONTENT_TYPE, "application/json")
                    .body(JSON.toJSONString(bodyParam))
                    .execute();
            log.info("Ai服务监控-非流式提问-请求返回——" + execute.toString());
            int status = execute.getStatus();
            log.info("Ai服务监控-非流式提问-请求返回——status——" + status);
            String body = execute.body();
            log.info("Ai服务监控-非流式提问-请求返回——body——" + body);
            long endfc = (System.currentTimeMillis() - startfc);
            aiHistoryEntity.setRemarks("Ai服务监控-非流式提问-耗时-"+ endfc + "ms");
            log.info("Ai服务监控-非流式提问耗时-"+ endfc + "ms");
            if(200 == status){
                log.info("Ai服务监控-非流式提问-请求正常返回body");
                aiHistoryEntity.setRemarks(body);
                Map bodyMap = JSONObject.parseObject(body, Map.class);
                String answer = (String)bodyMap.getOrDefault("answer",null);
                aiHistoryEntity.setAnswer(answer);
                if(null != aiHistoryEntity.getId()){
                    int up = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                }else{
                    insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                }
                return AjaxResult.success("提问成功",answer);
            }else{
                log.info("Ai服务监控-非流式提问-请求异常返回");
                if(null != aiHistoryEntity.getId()){
                    aiHistoryEntity.setRemarks("Ai服务监控-非流式提问-status-"+ status);
                    int up = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                }else{
                    insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
                }
                return AjaxResult.error("服务异常，请联系管理员！");
            }
        }catch (Exception e){
            log.info("Ai服务监控-非流式提问-异常");
            log.info("Ai服务监控-非流式提问——catch——"+ e.getMessage());
            log.info(e.toString());
            if(null != aiHistoryEntity.getId()){
                aiHistoryEntity.setRemarks("Ai服务监控-非流式提问-"+ e.getMessage());
                int up = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
            }else{
                insert = aiHistoryMapper.addHistoryRecord(aiHistoryEntity);
            }
            return AjaxResult.error(444,"请联系管理员检查服务！");
        }
    }


    @Override
    public void AISplitWordsRetryAnalysis() {

        // 需要先查询，所有
        List<AiHistoryEntity> entityList = aiHistoryMapper.getAiHistoryNotSplitWordsList();
        if(CollectionUtils.isEmpty(entityList)){
            log.info("无数据，无需补偿处理！");
            return ;
        }
        // step1 ：开启实际分词
        if(CollectionUtils.isEmpty(entityList)){
            log.info("无重新分词数据，无需补偿处理！");
            return ;
        }
        for (AiHistoryEntity aiHistoryEntity : entityList) {
            try {

                // 实际分词与结果
                log.info("获取分词结果");
                long startfc = System.currentTimeMillis();
                String fenci =  this.getQuestionSplitWordsRetry(aiHistoryEntity);
                aiHistoryEntity.setFenciAgentName(fenci);
                long endfc = (System.currentTimeMillis() - startfc);
                log.info("ai分词耗时-"+ endfc + "ms");
                if(StringUtils.isNotEmpty(fenci)){
                    Set<String> fc = new HashSet<>();
                    String temp = fenci.replaceAll("，", ",");
                    String fenciNew = temp.replaceAll("[\\t\\n]", "");
                    log.info(fenciNew);
                    Map bodyMap = JSONObject.parseObject(fenciNew, Map.class);
                    Object data = bodyMap.getOrDefault("data",null);
                    if(data != null){
                        Map dataMap = JSONObject.parseObject(data.toString(), Map.class);
                        Object outputs = dataMap.getOrDefault("outputs", null);
                        if(outputs != null){
                            Map outputsMap = JSONObject.parseObject(outputs.toString(), Map.class);
                            Object result = outputsMap.getOrDefault("data", null);
                            log.info(result.toString());
                            if(result != null){
                                Map resultMap = JSONObject.parseObject(result.toString(), Map.class);
                                String pinpai = (String)resultMap.getOrDefault("汽车品牌", null);
                                if(pinpai == null){
                                    pinpai = (String)resultMap.getOrDefault("品牌", null);
                                    if(pinpai == null){
                                        pinpai = (String)resultMap.getOrDefault("品牌标签", null);
                                    }
                                }
                                String zhibiao = (String)resultMap.getOrDefault("指标", null);
                                if(zhibiao == null){
                                    zhibiao = (String)resultMap.getOrDefault("指标标签", null);
                                }
                                log.info(pinpai);
                                log.info(zhibiao);
                                if(pinpai != null){
                                    fc.add(pinpai);
                                }
                                if(zhibiao != null){
                                    fc.add(zhibiao);
                                }
                            }
                        }
                    }
                    if(fc.size() > 0){
                        String fcStr = String.join(",", fc);
                        aiHistoryEntity.setSplitWords(fcStr);
                        log.info(fcStr);
                    }
                    log.info(aiHistoryEntity.getQuestion());
                    int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                }else{
                    aiHistoryEntity.setPermission("0");
                    aiHistoryEntity.setRemarks("AI分词错误-"+ aiHistoryEntity.toString());
                    int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
                }
            }catch (Exception e){
                aiHistoryEntity.setPermission("0");
                aiHistoryEntity.setRemarks("分词请求错误-"+ e.getMessage());
                int insert = aiHistoryMapper.updateHistoryRecord(aiHistoryEntity);
            }
        }
    }

    // 获取问题分词
    public String getQuestionSplitWordsRetry(AiHistoryEntity aiHistoryEntity) {
        log.info("开始分词处理");
        List<AiAgentType> agentTypeFenci = aiAgentTypeMapper.getAgentTypeFenci();
        AiAgentType aiAgentType = agentTypeFenci.get(0);
        String url_messages = aiAgentType.getPathValue();

        Map<String, Object> bodyParam = new HashMap<>();
        Map<String, Object> inputs = new HashMap<>();
        inputs.put("question",aiHistoryEntity.getQuestion());
        bodyParam.put("inputs",inputs);
        //bodyParam.put("conversation_id", aiHistoryEntity.getFenciSessionId());
        bodyParam.put("response_mode", "blocking");
        bodyParam.put("user", aiHistoryEntity.getUserId());

        String authorization = "Bearer " + aiAgentType.getAgentKey();
        aiHistoryEntity.setFenciAgentId(authorization);
        HttpResponse execute = HttpRequest.post(url_messages)
                .header(Header.AUTHORIZATION, authorization)
                .header(Header.CONTENT_TYPE, "application/json")
                .body(JSON.toJSONString(bodyParam))
                .execute();
        int status = execute.getStatus();
        String body = execute.body();
        log.info("分词返回- " + body);
        if(200 == status){
            // 由于分词采用工作流没有上下文，需考虑优化后再处理
            // aiHistoryEntity.setAgentId(authorization);
            return body;
        }else{
            return null;
        }
    }


}
