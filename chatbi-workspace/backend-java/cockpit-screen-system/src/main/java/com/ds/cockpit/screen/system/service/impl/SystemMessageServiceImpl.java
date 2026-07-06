package com.ds.cockpit.screen.system.service.impl;

import cn.hutool.http.HttpRequest;
import cn.hutool.http.HttpResponse;
import com.alibaba.fastjson2.JSON;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.ds.cockpit.screen.common.core.domain.entity.SystemMessageEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.SystemMessageVo;
import com.ds.cockpit.screen.common.utils.StringUtils;
import com.ds.cockpit.screen.system.domain.vo.SSODataVo;
import com.ds.cockpit.screen.system.domain.vo.SSOResultVo;
import com.ds.cockpit.screen.system.domain.vo.SSOUserInfoResVo;
import com.ds.cockpit.screen.system.mapper.SystemMessageMapper;
import com.ds.cockpit.screen.system.service.SystemMessageService;
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
public class SystemMessageServiceImpl extends ServiceImpl<SystemMessageMapper, SystemMessageEntity>
    implements SystemMessageService {

    @Autowired
    private SystemMessageMapper systemMessageMapper;

    @Override
    public List<SystemMessageEntity> getMessages(SystemMessageVo vo) {
        return  systemMessageMapper.getMessages(vo);
    }

    @Override
    public Boolean closeNotice(SystemMessageVo systemMessageVo) {
        SystemMessageEntity systemMessageEntity = systemMessageMapper.selectByEntityId(systemMessageVo.getId());
        if(0 == systemMessageEntity.getSendUrgentNotice() && systemMessageEntity.getId() != null){
            // 不支持撤回发布
            throw new RuntimeException("消息未发布，请确认后操作");
        }
        //更新标识及时间
        // systemMessageEntity.setAvailability(0);
        // systemMessageEntity.setUpdateTime(new Date());
        int update = systemMessageMapper.unSendUrgentNotice(systemMessageEntity.getId());
        if(update > 0){
            return true;
        }
        return false;
    }

    @Override
    public Boolean pushNotice(SystemMessageVo systemMessageVo) {
        SystemMessageEntity systemMessageEntity = systemMessageMapper.selectByEntityId(systemMessageVo.getId());
        if(1 == systemMessageEntity.getSendUrgentNotice() && systemMessageEntity.getId() != null){
            // 不支持撤回发布
            throw new RuntimeException("消息已发布，请勿重复发布");
        }
        //更新标识及时间
        int update = systemMessageMapper.sendUrgentNotice(systemMessageEntity.getId());
        if(update > 0){
            return true;
        }
        return false;
    }

    @Override
    public Boolean addAndEdit(HttpServletRequest request, SystemMessageVo systemMessageVo) throws Exception {

        SystemMessageEntity systemMessageEntity = new SystemMessageEntity();
        BeanUtils.copyProperties(systemMessageVo,systemMessageEntity);
        SSOUserInfoResVo ssoUserInfoResVo = checkArgument(request);
        log.info("成功获取用户信息");
        systemMessageEntity.setUserId(ssoUserInfoResVo.getAccount()+"-"+ssoUserInfoResVo.getNickname());
        int insert = 0 ;
        if(null != systemMessageVo.getId()){
            insert = systemMessageMapper.updateEntity(systemMessageEntity);
        }else{
            insert = systemMessageMapper.insertEntity(systemMessageEntity);
        }
        if(insert > 0){
            return true;
        }
        return false;
    }

    @Override
    public Boolean delete(SystemMessageVo systemMessageVo) {
        if(null == systemMessageVo.getId()){
            return false;
        }
        SystemMessageEntity systemMessageEntity = systemMessageMapper.selectByEntityId(systemMessageVo.getId());
        if(systemMessageEntity != null ){
            int update = systemMessageMapper.unAvailability(systemMessageVo.getId());
            if(update > 0){
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




