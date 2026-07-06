package com.ds.cockpit.screen.web.controller.system;

import com.ds.cockpit.screen.common.core.controller.BaseControllerNew;
import com.ds.cockpit.screen.common.core.domain.entity.vo.BuryingPointExportVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.BuryingPointRequestVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.BuryingResponseVo;
import com.ds.cockpit.screen.common.response.ApiResponse;
import com.ds.cockpit.screen.common.utils.poi.ExcelUtil;
import com.ds.cockpit.screen.system.service.BuryingpointService;
import com.ds.cockpit.screen.system.utils.PreconditionsUtils;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.servlet.http.HttpServletResponse;
import java.util.ArrayList;
import java.util.List;

@Api(tags = "埋点")
@RestController
@RequestMapping("/burying/point")
public class BuryingpointController extends BaseControllerNew {

    @Autowired
    private BuryingpointService buryingpointService;

    @ApiOperation("埋点接数")
    @PostMapping(value = "/buryingpoint")
    public ApiResponse<Integer> buryingpoint(@RequestBody BuryingPointRequestVO vo) {
        int result = buryingpointService.getburyingpoint(vo);
        return success(result);

    }

    @ApiOperation("埋点点击量")
    @PostMapping("/getBuryingHits")
    public ApiResponse<List<BuryingResponseVo>> getBuryingHits(@RequestBody BuryingPointRequestVO vo) {
        List<BuryingResponseVo> buryingHits = buryingpointService.getBuryingHits(vo);
        return  success(buryingHits);
    }

    @GetMapping(value = "/export/buryingpoint/{start}/{end}")
    public void exportBuryingpoint(HttpServletResponse response, @PathVariable("start") String startTime,
                                @PathVariable("end") String endTime, String environment) throws Exception {
        PreconditionsUtils.checkNotNull(startTime, "数据开始时间不能为空（yyyy-MM-dd）");
        PreconditionsUtils.checkNotNull(endTime, "数据结束时间不能为空（yyyy-MM-dd）");
        PreconditionsUtils.checkNotNull(environment, "环境参数未指定");
        List<BuryingPointExportVO> data = new ArrayList();
        data = buryingpointService.exportBuryingpoint(startTime, endTime, environment);
        //返回文件
        ExcelUtil<BuryingPointExportVO> util = new ExcelUtil<BuryingPointExportVO>(BuryingPointExportVO.class);
        util.exportExcel(response, data,"系统埋点分环境分时导出" );
    }
}
