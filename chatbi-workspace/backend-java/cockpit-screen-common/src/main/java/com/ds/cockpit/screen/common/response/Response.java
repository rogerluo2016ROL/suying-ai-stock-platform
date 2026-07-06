package com.ds.cockpit.screen.common.response;

import com.ds.cockpit.screen.common.exception.base.BaseExceptionNew;
import org.springframework.beans.factory.annotation.Autowired;

/**
 * @program: aion-daily
 * @ClassName Response
 * @description:
 * @author: lukx
 * @create: 2022-06-08 10:54
 * @Version 1.0
 **/
public class Response<T extends Object> {

    @Autowired(required = false)
    protected ApiResponseFactory apiResponseFactory;

    protected ApiResponse<T> fail(BaseExceptionNew e, String msg) {
        return this.respone(e, msg, null);
    }

    protected ApiResponse<T> success() {
        return this.respone(null, null, null);
    }

    protected ApiResponse<T> success(Object data) {
        return this.respone(null, null, data);
    }

    protected ApiResponse<T> success(Object data, String mag) {
        return this.respone(null, mag, data);
    }

    protected ApiResponse<T> respone(BaseExceptionNew e, String msg, Object data) {
        if (e == null) {
            return this.apiResponseFactory.ofSuccess(data);
        }

        //log.error(msg, e);
        return this.apiResponseFactory.ofException(e);
    }
}
