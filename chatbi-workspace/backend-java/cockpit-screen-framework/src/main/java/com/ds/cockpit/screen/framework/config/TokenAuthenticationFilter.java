package com.ds.cockpit.screen.framework.config;

import com.ds.cockpit.screen.system.domain.vo.SSOUserInfoResVo;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import javax.annotation.Resource;
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Collections;
import java.util.Arrays;
import java.util.List;

/**
 * @Author: ZhouHong
 * @Date: 2025-01-17 下午 03:11
 */
@Slf4j
@Component
public class TokenAuthenticationFilter extends OncePerRequestFilter {

    private static final List<String> PUBLIC_PATH_PREFIXES = Arrays.asList(
            "/api/v1/chatbi/",
            "/gac/dify/ai/",
            "/login",
            "/register",
            "/captchaImage",
            "/platform"
    );

    @Autowired
    @Resource
    private TokenValidationService tokenValidationService;

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getServletPath();
        return PUBLIC_PATH_PREFIXES.stream().anyMatch(path::startsWith)
                || path.endsWith(".html")
                || path.endsWith(".css")
                || path.endsWith(".js");
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String token = request.getHeader("Authorization");
        if (token != null) {
            try {
                SSOUserInfoResVo userInfo = tokenValidationService.validateToken(token);

                // 创建认证对象
                UsernamePasswordAuthenticationToken authentication = new UsernamePasswordAuthenticationToken(
                        userInfo.getAccount(),
                        null,
                        Collections.emptyList()
                );
                authentication.setDetails(new WebAuthenticationDetailsSource().buildDetails(request));

                // 设置认证对象到安全上下文中
                SecurityContextHolder.getContext().setAuthentication(authentication);
            } catch (Exception e) {
                // 验证失败，返回401状态码
                response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                return;
            }
        }else{
            log.info("请求头认证数据为空");
            // 验证失败，返回401状态码
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }
        log.info("请求头认证");
        // 继续过滤器链
        filterChain.doFilter(request, response);
    }
}
