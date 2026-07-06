package com.ds.cockpit.screen.common.core.domain.entity.vo.dataperm;

import lombok.Data;

import java.util.List;

/**
 * @Author: ZhouHong
 * @Date: 2025-05-22 下午 08:27
 */
@Data
public class DataSourcePerms{
    Long sourceId;
    String sourceName;
    List<DataTablePerm> dataTablePerms;
}
