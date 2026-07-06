package com.ds.cockpit.screen.web.core.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurerAdapter;

import java.util.List;

/**
 * @Author: ZhouHong
 * @Date: 2025-06-25 下午 05:19
 */
@Configuration
public class SseConverterConfig extends WebMvcConfigurerAdapter {
    private final ThreadPoolTaskExecutor chatBIStreamExecutor = chatBIStreamExecutor();

    @Override
    public void configureMessageConverters(List<HttpMessageConverter<?>> converters) {
        converters.add(new MappingJackson2HttpMessageConverter() {
            @Override
            public boolean canWrite(Class<?> clazz, MediaType mediaType) {
                return super.canWrite(clazz, mediaType) ||
                        (mediaType != null && mediaType.includes(MediaType.TEXT_EVENT_STREAM));
            }
        });
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(chatBIStreamExecutor);
        configurer.setDefaultTimeout(65000);
    }

    private ThreadPoolTaskExecutor chatBIStreamExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("chatbi-sse-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(200);
        executor.initialize();
        return executor;
    }
}
