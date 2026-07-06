package com.ds.cockpit.screen.common.core.domain.entity.vo;

import lombok.Data;

@Data
public class SystemUserNoviceGuideVo {


    /**
     * 主键
     */
    private Long id;

    /**
     * 用户id
     */
    private String userId;

    /**
     * 用户名
     */
    private String userName;

    /**
     * 用户部门
     */
    private String userDept;


    /**
     * 说明、描述
     */
    private String descriptions;
}
