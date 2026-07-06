package com.ds.cockpit.screen.system.utils;

import cn.hutool.core.date.DateTime;
import cn.hutool.core.date.DateUtil;

import java.text.SimpleDateFormat;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.temporal.TemporalAdjusters;
import java.util.Calendar;
import java.util.Date;
import java.util.LinkedList;

public class DateUtils {
    /**
     * 时间格式(yyyy-MM-dd HH:mm:ss)
     */
    public final static String DATE_TIME_PATTERN = "yyyy-MM-dd HH:mm:ss";

    /**
     * 时间格式(yyyyMMdd)
     */
    public final static String DATE_PATTERN_YYYY_MM_DD = "yyyyMMdd";

    /**
     * 时间格式(yyyyMM)
     */
    public final static String DATEPATTERN = "yyyyMM";

    /**
     * 时间格式(yyyy)
     */
    public final static String DATE_PATTERN_YYYY = "yyyy";


    public static String format(Date date, String pattern) {
        if (date != null) {
            SimpleDateFormat df = new SimpleDateFormat(pattern);
            return df.format(date);
        }
        return null;
    }

    public static LinkedList<String> getAllMonthForYear(String year) {
        LinkedList<String> months = new LinkedList<>();
        for (int i = 1; i <= 12; i++) {
            if (i < 10) {
                months.add(year + "0" + i);
                continue;
            }
            months.add(year + i);
        }
        return months;
    }

    //过去七天
    public static String getLastWeek(String date) {
        SimpleDateFormat format = new SimpleDateFormat(DATE_PATTERN_YYYY_MM_DD);
        Calendar c = Calendar.getInstance();
        c.setTime(DateUtil.parse(date));
        c.add(Calendar.DATE, -7);
        Date d = c.getTime();
        return format.format(d);
    }

    //过去一月
    public static String getLastMonth(String date) {
        SimpleDateFormat format = new SimpleDateFormat(DATE_PATTERN_YYYY_MM_DD);
        Calendar c = Calendar.getInstance();
        c.setTime(new Date());
        c.add(Calendar.MONTH, -1);
        Date m = c.getTime();
        return format.format(m);
    }

    //过去一年
    public static String getLastYear(String date) {
        SimpleDateFormat format = new SimpleDateFormat(DATE_PATTERN_YYYY_MM_DD);
        Calendar c = Calendar.getInstance();
        c.setTime(new Date());
        c.add(Calendar.YEAR, -1);
        Date y = c.getTime();
        return format.format(y);
    }

    // 根据offset偏移月份
    public static String getLastMonthByOffset(String str, int offset){
        DateTime date = DateUtil.parse(str, DATE_PATTERN_YYYY_MM_DD);
        DateTime lastMonth = DateUtil.offsetMonth(date, offset);
        String dateStr = DateUtil.format(lastMonth, DATE_PATTERN_YYYY_MM_DD);
        return dateStr;
    }

    // 根据offset偏移天数
    public static String getDayByOffset(String str, int offset){
        DateTime date = DateUtil.parse(str, DATE_PATTERN_YYYY_MM_DD);
        DateTime lastMonth = DateUtil.offsetDay(date, offset);
        String dateStr = DateUtil.format(lastMonth, DATE_PATTERN_YYYY_MM_DD);
        return dateStr;
    }

    // 获取月份的第一天
    public static String getFirstDayOfMonth(String date){
        LocalDate localDate = LocalDate.parse(date, DateTimeFormatter.ofPattern(DATE_PATTERN_YYYY_MM_DD));
        LocalDate localDateFirstDay = localDate.with(TemporalAdjusters.firstDayOfMonth());
        return localDateFirstDay.format(DateTimeFormatter.ofPattern(DATE_PATTERN_YYYY_MM_DD));
    }
    
    // 获取月份的最后一天
    public static String getLastDayOfMonth(String date){
        LocalDate localDate = LocalDate.parse(date, DateTimeFormatter.ofPattern(DATE_PATTERN_YYYY_MM_DD));
        LocalDate localDateLastDay = localDate.with(TemporalAdjusters.lastDayOfMonth());
        return localDateLastDay.format(DateTimeFormatter.ofPattern(DATE_PATTERN_YYYY_MM_DD));
    }

    // 获取周的第一天
    public static String getFirstDayOfWeek(String date){
        LocalDate localDate = LocalDate.parse(date, DateTimeFormatter.ofPattern(DATE_PATTERN_YYYY_MM_DD));
        LocalDate localDateFirstDay = localDate.with(localDate.with(DayOfWeek.MONDAY));
        return localDateFirstDay.format(DateTimeFormatter.ofPattern(DATE_PATTERN_YYYY_MM_DD));
    }
    // 获取周的最后一天
    public static String getLastDayOfWeek(String date){
        LocalDate localDate = LocalDate.parse(date, DateTimeFormatter.ofPattern(DATE_PATTERN_YYYY_MM_DD));
        LocalDate localDateFirstDay = localDate.with(localDate.with(DayOfWeek.SUNDAY));
        return localDateFirstDay.format(DateTimeFormatter.ofPattern(DATE_PATTERN_YYYY_MM_DD));
    }

    // 获取年的第一天
    public static String getFirstDayOfYear(String date){
        LocalDate localDate = LocalDate.parse(date, DateTimeFormatter.ofPattern(DATE_PATTERN_YYYY_MM_DD));
        LocalDate localDateFirstDay = localDate.with(localDate.with(TemporalAdjusters.firstDayOfYear()));
        return localDateFirstDay.format(DateTimeFormatter.ofPattern(DATE_PATTERN_YYYY_MM_DD));
    }
    // 获取年的最后一天
    public static String getLastDayOfYear(String date){
        LocalDate localDate = LocalDate.parse(date, DateTimeFormatter.ofPattern(DATE_PATTERN_YYYY_MM_DD));
        LocalDate localDateFirstDay = localDate.with(localDate.with(TemporalAdjusters.lastDayOfYear()));
        return localDateFirstDay.format(DateTimeFormatter.ofPattern(DATE_PATTERN_YYYY_MM_DD));
    }



    public static LocalDate parse(String date){
      return LocalDate.parse(date, DateTimeFormatter.ofPattern(DATE_PATTERN_YYYY_MM_DD));
    }


    public static String format(LocalDate date){
        return date.format(DateTimeFormatter.ofPattern(DATE_PATTERN_YYYY_MM_DD));
    }

    // 根据日期获取年份字符串
    public static String getYearStr(String date){
        LocalDate localDate = parse(date);
        int year = localDate.getYear();
        return String.valueOf(year);
    }


}
