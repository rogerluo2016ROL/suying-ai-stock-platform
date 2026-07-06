package com.ds.cockpit.screen.web.task;

import cn.hutool.core.date.DateUtil;
import com.ds.cockpit.screen.system.service.GacAIDifySteamService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import javax.annotation.Resource;

/**
 * @Author: ZhouHong
 * @Date: 2025-06-16 上午 11:42
 */
@Component
@Slf4j
public class AISplitWordsAnalysisTask {

    @Resource
    private GacAIDifySteamService gacAIDifySteamService;

    @Scheduled(cron = "0 59 23 * * ?")
    //@Scheduled(cron = "0 0/1 * * * ?")
    public void timeOneCheck() {
        log.info("AI分词补偿机制-定时任务start{}", DateUtil.date());
        try{
            gacAIDifySteamService.AISplitWordsRetryAnalysis();
        }catch (Exception e){
            log.info("消息中心数据分析-定时任务error-end{}",DateUtil.date());
            log.error("消息中心数据分析失败：{}", e.getMessage());
            log.error(e.toString());
        }
        log.info("AI分词补偿机制-定时任务end{}",DateUtil.date());
    }

}
