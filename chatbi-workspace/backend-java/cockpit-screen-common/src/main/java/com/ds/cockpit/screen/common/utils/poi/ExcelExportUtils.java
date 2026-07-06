package com.ds.cockpit.screen.common.utils.poi;

import cn.hutool.poi.excel.ExcelUtil;
import cn.hutool.poi.excel.ExcelWriter;
import javax.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.List;

/**
 * @Author: ZhouHong
 * @Date: 2025-07-08 下午 03:34
 */
public class ExcelExportUtils {
    /**
     * 全量数据导出（适合数据量在10万条以内）
     * @param response HTTP响应
     * @param fileName 输出文件名（无需后缀）
     * @param dataList 数据集
     */
    public static void exportAllData(HttpServletResponse response,
                                     String fileName,
                                     List<?> dataList) throws IOException {
        // 1. 初始化ExcelWriter（自动检测数据量选择SXSSF模式）
        ExcelWriter writer = ExcelUtil.getWriterWithSheet("Sheet1");

        try {
            // 2. 设置响应头（解决中文乱码）
            String encodedName = new String(fileName.getBytes("GBK"), "ISO8859-1");
            response.setContentType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
            response.setHeader("Content-Disposition", "attachment;filename=" + encodedName + ".xlsx");

            // 3. 批量写入数据（Hutool自动优化内存）
            writer.write(dataList, true);

            // 4. 输出到客户端
            writer.flush(response.getOutputStream(), true);
        } finally {
            writer.close();
        }
    }

    /**
     * 大字段安全处理（防XSS+长度控制）
     */
    public static String safeField(Object field) {
        if (field == null) return "";
        String str = field.toString()
                .replace("<", "&lt;")
                .replace(">", "&gt;");
        return str.length() > 32767 ? str.substring(0, 30000) + "..." : str;
    }
}
