package com.ds.cockpit.screen.common.core.domain.entity.vo.dataperm;

import lombok.Data;

import java.util.List;

/**
 * @Author: ZhouHong
 * @Date: 2025-05-22 下午 08:28
 */
@Data
public class RowPerm {

    /**
     * 字段名
     */
    private String columnName;

    /**
     * 字段值列表
     */
    private List<ColumnValue> columnValues;

}
