package com.ds.cockpit.screen.common.core.domain.entity.vo;

import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

import java.io.Serializable;
import java.util.List;

@Data
public class UserMenuPermVo implements Serializable {

    @ApiModelProperty("accessToken")
    private String accessToken;

    @ApiModelProperty("timestamp")
    private String timestamp;

    @ApiModelProperty("terminalType-终端类型")
    private String terminalType;

}
