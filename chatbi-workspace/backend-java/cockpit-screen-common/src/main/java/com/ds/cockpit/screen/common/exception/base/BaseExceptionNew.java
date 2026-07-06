package com.ds.cockpit.screen.common.exception.base;

import com.ds.cockpit.screen.common.constant.Status;
import lombok.Data;

/**
 * @program: daily
 * @ClassName BaseException
 * @description: 异常基类
 * @author: lukx
 * @create: 2022-04-27 14:33
 * @Version 1.0
 **/
@Data
public class BaseExceptionNew extends RuntimeException {

    private static final long serialVersionUID = 1L;

    private Integer code;
    private String message;
    private Object data;

    public BaseExceptionNew(Status status) {
        super(status.getMessage());
        this.code = status.getCode();
        this.message = status.getMessage();
    }

    public BaseExceptionNew(Status status, Object data) {
        this(status);
        this.data = data;
    }

    public BaseExceptionNew(Integer code, String message) {
        super(message);
        this.code = code;
        this.message = message;
    }

    public BaseExceptionNew(Integer code, String message, Object data) {
        this(code, message);
        this.data = data;
    }
}
