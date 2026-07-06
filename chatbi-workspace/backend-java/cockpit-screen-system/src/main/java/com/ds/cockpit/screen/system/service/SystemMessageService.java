package com.ds.cockpit.screen.system.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.ds.cockpit.screen.common.core.domain.entity.SystemMessageEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.SystemMessageVo;

import javax.servlet.http.HttpServletRequest;
import java.util.List;

/**
* @author zhouhong
* @description 针对表【system_message】的数据库操作Service
* @createDate 2024-01-25
*/

public interface SystemMessageService extends IService<SystemMessageEntity> {

    List<SystemMessageEntity> getMessages(SystemMessageVo systemMessageVo);

    Boolean closeNotice(SystemMessageVo systemMessageVo);

    Boolean addAndEdit(HttpServletRequest request, SystemMessageVo systemMessageVo) throws Exception;

    Boolean delete(SystemMessageVo systemMessageVo);

    Boolean pushNotice(SystemMessageVo systemMessageVo);
}
