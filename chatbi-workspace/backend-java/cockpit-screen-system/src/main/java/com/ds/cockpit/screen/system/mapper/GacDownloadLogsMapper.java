package com.ds.cockpit.screen.system.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.ds.cockpit.screen.common.core.domain.entity.GacDownloadLogs;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

/**
 * @Author: ZhouHong
 * @Date: 2024-12-19 上午 11:46
 */
@Mapper
public interface GacDownloadLogsMapper extends BaseMapper<GacDownloadLogs> {

    List<GacDownloadLogs> selectListBy(@Param("logs") GacDownloadLogs gacDownloadLogs);

    /**
     * 新增
     *
     * @param gacDownloadLogs 信息
     * @return 结果
     */
    int insertGacDownloadLogs(GacDownloadLogs gacDownloadLogs);

    GacDownloadLogs selectById(String id);

    int updateAnalysis(GacDownloadLogs gacDownloadLogs);

}
