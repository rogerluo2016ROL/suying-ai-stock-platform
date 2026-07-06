package com.ds.cockpit.screen.common.core.domain.entity.vo.dataperm;

import lombok.Data;

/**
 * @Author: ZhouHong
 * @Date: 2025-05-22 下午 08:29
 */
@Data
public class ColumnValue {

    /**
     * 字段值
     */
    private String columnValue;

    /**
     * 字段值规则,eq:等于,great:大于,ge:大于等于,less:小于,le:小于等于
     * (由于设计理念继承于旧版保留了次字段，实际目前均为 等于-eq)
     */
    private String valueRule;

}
