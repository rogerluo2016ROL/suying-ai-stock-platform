package com.ds.cockpit.screen.system.service.impl;

import cn.hutool.http.HttpUtil;
import com.alibaba.fastjson2.JSONArray;
import com.alibaba.fastjson2.JSONObject;
import com.alibaba.fastjson2.JSON;
import com.ds.cockpit.screen.common.core.domain.entity.vo.MenuEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.UserMenuPermVo;
import com.ds.cockpit.screen.system.service.UserPermissionsService;
import com.ds.cockpit.screen.system.utils.PreconditionsUtils;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
@Slf4j
public class UserPermissionsServiceImpl implements UserPermissionsService {

    @Value("${ac.url:}")
    private String url;

    @Value("${ac.menuAndPerm:null}")
    private String menuURL;

    @Override
    public List<MenuEntity> getUserMenuListByUserId(String userId , UserMenuPermVo userMenuPermVo) {
        PreconditionsUtils.checkNotNull(userId, "用户信息不能为空");
        PreconditionsUtils.checkNotNull(userMenuPermVo.getAccessToken(), "认证信息不能为空");
        PreconditionsUtils.checkNotNull(userMenuPermVo.getTimestamp(), "认证信息不能为空");
        PreconditionsUtils.checkNotNull(userMenuPermVo.getTerminalType(), "应用类型不能为空");
        log.info("userId:{},token:{}",userId,userMenuPermVo.getAccessToken() );
        Map<String, Object> param = new HashMap<>();
        param.put("accessToken", userMenuPermVo.getAccessToken());
        param.put("timestamp", userMenuPermVo.getTimestamp());
        param.put("terminalType", userMenuPermVo.getTerminalType());
        log.info("UserMenuListURL:{}", url+ menuURL );
        String body = HttpUtil.createGet(url+ menuURL).form(param).execute().body();
        JSONObject parse = JSONObject.parseObject(body);
        JSONObject data = parse.getJSONObject("data");
        log.info("data:{}",data);
        List<MenuEntity> menuEntityList = new ArrayList<>();
        if (data != null){
            JSONArray menuList = data.getJSONArray("menuList");
            menuEntityList = JSON.parseArray(menuList.toJSONString(), MenuEntity.class);
            return menuEntityList;
        }else{
            log.info("UserMenu-msg:{}",parse.getJSONObject("msg"));
        }
        return menuEntityList;
    }

    @Override
    public List<MenuEntity> getUserMenuListBy(String accessToken, String timestamp, String terminalType) {
        PreconditionsUtils.checkNotNull(accessToken, "认证信息不能为空");
        PreconditionsUtils.checkNotNull(timestamp, "认证信息不能为空");
        PreconditionsUtils.checkNotNull(terminalType, "应用类型不能为空");
        log.info("token:{}",accessToken );
        Map<String, Object> param = new HashMap<>();
        param.put("accessToken", accessToken);
        param.put("timestamp", timestamp);
        param.put("terminalType", terminalType);
        log.info("UserMenuListURL:{}", url+ menuURL );
        String body = HttpUtil.createGet(url+ menuURL).form(param).execute().body();
        JSONObject parse = JSONObject.parseObject(body);
        JSONObject data = parse.getJSONObject("data");
        log.info("data:{}",data);
        List<MenuEntity> menuEntityList = new ArrayList<>();
        if (data != null){
            JSONArray menuList = data.getJSONArray("menuList");
            menuEntityList = JSON.parseArray(menuList.toJSONString(), MenuEntity.class);
            return menuEntityList;
        }else{
            log.info("UserMenu-msg:{}",parse.getJSONObject("msg"));
        }
        return menuEntityList;
    }

    /*@Override
    public String getToken(String userId) {
        Map<String, Object> param = new HashMap<>();
        param.put("username", userId);
        String body = HttpUtil.createGet(tokenURL).form(param).execute().body();
        String token = "";
        if (StringUtils.isNoneBlank(body)){
            token = JSONObject.parseObject(body).getString("data");
        }
        return token;
    }*/
}
