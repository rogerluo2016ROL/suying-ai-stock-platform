package com.ds.cockpit.screen.common.core.domain.entity.vo;

import lombok.Data;
import lombok.ToString;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

@Data
@ToString
public class MenuEntity implements Serializable {

    /**
     * 菜单编码
     */
    private String code;

    /**
     * 是否隐藏(0:显示 1:隐藏)
     */
    private String visible;

    private Integer isDelete;

    /**
     * 菜单图标
     */
    private String icon;

    /**
     * 排序值。越小越先排序
     */
    private Integer orderBy;

    /**
     * 父菜单id
     */
    private Long pId;

    private Long pid;

    private String terminal;

    /**
     * 组件类型,1:目录,2:菜单,3:按钮
     */
    private String type;

    /**
     * 组件地址
     */
    private String url;

    /**
     * 组件地址
     */
    private String component;

    private Long appId;

    /**
     * 菜单名称
     */
    private String name;

    /**
     * 动作
     */
    private String action;

    /**
     * 权限标识
     */
    private String perms;

    /**
     * 菜单id(编码)
     */
    private Long id;

    private String state;

    private List<MenuEntity> childrenList = new ArrayList<>(32);

}
