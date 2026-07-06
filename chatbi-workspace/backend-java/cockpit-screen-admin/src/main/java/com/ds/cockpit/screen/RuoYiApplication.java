package com.ds.cockpit.screen;

import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * 启动程序
 * 
 * @author ruoyi
 */
@Slf4j
@EnableScheduling
@SpringBootApplication(exclude = { DataSourceAutoConfiguration.class })
public class RuoYiApplication
{
    public static void main(String[] args)
    {
        // System.setProperty("spring.devtools.restart.enabled", "false");
        SpringApplication.run(RuoYiApplication.class, args);
        log.info("(♥◠‿◠)ﾉﾞ  集团整合驾驶舱-评价分析/埋点/企微移动系统管理/AI服务-启动成功   ლ(´ڡ`ლ)ﾞ  ");
        log.info("\n" +
                "   ______       _        ______  \n" +
                " .' ___  |     / \\     .' ___  | \n" +
                "/ .'   \\_|    / _ \\   / .'   \\_| \n" +
                "| |   ____   / ___ \\  | |        \n" +
                "\\ `.___]  |_/ /   \\ \\_\\ `.___.'\\ \n" +
                " `._____.'|____| |____|`.____ .' \n" +
                "                                 \n");
    }
}
