package com.ds.cockpit.screen.system.service.impl;

import cn.hutool.http.HttpRequest;
import cn.hutool.http.HttpResponse;
import com.alibaba.fastjson2.JSON;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.ds.cockpit.screen.common.core.domain.entity.SystemMessageEntity;
import com.ds.cockpit.screen.common.core.domain.entity.SystemVersionsEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.SystemVersionsVo;
import com.ds.cockpit.screen.common.utils.StringUtils;
import com.ds.cockpit.screen.system.domain.vo.SSODataVo;
import com.ds.cockpit.screen.system.domain.vo.SSOResultVo;
import com.ds.cockpit.screen.system.domain.vo.SSOUserInfoResVo;
import com.ds.cockpit.screen.system.mapper.SystemMessageMapper;
import com.ds.cockpit.screen.system.mapper.SystemVersionsMapper;
import com.ds.cockpit.screen.system.service.SystemVersionsService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.BeanUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import javax.servlet.http.HttpServletRequest;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** 开发环境使用
 * @author zhouhong
 * @description 针对表【system_user_login】的数据库操作Service实现
 * @createDate 2024-01-25
 */
@Slf4j
@Service
public class SystemVersionsServiceImpl implements SystemVersionsService {

    @Autowired
    private SystemVersionsMapper systemVersionsMapper;

    @Autowired
    private SystemMessageMapper systemMessageMapper;

    @Override
    public List<SystemVersionsEntity> getVersions(SystemVersionsVo vo) {
        return  systemVersionsMapper.getVersions(vo);
    }

    // 若需使用需进行改造
    @Override
    public Boolean changeStatus(SystemVersionsVo vo) {
        SystemVersionsEntity systemVersionsEntity = new SystemVersionsEntity();
        BeanUtils.copyProperties(vo,systemVersionsEntity);
        if(0 == systemVersionsEntity.getAvailability()){
            throw new RuntimeException("版本无效或发版失败，请确认后操作");
        }
        //更新失效标识及失效时间
        systemVersionsEntity.setAvailability(0);
        systemVersionsEntity.setUpdateTime(new Date());
        //return updateById(systemVersionsEntity);
        int update = systemVersionsMapper.unAvailability(vo.getId());
        if(update > 0){
            return true;
        }
        return false;
    }

    @Override
    public Boolean add(HttpServletRequest request, SystemVersionsVo systemVersionsVo) throws Exception {
        SystemVersionsEntity systemVersionsEntity = new SystemVersionsEntity();
        BeanUtils.copyProperties(systemVersionsVo,systemVersionsEntity);
        SSOUserInfoResVo ssoUserInfoResVo = checkArgument(request);
        log.info("成功获取用户信息");
        systemVersionsEntity.setUserId(ssoUserInfoResVo.getAccount()+"-"+ssoUserInfoResVo.getNickname());
        int insert = systemVersionsMapper.insertEntity(systemVersionsEntity);
        if(insert > 0){
            if(systemVersionsEntity.getReleased() == 1){
                SystemMessageEntity systemMessageEntity = new SystemMessageEntity();
                systemMessageEntity.setTitle("发版计划");

                StringBuilder sb = new StringBuilder();
                sb.append(systemVersionsEntity.getContent()).append(System.lineSeparator());
                sb.append("版本:").append(systemVersionsEntity.getImplementTime()).append(System.lineSeparator());
                sb.append("验证人:").append(systemVersionsEntity.getInfluenceScope()).append(System.lineSeparator());
                sb.append("是否影响用户使用:").append(systemVersionsEntity.getUsable() == 1 ? "影响" : "不影响").append(System.lineSeparator());
                String content = sb.toString();
                systemMessageEntity.setContent(content);

                systemMessageEntity.setSendUrgentNotice(systemVersionsEntity.getReleased());
                //systemMessageEntity.setUrgentNoticeContent();
                systemMessageEntity.setAvailability(1);
                systemMessageEntity.setSendUrgentNotice(1);
                systemMessageEntity.setExpirationTime(systemVersionsEntity.getExpirationTime());
                systemMessageEntity.setUserId(ssoUserInfoResVo.getAccount()+"-"+ssoUserInfoResVo.getNickname());
                insert = systemMessageMapper.insertEntity(systemMessageEntity);
                if(insert > 0){
                    return true;
                }
            }
            return true;
        }
        return false;
    }

    @Override
    public Boolean delete(SystemVersionsVo systemVersionsVo) {
        if(null == systemVersionsVo || null == systemVersionsVo.getId()){
            return false;
        }
        SystemVersionsEntity systemVersionsEntity = systemVersionsMapper.selectByEntityId(systemVersionsVo.getId());
        if(systemVersionsEntity != null ){
            int update = systemVersionsMapper.unAvailability(systemVersionsVo.getId());
            if(update > 0){
                return true;
            }
        }
        return false;
    }

    @Override
    public Boolean update(HttpServletRequest request, SystemVersionsVo systemVersionsVo) throws Exception {
        if(null == systemVersionsVo || null == systemVersionsVo.getId()){
            return false;
        }
        if(systemVersionsVo != null ){
            SystemVersionsEntity systemVersionsEntity = new SystemVersionsEntity();
            BeanUtils.copyProperties(systemVersionsVo,systemVersionsEntity);
            SSOUserInfoResVo ssoUserInfoResVo = checkArgument(request);
            log.info("成功获取用户信息");
            systemVersionsEntity.setUserId(ssoUserInfoResVo.getAccount()+"-"+ssoUserInfoResVo.getNickname());
            int update = systemVersionsMapper.updateEntity(systemVersionsEntity);
            if(update > 0){
                return true;
            }
        }
        return false;
    }

    @Override
    public Boolean released(SystemVersionsVo systemVersionsVo) {
        if(null == systemVersionsVo || null == systemVersionsVo.getId()){
            return false;
        }
        SystemVersionsEntity systemVersionsEntity = systemVersionsMapper.selectByEntityId(systemVersionsVo.getId());
        if(systemVersionsEntity != null ){
            if(1 == systemVersionsEntity.getReleased() || 0 == systemVersionsEntity.getAvailability()){
                throw new RuntimeException("版本已发布或已删除，请确认后操作");
            }
            int released = systemVersionsMapper.released(systemVersionsVo.getId());
            if(released > 0){
                return true;
            }
        }
        return false;
    }

    @Override
    public Boolean recall(SystemVersionsVo systemVersionsVo) {
        if(null == systemVersionsVo || null == systemVersionsVo.getId()){
            return false;
        }
        SystemVersionsEntity systemVersionsEntity = systemVersionsMapper.selectByEntityId(systemVersionsVo.getId());
        if(systemVersionsEntity != null ){
            if(0 == systemVersionsEntity.getReleased() || 0 == systemVersionsEntity.getAvailability()){
                throw new RuntimeException("版本未发布或已删除，请确认后操作");
            }
            int recall = systemVersionsMapper.recall(systemVersionsVo.getId());
            if(recall > 0){
                return true;
            }
        }
        return false;
    }

    @Value("${ac.url:}")
    private String url;

    @Value("${ac.jwtAnalysis:}")
    private String jwtAnalysis;

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




