package com.ds.cockpit.screen.web.controller.system;

import cn.hutool.core.bean.BeanUtil;
import com.ds.cockpit.screen.common.annotation.Log;
import com.ds.cockpit.screen.common.core.controller.BaseController;
import com.ds.cockpit.screen.common.core.domain.AjaxResult;
import com.ds.cockpit.screen.common.core.domain.entity.GacEvaluationAnalysis;
import com.ds.cockpit.screen.common.core.domain.entity.vo.GacEvaluationAnalysisVo;
import com.ds.cockpit.screen.common.core.page.TableDataInfo;
import com.ds.cockpit.screen.common.enums.BusinessType;
import com.ds.cockpit.screen.common.utils.StringUtils;
import com.ds.cockpit.screen.framework.config.ServerConfig;
import com.ds.cockpit.screen.system.domain.vo.SSOUserInfoResVo;
import com.ds.cockpit.screen.system.service.IGacEvaluationAnalysisService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import javax.servlet.http.HttpServletRequest;
import java.util.List;

/**
 * 评价分析
 * 
 * @author
 */
@RestController
@RequestMapping("/gac/evaluation/analysis")
public class GacEvaluationAnalysisController extends BaseController
{
    @Autowired
    private IGacEvaluationAnalysisService gacEvaluationAnalysisService;

    @Autowired
    private ServerConfig serverConfig;

    private static final String FILE_DELIMETER = ",";

    /**
     * 获取数据列表
     */
    @PostMapping("/list")
    @Log(title = "评价分析", businessType = BusinessType.OTHER)
    public TableDataInfo list(HttpServletRequest request, @RequestBody GacEvaluationAnalysis gacEvaluationAnalysis) throws Exception {
        gacEvaluationAnalysisService.checkArgument(request);
        List<GacEvaluationAnalysis> list = gacEvaluationAnalysisService.selectListBy(request, gacEvaluationAnalysis);
        return getDataTable(list);
    }


    /**
     * 新增评价分析-简单文本
     */

    @Log(title = "评价分析", businessType = BusinessType.INSERT)
    @PostMapping("/add")
    public AjaxResult add(HttpServletRequest request, @RequestBody GacEvaluationAnalysis gacEvaluationAnalysis) throws Exception {
        gacEvaluationAnalysisService.checkArgument(request);
        return toAjax(gacEvaluationAnalysisService.addEvaluationAnalysis(request, gacEvaluationAnalysis));
    }

    /**
     * 新增评价分析-简单文本
     */
    @Log(title = "评价分析上传新增与提交", businessType = BusinessType.INSERT)
    @PostMapping("/submit")
    public AjaxResult submit(HttpServletRequest request, @RequestBody GacEvaluationAnalysis gacEvaluationAnalysis)
    {
        return toAjax(gacEvaluationAnalysisService.addEvaluationAnalysis(request, gacEvaluationAnalysis));
    }

    /**
     * 评价分析-清除文件
     */
    @Log(title = "评价分析-清除文件", businessType = BusinessType.UPDATE)
    @PostMapping("/deleteFiles")
    public AjaxResult deleteFiles(HttpServletRequest request, @RequestParam("id") String id)
    {
        return toAjax(gacEvaluationAnalysisService.deleteFiles(request, id));
    }

    /**
     * 新增评价分析-简单文本
     */
    //@Log(title = "评价分析上传新增与提交", businessType = BusinessType.INSERT)
    //@PostMapping("/submitAndAdd")
    public AjaxResult submit(HttpServletRequest request, @RequestBody GacEvaluationAnalysisVo gacEvaluationAnalysisVo) throws Exception {
        gacEvaluationAnalysisService.checkArgument(request);
        // 文本评价
        if(StringUtils.isNotEmpty(gacEvaluationAnalysisVo.getEvaluationAnalysis())){
            GacEvaluationAnalysis gacEvaluationAnalysis = new GacEvaluationAnalysis();
            BeanUtil.copyProperties(gacEvaluationAnalysisVo, gacEvaluationAnalysis);
            int insert = gacEvaluationAnalysisService.addEvaluationAnalysis(request, gacEvaluationAnalysis);
            if(insert > 0){
                return  success(gacEvaluationAnalysis);
            }
        }else{
            error(StringUtils.format("评价分析为空，未获取到数据。"));
        }
        return error();
    }

    /**
     * 新增评价分析-简单文本
     */
    @Log(title = "评价分析上传新增与提交", businessType = BusinessType.INSERT)
    @PostMapping("/submitAndAddList")
    public AjaxResult submitList(@RequestBody List<GacEvaluationAnalysisVo> gacEvaluationAnalysisVos, HttpServletRequest request) throws Exception {
        gacEvaluationAnalysisService.checkArgument(request);
        int inserts = 0;
        for (GacEvaluationAnalysisVo gacEvaluationAnalysisVo : gacEvaluationAnalysisVos) {
            if(StringUtils.isEmpty(gacEvaluationAnalysisVo.getEvaluationAnalysis()) &&
                    ( StringUtils.isEmpty(gacEvaluationAnalysisVo.getEvaluationAnalysisFile()))){
                return error(StringUtils.format("评价分析文本评价或文件上传需至少有一项！"));
            }

            // 文本评价
            if(StringUtils.isNotEmpty(gacEvaluationAnalysisVo.getEvaluationAnalysis()) ||
                    StringUtils.isNotEmpty(gacEvaluationAnalysisVo.getEvaluationAnalysisFile())){
                GacEvaluationAnalysis gacEvaluationAnalysis = new GacEvaluationAnalysis();
                BeanUtil.copyProperties(gacEvaluationAnalysisVo, gacEvaluationAnalysis);
                int insert = gacEvaluationAnalysisService.addEvaluationAnalysis(request, gacEvaluationAnalysis);
                if(insert > 0){
                    inserts = inserts+ insert;
                }
            }else{
                error(StringUtils.format("评价分析为空，未获取到数据。"));
            }
        }
        if(inserts > 0){
            return success(inserts);
        }else{
            return error();
        }
    }

    /**
     * token解析
     */
    @GetMapping("/token")
    //@Log(title = "token解析", businessType = BusinessType.OTHER)
    public AjaxResult tokenJwt(HttpServletRequest request){
        try {
            SSOUserInfoResVo userInfoResVo = gacEvaluationAnalysisService.checkArgument(request);
            if(userInfoResVo != null ){
                return success(userInfoResVo);
            }else{
                return error("解析用户token失败");
            }
        } catch (Exception e) {
            e.printStackTrace();
            return error("解析用户token失败");
        }
    }



}
