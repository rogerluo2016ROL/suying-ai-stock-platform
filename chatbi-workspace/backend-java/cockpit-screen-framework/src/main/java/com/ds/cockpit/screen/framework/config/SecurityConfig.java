package com.ds.cockpit.screen.framework.config;

import com.ds.cockpit.screen.framework.config.properties.PermitAllUrlProperties;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

import javax.annotation.Resource;
import java.util.Arrays;

/**
 * @Author: ZhouHong
 * @Date: 2025-01-17 下午 03:15
 */
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Autowired
    @Resource
    private TokenAuthenticationFilter tokenAuthenticationFilter;

    /**
     * 允许匿名访问的地址
     */
    @Autowired
    private PermitAllUrlProperties permitAllUrl;

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
                // CSRF禁用，因为不使用session
                .csrf(csrf -> csrf.disable())
                .cors(cors -> cors.configurationSource(corsConfigurationSource()))
                // 禁用HTTP响应标头
                .headers((headersCustomizer) -> {
                    headersCustomizer.cacheControl(cache -> cache.disable()).frameOptions(options -> options.sameOrigin());
                })
                .authorizeHttpRequests((requests) -> {
                    permitAllUrl.getUrls().forEach(url -> requests.antMatchers(url).permitAll());
                    // 对于登录login 注册register 验证码captchaImage 允许匿名访问
                    requests.antMatchers("/login", "/register", "/captchaImage", "/platform",
                                    "/api/v1/chatbi/**", "/gac/dify/ai/**").permitAll()
                            // 静态资源，可匿名访问
                            .antMatchers(HttpMethod.GET, "/", "/*.html", "/**/*.html", "/**/*.css", "/**/*.js", "/profile/**").permitAll()
                            //.antMatchers("/swagger-ui.html", "/swagger-resources/**", "/webjars/**", "/*/api-docs", "/druid/**").permitAll()
                            // 除上面外的所有请求全部需要鉴权认证
                            .anyRequest().authenticated();
                })
                .addFilterBefore(tokenAuthenticationFilter, org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    @Bean
    public CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOriginPatterns(Arrays.asList("*"));
        configuration.setAllowedMethods(Arrays.asList("GET", "POST", "PUT", "DELETE", "OPTIONS"));
        configuration.setAllowedHeaders(Arrays.asList("*"));
        configuration.setAllowCredentials(false);

        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/v1/chatbi/**", configuration);
        source.registerCorsConfiguration("/gac/dify/ai/**", configuration);
        return source;
    }

    /**
     * 身份验证实现
     */
    /*@Bean
    public AuthenticationManager authenticationManager()
    {
        return null;
    }*/
}
