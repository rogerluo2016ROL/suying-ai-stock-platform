package com.ds.cockpit.screen.common.constant;

/**
 * @program: daily
 * @ClassName ApiResponse
 * @description: 错误码接口
 * @author: lukx
 * @create: 2022-04-26 16:51
 * @Version 1.0
 **/
public interface IStatus {

    /**
     * 状态码
     *
     * @return 状态码
     */
    Integer getCode();

    /**
     * 返回信息
     *
     * @return 返回信息
     */
    String getMessage();

}