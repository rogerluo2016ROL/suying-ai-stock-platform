package com.ds.cockpit.screen.common.response;

import com.ds.cockpit.screen.common.constant.IStatus;
import com.ds.cockpit.screen.common.constant.Status;
import com.ds.cockpit.screen.common.exception.base.BaseExceptionNew;
import org.springframework.stereotype.Component;

/**
 * @program: aion-daily
 * @ClassName ApiResponseFactory
 * @description:
 * @author: lukx
 * @create: 2022-06-08 10:49
 * @Version 1.0
 **/
@SuppressWarnings({"rawtypes", "unchecked"})
@Component
public class ApiResponseFactory {

    /**
     * 构造一个自定义的API返回
     *
     * @param code    状态码
     * @param message 返回内容
     * @param data    返回数据
     * @return ApiResponse
     */
    public ApiResponse of(Integer code, String message, Object data) {
        return new ApiResponse(code, message, data);
    }

    /**
     * 构造一个成功且不带数据的API返回
     *
     * @return ApiResponse
     */
    public ApiResponse ofSuccess() {
        return ofSuccess(null);
    }

    /**
     * 构造一个成功且带数据的API返回
     *
     * @param data 返回数据
     * @return ApiResponse
     */
    public ApiResponse ofSuccess(Object data) {
        return ofStatus(Status.SUCCESS, data);
    }

    /**
     * 构造一个成功且自定义消息的API返回
     *
     * @param message 返回内容
     * @return ApiResponse
     */
    public ApiResponse ofMessage(String message) {
        return of(Status.SUCCESS.getCode(), message, null);
    }

    /**
     * 构造一个有状态的API返回
     *
     * @param status 状态 {@link Status}
     * @return ApiResponse
     */
    public ApiResponse ofStatus(Status status) {
        return ofStatus(status, null);
    }

    /**
     * 构造一个有状态且带数据的API返回
     *
     * @param status 状态 {@link IStatus}
     * @param data   返回数据
     * @return ApiResponse
     */
    public ApiResponse ofStatus(IStatus status, Object data) {
        return of(status.getCode(), status.getMessage(), data);
    }

    /**
     * 构造一个异常的API返回
     *
     * @param t   异常
     * @param <T> {@link BaseExceptionNew} 的子类
     * @return ApiResponse
     */
    public <T extends BaseExceptionNew> ApiResponse ofException(T t) {
        return of(t.getCode(), t.getMessage(), t.getData());
    }
}
