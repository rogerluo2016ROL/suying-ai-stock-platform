package com.ds.cockpit.screen.framework.config;

import cn.hutool.http.HttpRequest;
import cn.hutool.http.HttpResponse;
import com.alibaba.fastjson2.JSON;
import com.ds.cockpit.screen.common.utils.StringUtils;
import com.ds.cockpit.screen.system.domain.vo.SSODataVo;
import com.ds.cockpit.screen.system.domain.vo.SSOResultVo;
import com.ds.cockpit.screen.system.domain.vo.SSOUserInfoResVo;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.HashMap;
import java.util.Map;

/**
 * @Author: ZhouHong
 * @Date: 2025-01-17 下午 02:50
 */
@Slf4j
@Service
public class TokenValidationService {

    @Value("${ac.url:}")
    private String url;

    @Value("${ac.jwtAnalysis:}")
    private String jwtAnalysis;

    public SSOUserInfoResVo validateToken(String token) {

        if(StringUtils.isNotEmpty(token)){
            // 请求平台管家校验token
            String urlJwt = url + jwtAnalysis;
            Map<String, String> map = new HashMap<>(1);
            map.put("token", token);
            Map<String, String > heads = new HashMap<>();
            heads.put("Content-Type", "application/json;charset=UTF-8");
            log.info("gac-开始请求平台管家接口：【{}】进行校验",urlJwt);
            HttpResponse platformResponse = HttpRequest.post(urlJwt)
                    .addHeaders(heads)
                    .body(JSON.toJSONString(map)).setConnectionTimeout(30000).setReadTimeout(30000).execute();
            if(platformResponse.getStatus()==200) {
                String body = platformResponse.body();
                SSOResultVo result = JSON.parseObject(body, SSOResultVo.class);
                if (!"0000".equals(result.getCode())){
                    log.error("gac-校验token-error："+result.getMsg());
                    throw new RuntimeException(StringUtils.format("token校验出错。 ", token));
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
            return null;
        }else{
            log.info("gac-未能获取到请求头中的token值");
            throw new RuntimeException(StringUtils.format("token校验出错。- {} ", token));
        }
    }
}
