package com.ds.cockpit.screen.common.constant;

import com.ds.cockpit.screen.common.enums.WeChatErrorCode;
import lombok.Getter;

/**
 * @program: daily
 * @ClassName Constant
 * @description: 通用状态码
 * @author: lukx
 * @create: 2022-04-26 16:51
 * @Version 1.0
 **/
@Getter
public enum Status implements IStatus {

    /**
     * 操作成功！
     */
    SUCCESS(200, "success"),

    /**
     * 操作异常！
     */
    ERROR(500, "操作异常！"),

    /**
     * 请求不存在！
     */
    REQUEST_NOT_FOUND(404, "请求不存在！"),

    /**
     * 请求方式不支持！
     */
    HTTP_BAD_METHOD(405, "请求方式不支持！"),

    /**
     * 请求异常！
     */
    BAD_REQUEST(400, "请求异常！"),

    /**
     * 参数不匹配！
     */
    PARAM_NOT_MATCH(400, "参数不匹配！"),

    /**
     * 参数不能为空！
     */
    PARAM_NOT_NULL(400, "参数不能为空！"),

    /**
     * 企业微信ACCESS_TOKEN异常
     */
    WECHAT_ACCESS_TOKEN_ERROR(400, "企业微信ACCESS_TOKEN异常"),

    /**
     * 投资费
     */
    TZ_XCX_TZF(1, "TZ_XCX_TZF");

    /**
     * 状态码
     */
    private Integer code;

    /**
     * 返回信息
     */
    private String message;

    Status(Integer code, String message) {
        this.code = code;
        this.message = message;
    }

    Status(WeChatErrorCode weChatErrorCode) {
        this.code = weChatErrorCode.getErrorCode();
        this.message = message;
    }

    public static Status fromCode(Integer code) {
        Status[] statuses = Status.values();
        for (Status status : statuses) {
            if (status.getCode().equals(code)) {
                return status;
            }
        }
        return SUCCESS;
    }

    @Override
    public String toString() {
        return String.format(" Status:{code=%s, message=%s} ", getCode(), getMessage());
    }

}
