package com.ds.cockpit.screen.common.core.domain.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.util.Date;

/**
 * 
 * @TableName system_user_novice_guide
 */
@Data
@TableName("system_user_novice_guide")
public class SystemUserNoviceGuideEntity implements Serializable {
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
     * 登录时间
     */
    private Date loginTime;

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

    private static final long serialVersionUID = 1L;

}