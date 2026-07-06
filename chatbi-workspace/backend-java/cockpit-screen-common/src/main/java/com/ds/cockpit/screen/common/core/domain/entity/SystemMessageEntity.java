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
 * 消息中心 system_message
 * @Author: ZhouHong
 * @Date: 2024-01-24 下午 02:27
 */
@Data
@TableName("system_message")
public class SystemMessageEntity extends Model<SystemMessageEntity> implements Serializable {

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
     * 通知内容
     */
    private String content;

    /**
     * 是否发布(0:否-撤回 1:是)
     */
    private Integer sendUrgentNotice;

    /**
     * 紧急公告内容
     */
    private String urgentNoticeContent;

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

    /**
     * 公告失效时间
     */
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss", timezone = "GMT+8")
    private Date expirationTime;

    private static final long serialVersionUID = 1L;

}
