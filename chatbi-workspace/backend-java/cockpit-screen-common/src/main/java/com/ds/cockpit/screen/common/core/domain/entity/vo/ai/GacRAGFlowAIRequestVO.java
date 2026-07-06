package com.ds.cockpit.screen.common.core.domain.entity.vo.ai;

import lombok.Data;

/** AI请求参数
 * @Author: ZhouHong
 * @Date: 2025-05-14 下午 01:55
 */
@Data
public class GacRAGFlowAIRequestVO {

    private Long id;
    private String question;
    private String userId;
    private String userName;
    private String sessionUuid;

    private Long agentId;
}
