package com.ds.cockpit.screen.web.controller.system;

import com.ds.cockpit.screen.common.annotation.Log;
import com.ds.cockpit.screen.common.core.controller.BaseController;
import com.ds.cockpit.screen.common.core.domain.AjaxResult;
import com.ds.cockpit.screen.common.core.domain.entity.GacDownloadLogs;
import com.ds.cockpit.screen.common.core.page.TableDataInfo;
import com.ds.cockpit.screen.common.enums.BusinessType;
import com.ds.cockpit.screen.system.service.IGacDownloadLogsService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.servlet.http.HttpServletRequest;
import java.util.List;

/**
 * 数据下载日志记录
 * 
 * @author
 */
@RestController
@RequestMapping("/gac/download/logs")
public class GacDownloadLogsController extends BaseController
{
    @Autowired
    private IGacDownloadLogsService gacDownloadLogsService;

    /**
     * 获取数据列表
     */
    @PostMapping("/list")
    @Log(title = "数据下载日志记录", businessType = BusinessType.OTHER)
    public TableDataInfo list(HttpServletRequest request, @RequestBody GacDownloadLogs gacDownloadLogs) throws Exception {
        List<GacDownloadLogs> list = gacDownloadLogsService.selectListBy(request, gacDownloadLogs);
        return getDataTable(list);
    }

    /**
     * 数据下载日志记录
     */
    @Log(title = "数据下载日志记录", businessType = BusinessType.INSERT)
    @PostMapping("/add")
    public AjaxResult submit(HttpServletRequest request, @RequestBody GacDownloadLogs GacDownloadLogs)
    {
        return toAjax(gacDownloadLogsService.addEvaluationAnalysis(request, GacDownloadLogs));
    }


}
