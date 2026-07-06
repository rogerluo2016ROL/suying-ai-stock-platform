package com.ds.cockpit.screen.system.utils;

import com.ds.cockpit.screen.common.enums.Code;
import com.ds.cockpit.screen.common.exception.CommonException;
import org.apache.commons.lang3.StringUtils;

import java.util.List;

/** 功能：参数检查的工具类 */
public class PreconditionsUtils {

  /**
   * 检查condition是否为真，为真抛出异常
   *
   * @param condition 条件
   */
  public static void checkArgument(boolean condition) {
    checkArgument(condition, "参数错误");
  }

  /**
   * 检查condition是否为真，为真抛出异常
   *
   * @param condition 条件
   * @param msg 错误消息
   */
  public static void checkArgument(boolean condition, String msg) {
    checkArgument(condition, msg, Code.ReqFailure);
  }

  /**
   * 检查condition是否为真，为真抛出异常
   *
   * @param condition 条件
   * @param msg 错误消息
   * @param code 错误类型
   */
  public static void checkArgument(boolean condition, String msg, Code code) {
    if (condition) {
      throw new CommonException(code, msg);
    }
  }

  /**
   * 检查condition是否为真，为真抛出异常
   *
   * @param condition 条件
   * @param code 错误类型 , msg 取code 里面的
   */
  public static void checkArgument(boolean condition, Code code) {
    if (condition) {
      throw new CommonException(code, code.getMsg());
    }
  }

  /**
   * 检查obj是否为空，为空抛出异常。
   *
   * @param obj 对象
   */
  public static void checkNotNull(Object obj) {
    checkNotNull(obj, "参数不能为空");
  }

  /**
   * 检查condition是否为空，为空抛出异常。
   *
   * @param obj 对象
   * @param msg 错误消息
   */
  public static void checkNotNull(Object obj, String msg) {
    checkNotNull(obj, msg, Code.ReqLostParams);
  }

  /**
   * 检查condition是否为空，为空抛出异常。
   *
   * @param obj 对象
   * @param code Code类型
   */
  public static void checkNotNull(Object obj, Code code) {
    checkNotNull(obj, code.getMsg(), code);
  }

  /**
   * 检查condition是否为空，为空抛出异常。
   *
   * @param obj 对象
   * @param msg 错误消息
   * @param code 错误类型
   */
  public static void checkNotNull(Object obj, String msg, Code code) {
    if (obj == null) {
      throw new CommonException(code, msg);
    }
    if (obj instanceof String) {
      String str = (String) obj;
      if (StringUtils.isBlank(str)) {
        throw new CommonException(code, msg);
      }
    }
    if (obj instanceof Long) {
      Long l = (Long) obj;
      // 这个是 对应主键来判断的，通常来说 主键值不能为零
      if (l == null || l.longValue() == 0) {
        throw new CommonException(code, msg);
      }
    }
    // 判断长整型数组是否为空，对应主键数组情况
    if (obj instanceof Long[]) {
      Long[] list = (Long[]) obj;
      if(list.length == 0) {
        throw new CommonException(code, msg);
      }
    }
    if (obj instanceof List) {
      List list = (List) obj;
      if (list.size() == 0) {
        throw new CommonException(code, msg);
      }
    }
    if (obj instanceof Long[]) {
      Long[] arrays = (Long[]) obj;
      if (arrays.length == 0) {
        throw new CommonException(code, msg);
      }
    }
  }

  public static boolean isBlank(Long id) {
    if (id != null) {
      return false;
    }
    return true;
  }

  /**
   * token获取失败
   *
   * @param obj
   * @param msg
   */
  public static void errorTokenObjMesage(Object obj, String msg) {
    errorTokenObjMesage(obj, msg, Code.SSOFailure);
  }

  /**
   * token获取失败
   *
   * @param obj
   * @param msg
   * @param code
   */
  public static void errorTokenObjMesage(Object obj, String msg, Code code) {
    if (obj == null) {
      throw new CommonException(code, msg);
    }
  }

  /**
   * token获取失败
   *
   * @param msg
   */
  public static void errorTokenMesage(String msg) {
    errorTokenMesage(msg, Code.SSOFailure);
  }

  /**
   * token获取失败
   *
   * @param msg
   * @param code
   */
  public static void errorTokenMesage(String msg, Code code) {
    throw new CommonException(code, msg);
  }



  /**
   * SSO用户信息获取失败
   *
   * @param obj
   * @param msg
   */
  public static void errorUserObjMsg(Object obj, String msg) {
    errorUserObjMsg(obj, msg, Code.SSOUSERMSG);
  }

  /**
   * SSO用户信息获取失败
   *
   * @param obj
   * @param msg
   * @param code
   */
  public static void errorUserObjMsg(Object obj, String msg, Code code) {
    if (obj == null) {
      throw new CommonException(code, msg);
    }
  }

  /**
   * SSO用户信息获取失败
   *
   * @param msg
   */
  public static void errorUserMsg(String msg) {
    errorUserMsg(msg, Code.SSOUSERMSG);
  }

  /**
   * SSO用户信息获取失败
   *
   * @param msg
   * @param code
   */
  public static void errorUserMsg(String msg, Code code) {
    throw new CommonException(code, msg);
  }

  /**
   * jwt失效或无效的jwt
   *
   * @param msg
   */
  public static void errorJwtMesage(String msg) {
    errorJwtMesage(msg, Code.JWTERRORMSG);
  }

  /**
   * jwt失效或无效的jwt
   *
   * @param msg
   * @param code
   */
  public static void errorJwtMesage(String msg, Code code) {
    throw new CommonException(code, msg);
  }

  /**
   * accessToken失效或无效的accessToken
   *
   * @param msg
   */
  public static void errorAccessTokenMesage(String msg) {
    errorAccessTokenMesage(msg, Code.TOKENERRORMSG);
  }

  /**
   * accessToken失效或无效的accessToken
   *
   * @param msg
   * @param code
   */
  public static void errorAccessTokenMesage(String msg, Code code) {
    throw new CommonException(code, msg);
  }
}
