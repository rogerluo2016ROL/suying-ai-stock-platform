package com.ds.cockpit.screen.common.core.domain.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.util.Date;

/**
 *  用户默认应用
 * @TableName system_user_default_app
 */
@Data
@TableName("system_user_default_app")
public class SystemUserDefaultAppEntity implements Serializable {
    /**
     * 主键
     */
    @TableId(type = IdType.AUTO)
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
     * 是否有效(0:无效 1:有效)
     */
    private Integer availability;

    /**
     * 创建时间
     */
    private Date createTime;

    /**
     * 说明、描述
     */
    private String descriptions;

    /**
     * 更新时间
     */
    private Date updateTime;

    /**
     * 默认应用-名称
     */
    private String appName;

    /**
     * 默认应用-应用id
     */
    private Long appId;

    /**
     * 默认应用-显示名称
     */
    private String showName;

    /**
     * 默认应用-应用编码
     */
    private String appCode;

    /**
     * 默认应用-终端类型,1:PC端, 2:APP端, 3:PAD端, 4:大屏端, 5:H5端, 6:企微端
     */
    private String terminalType;

    private static final long serialVersionUID = 1L;

}