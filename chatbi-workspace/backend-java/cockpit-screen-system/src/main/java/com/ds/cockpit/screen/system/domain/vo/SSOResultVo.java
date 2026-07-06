package com.ds.cockpit.screen.system.domain.vo;

import lombok.Data;

@Data
public class SSOResultVo {
    private String code;

    private String msg;

    private boolean success;

    private SSODataVo data;
}
