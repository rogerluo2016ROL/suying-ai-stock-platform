package com.ds.cockpit.screen.system.service.impl;

import lombok.AllArgsConstructor;
import lombok.Getter;


/**
 *  用户自定义指标卡状态枚举
 */
@Getter
@AllArgsConstructor
public enum UserDefinedEnum {

    DELETE(0,"删除"),
    ADD(1,"添加");

    private Integer status;
    private String desc;

}
