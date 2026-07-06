package com.ds.cockpit.screen.system.service;

import com.ds.cockpit.screen.common.core.domain.entity.GacDownloadLogs;
import com.ds.cockpit.screen.system.domain.vo.SSOUserInfoResVo;

import javax.servlet.http.HttpServletRequest;
import java.util.List;

/**
 * 数据下载日志记录 业务层
 * 
 * @author zhouhong
 */
public interface IGacDownloadLogsService
{
    /**
     * 根据条件查询数据列表
     * @param gacDownloadLogs
     * @return
     */
    List<GacDownloadLogs> selectListBy(HttpServletRequest request, GacDownloadLogs gacDownloadLogs);

    /**
     * 新增评价分析
     * @param gacDownloadLogs
     * @return
     */
    int addEvaluationAnalysis(HttpServletRequest request, GacDownloadLogs gacDownloadLogs);

    SSOUserInfoResVo checkArgument(HttpServletRequest request) throws Exception;
}
