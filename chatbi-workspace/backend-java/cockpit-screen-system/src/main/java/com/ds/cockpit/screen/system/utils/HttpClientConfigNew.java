package com.ds.cockpit.screen.system.utils;

import io.netty.channel.ChannelOption;
// import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

import java.time.Duration;

/**
 * @Author: ZhouHong
 * @Date: 2025-06-17 上午 10:02
 */
//@Configuration
public class HttpClientConfigNew {

    private static final int RESPONSE_TIMEOUT_SECONDS = 6000;
    private static final int CONNECT_TIMEOUT_MILLIS = 5000000;
    private static final int MAX_IN_MEMORY_SIZE = 100 * 1024 * 1024;

    public static HttpClient createHttpClient() {
        return HttpClient.create()
                .responseTimeout(Duration.ofSeconds(RESPONSE_TIMEOUT_SECONDS)) // 响应超时时间:ml-citation{ref="4" data="citationList"}
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, CONNECT_TIMEOUT_MILLIS); // 连接超时
    }

    public static WebClient createWebClient() {
        return WebClient.builder()
                .clientConnector(new ReactorClientHttpConnector(createHttpClient()))
                .codecs(config -> config.defaultCodecs()
                        .maxInMemorySize(MAX_IN_MEMORY_SIZE)) // 提升缓冲区容量:ml-citation{ref="5" data="citationList"}
                .build();
    }
}
