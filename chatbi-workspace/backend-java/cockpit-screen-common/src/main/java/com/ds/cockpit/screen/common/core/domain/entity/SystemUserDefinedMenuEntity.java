package com.ds.cockpit.screen.common.core.domain.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.fasterxml.jackson.annotation.JsonFormat;
import lombok.Data;

import java.io.Serializable;
import java.util.Date;

/**
 * 
 * @TableName system_user_defined_menu
 */
@Data
@TableName("system_user_defined_menu")
public class SystemUserDefinedMenuEntity implements Serializable {
    /**
     * 
     */
    @TableId(type = IdType.AUTO)
    private Long id;

    /**
     * 原始id
     */
    private Long uId;

    /**
     * 用户唯一标识
     */
    private String userId;

    /**
     * 菜单编码
     */
    private String menuCode;

    /**
     * 菜单名称
     */
    private String name;

    /**
     * 排序字段
     */
    private Integer orderValue;

    /**
     * 状态
     */
    private Integer status;

    /**
     * 指标卡别名
     */
    private String pluginPath;


    /**
     * 父id
     */
    private String parentId;

    /**
     * 父菜单名称
     */
    private String parentName;



    /**
     * 创建时间
     */
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss", timezone = "GMT+8")
    private Date createTime;

    /**
     * 编辑时间
     */
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss", timezone = "GMT+8")
    private Date updateTime;

    private static final long serialVersionUID = 1L;

}