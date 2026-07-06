package com.ds.cockpit.screen.common.utils;

/**
 * @Author: ZhouHong
 * @Date: 2025-07-08 下午 03:23
 */
public class CsvEscapeUtils {
    private static final char QUOTE = '\"';
    private static final String ESCAPED_QUOTE = "\"\"";

    /**
     * 转义CSV字段中的特殊字符
     * @param value 原始字段值
     * @return 转义后的安全字符串
     */
    public static String escapeField(String value) {
        if (value == null) {return "";}

        // 1. 优先转义内部双引号
        String escaped = value.replace(String.valueOf(QUOTE), ESCAPED_QUOTE);

        // 2. 检查是否需要包裹整个字段
        if (needsWrapping(escaped)) {
            escaped = QUOTE + escaped + QUOTE;
        }
        return escaped;
    }

    /**
     * 判断字段是否需要引号包裹
     */
    private static boolean needsWrapping(String value) {
        return value.contains(",") ||
                value.contains("\n") ||
                value.contains("\r") ||
                value.trim().length() != value.length();
    }
}
