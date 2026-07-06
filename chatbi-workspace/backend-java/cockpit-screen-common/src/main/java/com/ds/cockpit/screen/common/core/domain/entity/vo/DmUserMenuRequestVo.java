package com.ds.cockpit.screen.common.core.domain.entity.vo;

import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

import java.io.Serializable;
import java.util.List;

@Data
public class DmUserMenuRequestVo implements Serializable {
    @ApiModelProperty("Id")
    private Long id;
    @ApiModelProperty("原始id")
    private Integer uId;
    @ApiModelProperty("用户Id")
    private String userId;
    @ApiModelProperty("菜单Id")
    private String menuCode;
    @ApiModelProperty("菜单名称")
    private String name;
    @ApiModelProperty("排序值")
    private Integer orderValue;
    @ApiModelProperty("指标卡状态")
    private Integer status;
    @ApiModelProperty("菜单Id集合")
    private List<String> menuCodeList;

    /**
     *  用户权限查询参数
     */

    @ApiModelProperty("accessToken")
    private String accessToken;

    @ApiModelProperty("timestamp")
    private String timestamp;

    @ApiModelProperty("terminalType-终端类型")
    private String terminalType;

}
