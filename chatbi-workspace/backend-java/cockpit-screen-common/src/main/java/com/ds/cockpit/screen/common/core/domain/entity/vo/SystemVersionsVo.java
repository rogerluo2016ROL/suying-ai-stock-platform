package com.ds.cockpit.screen.common.core.domain.entity.vo;

import com.fasterxml.jackson.annotation.JsonFormat;
import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

import java.util.Date;

/**
 * 版本管理
 * @Author: ZhouHong
 * @Date: 2024-01-24 下午 02:27
 */

@Data
public class SystemVersionsVo {

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
     * 发版内容
     */
    @ApiModelProperty("发版内容")
    private String content;

    /**
     * 影响范围
     */
    @ApiModelProperty("影响范围（验证人）")
    private String influenceScope;

    /**
     * 实施时间
     */
    @ApiModelProperty("实施时间(版本号)")
    private String implementTime;

    /**
     * 创建时间
     */
    @ApiModelProperty(value = "创建时间")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss", timezone = "GMT+8")
    private Date createTime;

    /**
     * 是否有效(0:无效 1:有效)
     */
    @ApiModelProperty("是否有效(0:无效 1:有效)")
    private Integer availability;

    /**
     * 是否影响用户使用(0:不影响 1:影响)
     */
    @ApiModelProperty("是否影响用户使用(0:不影响 1:影响)")
    private Integer usable;

    /**
     * 是否发布(0:撤回 1:发布)
     */
    @ApiModelProperty("是否公告(0:否 1:是)")
    private Integer released;

    /**
     * 公告失效时间
     */
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss", timezone = "GMT+8")
    @ApiModelProperty("公告失效时间")
    private Date expirationTime;

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
    @ApiModelProperty(value = "更新时间——自动生成")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss", timezone = "GMT+8")
    private Date updateTime;

}
