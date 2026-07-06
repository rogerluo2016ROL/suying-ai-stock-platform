package com.ds.cockpit.screen.system.domain.vo;

//import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

/**
 * @author oumin
 * @date 2020/10/29 20:06
 */
@Data
public class SSOUserInfoResVo {

    private String username;

    /**
     * 门户的登录账号
     */
    //@ApiModelProperty(value = "门户的登录账号")
    private String account;

    /**
     * 用户的名称（姓名或别称)
     */
    //@ApiModelProperty(value = "用户的名称（姓名或别称)")
    private String nickname;

    /**
     * 邮箱
     */
    //@ApiModelProperty(value = "邮箱")
    private String email;

    /**
     * 手机号码
     */
    //@ApiModelProperty(value = "手机号码")
    private String mobile;

    private Integer status;

    private String remark;

    private String channel;

    private String fromId;
}
