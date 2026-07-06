package com.ds.cockpit.screen.system.utils;

import com.alibaba.fastjson2.JSONObject;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.ClientHttpResponse;
import org.springframework.http.converter.FormHttpMessageConverter;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.ResponseErrorHandler;
import org.springframework.web.client.RestTemplate;

import javax.servlet.http.HttpServletResponse;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * https://www.cnblogs.com/hujunzheng/p/6018505.html
 *
 * <p>https://my.oschina.net/u/4136962/blog/3175408
 *
 * <p>https://www.cnblogs.com/victorbu/p/12708340.html
 *
 * <p>https://blog.csdn.net/smilefyx/article/details/79006324 @Title:
 * RestTemplateUtils.java @Prject: sensorsdata @Package:
 * com.springboottest.sensorsdata.utils @Description:
 *
 * @author: hujunzheng
 * @date: 2017年4月20日 下午2:07:18
 * @version: V1.0
 */
@Slf4j
public class RestTemplateUtils {

  /**
   * @ClassName: DefaultResponseErrorHandler @Description:
   *
   * @author: hujunzheng
   * @date: 2017年4月20日 下午2:15:27
   */
  private static class DefaultResponseErrorHandler implements ResponseErrorHandler {

    @Override
    public boolean hasError(ClientHttpResponse response) throws IOException {
      return response.getStatusCode().value() != HttpServletResponse.SC_OK;
    }

    @Override
    public void handleError(ClientHttpResponse response) throws IOException {
      BufferedReader br = new BufferedReader(new InputStreamReader(response.getBody()));
      StringBuilder sb = new StringBuilder();
      String str = null;
      while ((str = br.readLine()) != null) {
        sb.append(str);
      }
      try {
        throw new Exception(sb.toString());
      } catch (Exception e) {
        log.error("错误解析异常", e);
      }
    }
  }

  /**
   * post 请求体中对象参数。 设置header头
   *
   * @param url
   * @param headers 请求头内容
   * @param requestBody 请求体 对象内容
   * @param responseType 响应对象
   * @param <T>
   * @return
   */
  public static <T> ResponseEntity<T> postBodyForHeader(
          String url, HttpHeaders headers, Object requestBody, Class<T> responseType) {

    RestTemplate restTemplate = SpringContextUtils.getBean(RestTemplate.class);
    headers.setContentType(MediaType.APPLICATION_JSON);
    HttpEntity httpEntity = new HttpEntity<>(requestBody, headers);

    return restTemplate.postForEntity(url, httpEntity, responseType);
  }

  /**
   * get 请求，无参指定header的请求
   *
   * @param url
   * @param headers
   * @param responseType
   * @param <T>
   * @return
   */
  public static <T> T getForHeaderNoParam(String url, HttpHeaders headers, Class<T> responseType) {
    RestTemplate restTemplate = SpringContextUtils.getBean(RestTemplate.class);

    HttpEntity httpEntity = new HttpEntity<>(headers);
    return restTemplate.getForObject(url, responseType, httpEntity);
  }

  /**
   * get 请求 带参数， param方式的参数【参数是拼接在url路径上】
   *
   * @param url
   * @param params 请求参数
   * @param responseType
   * @param <T>
   * @return
   */
  public static <T> T getByParam(String url, Map<String, Object> params, Class<T> responseType) {
    RestTemplate restTemplate = SpringContextUtils.getBean(RestTemplate.class);

    return restTemplate.getForObject(url, responseType, params);
  }

  /**
   * get 请求带上参数，同时 带上 header 头
   *
   * @param url 请求路径，路径是带上请求参数的比如 http://....../qwe?sig=123......"
   * @param headers
   * @param responseType
   * @param <T>
   * @return
   */
  public static <T> ResponseEntity<T> getForHeaderAndParam(
          String url, HttpHeaders headers, Class<T> responseType) {
    RestTemplate restTemplate = SpringContextUtils.getBean(RestTemplate.class);

    HttpEntity httpEntity = new HttpEntity<>(headers);

    return restTemplate.exchange(url, HttpMethod.GET, httpEntity, responseType);
  }

  /**
   * @param url
   * @param params
   * @return @Title: get
   * @author: hujunzheng @Description: TODO
   * @return: String
   */
  public static String get(String url, JSONObject params) {
    //    RestTemplate restTemplate = new RestTemplate();
    RestTemplate restTemplate = SpringContextUtils.getBean(RestTemplate.class);
    restTemplate.setErrorHandler(new DefaultResponseErrorHandler());
    String response =
        restTemplate.getForObject(expandURL(url, params.keySet()), String.class, params);
    return response;
  }

  /**
   * @param url
   * @param params 请求body json对象
   * @param mediaType： Content-Type 内容
   * @return @Title: post
   * @author: hujunzheng @Description: 将参数都拼接在url之后
   * @return: String
   */
  public static String post(String url, JSONObject params, MediaType mediaType) {
    //    RestTemplate restTemplate = new RestTemplate();
    RestTemplate restTemplate = SpringContextUtils.getBean(RestTemplate.class);
    // 拿到header信息
    HttpHeaders requestHeaders = new HttpHeaders();
    requestHeaders.setContentType(mediaType);
    HttpEntity<JSONObject> requestEntity =
        (mediaType == MediaType.APPLICATION_JSON || mediaType == MediaType.APPLICATION_JSON_UTF8)
            ? new HttpEntity<JSONObject>(params, requestHeaders)
            : new HttpEntity<JSONObject>(null, requestHeaders);
    restTemplate.setErrorHandler(new DefaultResponseErrorHandler());
    String result =
        (mediaType == MediaType.APPLICATION_JSON || mediaType == MediaType.APPLICATION_JSON_UTF8)
            ? restTemplate.postForObject(url, requestEntity, String.class)
            : restTemplate.postForObject(
                expandURL(url, params.keySet()), requestEntity, String.class, params);
    return result;
  }

  /**
   * @param url
   * @param params
   * @param mediaType
   * @param clz
   * @return @Title: post
   * @author: hujunzheng @Description: 发送json或者form格式数据
   * @return: String
   */
  public static <T> T post(String url, JSONObject params, MediaType mediaType, Class<T> clz) {
    //    RestTemplate restTemplate = new RestTemplate();
    RestTemplate restTemplate = SpringContextUtils.getBean(RestTemplate.class);

    // 这是为 MediaType.APPLICATION_FORM_URLENCODED 格式HttpEntity 数据 添加转换器
    // 还有就是，如果是APPLICATION_FORM_URLENCODED方式发送post请求，
    // 也可以直接HttpHeaders requestHeaders = new HttpHeaders(createMultiValueMap(params)，true)，就不用增加转换器了
    restTemplate.getMessageConverters().add(new FormHttpMessageConverter());
    // 设置header信息
    HttpHeaders requestHeaders = new HttpHeaders();
    requestHeaders.setContentType(mediaType);

    HttpEntity<?> requestEntity =
        (mediaType == MediaType.APPLICATION_JSON || mediaType == MediaType.APPLICATION_JSON_UTF8)
            ? new HttpEntity<JSONObject>(params, requestHeaders)
            : (mediaType == MediaType.APPLICATION_FORM_URLENCODED
                ? new HttpEntity<MultiValueMap>(createMultiValueMap(params), requestHeaders)
                : new HttpEntity<>(null, requestHeaders));

    restTemplate.setErrorHandler(new DefaultResponseErrorHandler());
    T result =
        (mediaType == MediaType.APPLICATION_JSON || mediaType == MediaType.APPLICATION_JSON_UTF8)
            ? restTemplate.postForObject(url, requestEntity, clz)
            : restTemplate.postForObject(
                mediaType == MediaType.APPLICATION_FORM_URLENCODED
                    ? url
                    : expandURL(url, params.keySet()),
                requestEntity,
                clz,
                params);

    return result;
  }

  private static MultiValueMap<String, String> createMultiValueMap(JSONObject params) {
    MultiValueMap<String, String> map = new LinkedMultiValueMap<>();
    for (String key : params.keySet()) {
      if (params.get(key) instanceof List) {
        for (Iterator<String> it = ((List<String>) params.get(key)).iterator(); it.hasNext(); ) {
          String value = it.next();
          map.add(key, value);
        }
      } else {
        map.add(key, params.getString(key));
      }
    }
    return map;
  }

  /**
   * @param url
   * @param keys
   * @return @Title: expandURL
   * @author: hujunzheng @Description: TODO
   * @return: String
   */
  private static String expandURL(String url, Set<?> keys) {
    final Pattern QUERY_PARAM_PATTERN = Pattern.compile("([^&=]+)(=?)([^&]+)?");
    Matcher mc = QUERY_PARAM_PATTERN.matcher(url);
    StringBuilder sb = new StringBuilder(url);
    if (mc.find()) {
      sb.append("&");
    } else {
      sb.append("?");
    }

    for (Object key : keys) {
      sb.append(key).append("=").append("{").append(key).append("}").append("&");
    }
    return sb.deleteCharAt(sb.length() - 1).toString();
  }
}
