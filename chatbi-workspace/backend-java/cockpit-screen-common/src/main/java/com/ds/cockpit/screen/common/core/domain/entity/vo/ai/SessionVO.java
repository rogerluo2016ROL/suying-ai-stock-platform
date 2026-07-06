package com.ds.cockpit.screen.common.core.domain.entity.vo.ai;

import com.alibaba.fastjson2.JSONArray;
import com.alibaba.fastjson2.JSONObject;
import lombok.Data;

/**
 * @Author: ZhouHong
 * @Date: 2025-05-12 上午 10:41
 */
@Data
public class SessionVO {

    private String answer;
    private String id;
    private String sessionId;
    private String agentId;

}
