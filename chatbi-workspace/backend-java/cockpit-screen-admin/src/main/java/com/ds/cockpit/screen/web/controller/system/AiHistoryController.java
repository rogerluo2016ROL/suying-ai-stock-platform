package com.ds.cockpit.screen.web.controller.system;

import com.ds.cockpit.screen.common.core.controller.BaseControllerNew;
import com.ds.cockpit.screen.common.core.domain.entity.AiHistoryEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.AiHistoryRequestVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.AiHistoryResponseVo;
import com.ds.cockpit.screen.common.response.ApiResponse;
import com.ds.cockpit.screen.system.service.AiHistoryService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@Api(tags = "历史会话回溯")
@RestController
@RequestMapping("/ai/histroy")
public class AiHistoryController extends BaseControllerNew {

    @Autowired
    private AiHistoryService aiHistoryService;

    @ApiOperation("获取历史会话")
    @PostMapping("/record/list")
    public ApiResponse<List<AiHistoryResponseVo>> getHistoryrecord(@RequestBody AiHistoryRequestVO vo) {
        List<AiHistoryResponseVo> historyrecord = aiHistoryService.getHistoryRecordList(vo);
        return  success(historyrecord);
    }

    @ApiOperation("历史会话详情回溯")
    @PostMapping("/gethistory")
    public ApiResponse<List<AiHistoryEntity>> getHistory(@RequestBody AiHistoryRequestVO vo) {
        List<AiHistoryEntity> gethistory = aiHistoryService.getHistory(vo);
        return  success(gethistory);
    }

    @ApiOperation("获取历史会话-意见反馈")
    @PostMapping("/details/list")
    public ApiResponse<List<AiHistoryEntity>> getHistoryDetails(@RequestBody AiHistoryRequestVO vo) {
        List<AiHistoryEntity> historyrecord = aiHistoryService.getHistoryDetailsList(vo);
        return  success(historyrecord);
    }


}
