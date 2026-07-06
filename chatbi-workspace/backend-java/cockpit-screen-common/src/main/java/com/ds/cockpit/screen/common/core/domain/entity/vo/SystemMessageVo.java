package com.ds.cockpit.screen.common.core.domain.entity.vo;

import com.fasterxml.jackson.annotation.JsonFormat;
import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

import java.util.Date;

/**
 * 消息中心
 * @Author: ZhouHong
 * @Date: 2024-01-24 下午 02:27
 */

@Data
public class SystemMessageVo {

    /**
     * id
     */
    private Long id;

    /**
     * 标题
     */
    @ApiModelProperty("标题(预留字段)")
    private String title;

    /**
     * 通知内容
     */
    @ApiModelProperty("通知内容")
    private String content;

    /**
     * 是否发布(0:否 1:是)
     */
    @ApiModelProperty("是否发布(0:否 1:是)")
    private Integer sendUrgentNotice;

    /**
     * 紧急公告内容
     */
    @ApiModelProperty("紧急公告内容")
    private String urgentNoticeContent;

    /**
     * 创建时间
     */
    @ApiModelProperty("创建时间-自动生成")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss", timezone = "GMT+8")
    private Date createTime;

    /**
     * 是否有效(0:无效 1:有效)
     */
    @ApiModelProperty("是否有效(0:无效 1:有效) ——手动失效时使用")
    private Integer availability;

    /**
     * 用户id
     */
    @ApiModelProperty("用户id")
    private String userId;

    /**
     * 说明、描述
     */
    @ApiModelProperty("说明、描述")
    private String descriptions;

    /**
     * 更新时间
     */
    @ApiModelProperty("更新时间——自动生成")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss", timezone = "GMT+8")
    private Date updateTime;

    /**
     * 失效时间
     */
    @ApiModelProperty("失效时间——设置或手动失效时生成")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss", timezone = "GMT+8")
    private Date expirationTime;

}
