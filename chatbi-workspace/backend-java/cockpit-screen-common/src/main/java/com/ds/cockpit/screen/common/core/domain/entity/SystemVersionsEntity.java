package com.ds.cockpit.screen.common.core.domain.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.baomidou.mybatisplus.extension.activerecord.Model;
import com.fasterxml.jackson.annotation.JsonFormat;
import lombok.Data;

import java.io.Serializable;
import java.util.Date;

/**
 * 版本管理 system_versions
 * @Author: ZhouHong
 * @Date: 2024-01-24 下午 02:27
 */
@Data
@TableName("system_versions")
public class SystemVersionsEntity extends Model<SystemVersionsEntity> implements Serializable {
    /**
     * id
     */
    @TableId(type = IdType.AUTO)
    private Long id;

    /**
     * 标题(预留字段)
     */
    private String title;

    /**
     * 发版内容
     */
    private String content;

    /**
     * 影响范围（验证人）
     */
    private String influenceScope;

    /**
     * 实施时间(版本号)
     */
    private String implementTime;

    /**
     * 创建时间
     */
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss", timezone = "GMT+8")
    private Date createTime;

    /**
     * 是否有效(0:无效 1:有效)
     */
    private Integer availability;

    /**
     * 是否影响用户使用(0:不影响 1:影响)
     */
    private Integer usable;

    /**
     * 是否发布(0:撤回 1:发布)
     * 是否公告(0:否 1:是)
     */
    private Integer released;

    /**
     * 公告失效时间
     */
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss", timezone = "GMT+8")
    private Date expirationTime;

    /**
     * 用户id
     */
    private String userId;

    /**
     * 说明、描述
     */
    private String descriptions;

    /**
     * 更新时间
     */
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss", timezone = "GMT+8")
    private Date updateTime;

    private static final long serialVersionUID = 1L;

}
