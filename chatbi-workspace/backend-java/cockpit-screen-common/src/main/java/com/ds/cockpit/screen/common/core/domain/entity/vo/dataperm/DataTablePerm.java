package com.ds.cockpit.screen.common.core.domain.entity.vo.dataperm;

import lombok.Data;

import java.util.List;

/**
 * @Author: ZhouHong
 * @Date: 2025-05-22 下午 08:28
 */
@Data
public class DataTablePerm {

    /**
     * 数据表名
     */
    private String tableName;

    /**
     * 行级数据权限
     */
    private List<RowPerm> rowPerms;

    /**
     * 列级数据权限
     */
    private List<String> columnPerms;

}
