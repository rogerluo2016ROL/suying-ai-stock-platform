package com.ds.cockpit.screen.system.service;

import com.ds.cockpit.screen.common.core.domain.AjaxResult;

/**
 * @Author: ZhouHong
 * @Date: 2025/7/30 09:43
 */
public interface AiAgentTypeDifyService {


    AjaxResult getListQAndA();

    AjaxResult getAgentQAndAById(Long id);
}
