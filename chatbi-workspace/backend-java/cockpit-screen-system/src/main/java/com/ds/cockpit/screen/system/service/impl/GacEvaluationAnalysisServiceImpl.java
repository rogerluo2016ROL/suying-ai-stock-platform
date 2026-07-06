package com.ds.cockpit.screen.system.service.impl;

import cn.hutool.http.HttpRequest;
import cn.hutool.http.HttpResponse;
import com.alibaba.fastjson2.JSON;
import com.ds.cockpit.screen.common.core.domain.entity.GacEvaluationAnalysis;
import com.ds.cockpit.screen.common.utils.StringUtils;
import com.ds.cockpit.screen.system.domain.vo.SSODataVo;
import com.ds.cockpit.screen.system.domain.vo.SSOResultVo;
import com.ds.cockpit.screen.system.domain.vo.SSOUserInfoResVo;
import com.ds.cockpit.screen.system.mapper.GacEvaluationAnalysisMapper;
import com.ds.cockpit.screen.system.service.IGacEvaluationAnalysisService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import javax.servlet.http.HttpServletRequest;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * @Author: ZhouHong
 * @Date: 2024-12-19 上午 11:41
 */
@Slf4j
@Service
public class GacEvaluationAnalysisServiceImpl implements IGacEvaluationAnalysisService {

    @Resource
    private GacEvaluationAnalysisMapper gacEvaluationAnalysisMapper;

    private static final String FILE_DELIMETER = ",";

    @Value("${ac.url:}")
    private String url;

    @Value("${ac.jwtAnalysis:}")
    private String jwtAnalysis;

    @Override
    public List<GacEvaluationAnalysis> selectListBy(HttpServletRequest request, GacEvaluationAnalysis gacEvaluationAnalysis){
        log.info("开始查询评价分析数据");
        return gacEvaluationAnalysisMapper.selectListBy(gacEvaluationAnalysis);
    }

    @Override
    public int addEvaluationAnalysis(HttpServletRequest request, GacEvaluationAnalysis gacEvaluationAnalysis) {
        try {
            SSOUserInfoResVo ssoUserInfoResVo = checkArgument(request);
            log.info("成功获取用户信息");
            gacEvaluationAnalysis.setCreateCode(ssoUserInfoResVo.getAccount()+"-"+ssoUserInfoResVo.getUsername());
            gacEvaluationAnalysis.setCreateBy(ssoUserInfoResVo.getNickname());
        } catch (Exception e) {
            e.printStackTrace();
            return 0;
        }
        log.info("开始保存评价分析数据");
        return gacEvaluationAnalysisMapper.insertGacEvaluationAnalysis(gacEvaluationAnalysis);
    }

    @Override
    public int deleteFiles(HttpServletRequest request, String id) {
        GacEvaluationAnalysis gacEvaluationAnalysis = gacEvaluationAnalysisMapper.selectById(id);
        try {
            SSOUserInfoResVo ssoUserInfoResVo = checkArgument(request);
            log.info("成功获取用户信息");
            log.info("评价分析id:{},上传文件清除，修改人：{}，{}, 修改时间： {}",
                    id, ssoUserInfoResVo.getAccount()+"-"+ssoUserInfoResVo.getUsername(), ssoUserInfoResVo.getNickname(), new Date());
            //gacEvaluationAnalysis.setCreateCode(ssoUserInfoResVo.getAccount()+"-"+ssoUserInfoResVo.getUsername());
            //gacEvaluationAnalysis.setCreateBy(ssoUserInfoResVo.getNickname());
            //gacEvaluationAnalysis.setEvaluationAnalysis("");
            gacEvaluationAnalysis.setEvaluationAnalysisFile("");
            gacEvaluationAnalysis.setOriginalFilenames("");
            gacEvaluationAnalysis.setNewFileNames("");
        } catch (Exception e) {
            e.printStackTrace();
            return 0;
        }
        log.info("开始更新评价分析数据-删除上传文件");
        return gacEvaluationAnalysisMapper.updateAnalysis(gacEvaluationAnalysis);
    }

    @Override
    public SSOUserInfoResVo checkArgument(HttpServletRequest request) throws Exception {
        log.info("gac-开始用户校验");
        String token = request.getHeader("Authorization");
        if(StringUtils.isNotEmpty(token)){
            // 请求平台管家校验token
            String urlJwt = url + jwtAnalysis;
            Map<String, String> map = new HashMap<>(1);
            map.put("token", token);
            Map<String, String > heads = new HashMap<>();
            heads.put("Content-Type", "application/json;charset=UTF-8");
            log.info("gac-开始请求平台管家接口：【{}】进行校验",urlJwt);
            HttpResponse platformResponse = HttpRequest.post(urlJwt)
                    .headerMap(heads, false)
                    .body(JSON.toJSONString(map)).execute();
            if(platformResponse.getStatus()==200) {
                String body = platformResponse.body();
                SSOResultVo result = JSON.parseObject(body, SSOResultVo.class);
                if (!"0000".equals(result.getCode())){
                    throw new Exception(StringUtils.format("token校验出错。 ", token));
                }else{
                    log.info("gac-校验token的返回体："+platformResponse.body());
                }
                SSODataVo ssoDataVo = result.getData();
                SSOUserInfoResVo userInfoResVo = ssoDataVo.getUserInfoResVo();
                log.info("gac-平台管家解析接口返回用户信息：【{}】", ssoDataVo.getUserInfoResVo().toString());
                return userInfoResVo;
            }else{
                log.info("gac-平台管家解析接口返回：【{}】",platformResponse.toString());
            }
            //SSOResponseResultVo ssoResponseResultVo = this.checkToken(urlJwt, token);
            return null;
        }else{
            log.info("gac-未能获取到请求头中的token值");
            throw new Exception(StringUtils.format("token校验出错。 ", token));
        }
    }
}
