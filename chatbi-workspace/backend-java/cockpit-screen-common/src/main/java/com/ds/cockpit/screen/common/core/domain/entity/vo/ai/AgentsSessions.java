package com.ds.cockpit.screen.common.core.domain.entity.vo.ai;

import com.alibaba.fastjson2.JSONObject;
import lombok.Data;

/**
 * @Author: ZhouHong
 * @Date: 2025-05-12 上午 10:39
 */
@Data
public class AgentsSessions {

    String agent_id;
    String user_id;
    String id;
    String source;
    JSONObject dsl;
    Message[] message;
}
