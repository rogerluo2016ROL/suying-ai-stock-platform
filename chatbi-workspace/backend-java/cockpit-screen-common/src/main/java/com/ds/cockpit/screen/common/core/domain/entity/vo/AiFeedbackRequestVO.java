package com.ds.cockpit.screen.common.core.domain.entity.vo;

import lombok.Data;

/**
 * @Author: ZhouHong
 * @Date: 2025-05-23 下午 11:05
 */
@Data
public class AiFeedbackRequestVO {

    private Long id;

    /**
     * 问题反馈/建议(提问)
     */
    private String questionFeedback;

    /**
     * 问题反馈/建议(回答)
     */
    private String answerFeedback;

    /**
     * 问题反馈/建议(补充)
     */
    private String opinionFeedback;


}
