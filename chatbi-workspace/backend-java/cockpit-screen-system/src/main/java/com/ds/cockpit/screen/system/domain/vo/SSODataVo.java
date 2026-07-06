package com.ds.cockpit.screen.system.domain.vo;

//import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

/**
 * @author oumin
 * @date 2020/10/29 20:06
 */
@Data
public class SSODataVo {

    // @ApiModelProperty(value = "登录链接")
    private String loginUrl;

    // @ApiModelProperty(value = "用户信息")
    private SSOUserInfoResVo userInfoResVo;
}
