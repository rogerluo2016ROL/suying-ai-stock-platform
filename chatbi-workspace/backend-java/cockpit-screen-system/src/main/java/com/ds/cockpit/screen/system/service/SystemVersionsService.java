package com.ds.cockpit.screen.system.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.ds.cockpit.screen.common.core.domain.entity.SystemVersionsEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.SystemVersionsVo;

import javax.servlet.http.HttpServletRequest;
import java.util.List;

/**
* @author zhouhong
* @description 针对表【system_versions】的数据库操作Service
* @createDate 2024-01-25
*/

public interface SystemVersionsService {

    List<SystemVersionsEntity> getVersions(SystemVersionsVo systemVersionsVo);

    Boolean changeStatus(SystemVersionsVo systemVersionsVo);

    Boolean add(HttpServletRequest request, SystemVersionsVo systemVersionsVo) throws Exception;

    Boolean delete(SystemVersionsVo systemVersionsVo);

    Boolean update(HttpServletRequest request, SystemVersionsVo systemVersionsVo) throws Exception;

    Boolean released(SystemVersionsVo systemVersionsVo);

    Boolean recall(SystemVersionsVo systemVersionsVo);
}
