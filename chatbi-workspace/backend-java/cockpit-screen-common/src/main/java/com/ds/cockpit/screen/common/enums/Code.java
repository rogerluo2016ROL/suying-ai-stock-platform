package com.ds.cockpit.screen.common.enums;

/** 功能：系统的返回状态码和错误码说明 */
public enum Code {
  // 系统状态码
  ReqSuccess(200, "执行成功"),
  ReqLostParams(300, "参数为空或不完整"),
  ReqIsExist(301, "已存在相同的记录"),
  ReqFailure(444, "执行失败"),
  SSOFailure(4455, "token获取失败"),
  SSOUSERMSG(4456, "SSO用户信息获取失败"),
  JWTERRORMSG(4457, "jwt已经失效或无效的jwt"),
  TOKENERRORMSG(4458, "accessToken已经失效或无效的accessToken"),

  // 用户和接口权限状态码
  ApiNotLogin(400, "用户未登录"),
  UnAuthorized(401, "权限不足"),
  ApiForbidden(403, "请求被禁止"),
  ApiNotFound(404, "不存在"),
  ApiStop(405, "API已停用"),
  ApiUnavailable(406, "服务不可用"),
  ApiTimeOut(407, "请求超时"),
  ApiNotPermissions(408, "用户权限不足"),
  ApiCallLimited(409, "超过调用次数"),
  ApiInvalidSign(410, "签名错误"),
  ApiInvalidReplay(411, "重复请求"),

  // 常见错误码
  ErrorSystem(500, "系统繁忙，请稍后重试！"),
  ErrorFormat(501, "格式错误"),
  ErrorType(502, "类型错误"),
  ErrorOverLength(503, "超过规定长度"),
  ErrorEmail(504, "邮箱格式错误"),
  ErrorPhone(505, "手机号码格式错误"),
  ErrorImageCodeNeed(506, "需要输入图形验证码"),
  ErrorImageCode(507, "图形验证码错误"),
  ErrorPhoneCode(508, "手机验证码错误"),

  // 永洪错误码
  ErrorYHFail(600, "永洪响应失败"),
  ErrorYHRequestFail(601, "永洪请求失败"),
  ErrorYHREPOSEFail(701, "此文件和文件夹已经存在"),

  // 部分操作成功
  PartSuccess(800, "部分操作成功"),
  ;

  private int code;
  private String msg;

  Code(int code, String msg) {
    this.code = code;
    this.msg = msg;
  }

  public int getCode() {
    return code;
  }

  public String getMsg() {
    return msg;
  }
}
