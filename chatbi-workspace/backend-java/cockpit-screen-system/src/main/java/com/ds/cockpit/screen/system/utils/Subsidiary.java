package com.ds.cockpit.screen.system.utils;

import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * @Author: ZhouHong
 * @Date: 2025-05-27 下午 01:41
 */
public enum Subsidiary {

    GAC_HYPER("广汽昊铂", "cockpit_auth_data_scope_hyper"),
    GAC_AION("广汽埃安", "cockpit_auth_data_scope_aion"),
    GAC_TRUMPCHI("广汽传祺", "cockpit_auth_data_scope_g060"),
    GAC_HONDA("广汽本田", "cockpit_auth_data_scope_g069"),
    GAC_TOYOTA("广汽丰田", "cockpit_auth_data_scope_g044"),
    GAC_INTL("广汽国际", "cockpit_auth_data_scope_g307"),
    GAC_LEADWAY("广汽领程", "cockpit_auth_data_scope_g041"),
    GAC_GROUP("广汽集团", "cockpit_auth_data_scope_g000"),
    GAC_HANGYE("行业", "");

    private final String chineseName;
    private final String tableName;
    private final Set<String> metrics = new HashSet<>();

    Subsidiary(String chineseName, String tableName) {
        this.chineseName = chineseName;
        this.tableName = tableName;
    }

    public void addMetric(String metric) {
        metrics.add(metric);
    }

    public Set<String> getMetrics() {
        return Collections.unmodifiableSet(metrics);
    }

    public String getChineseName()
    {
        return chineseName;
    }

    public String getTableName()
    {
        return tableName;
    }

    public static String getTableNameByChineseName(String chineseName) {
        for (Subsidiary subsidiary : values()) {
            if (subsidiary.chineseName.equals(chineseName)) {
                return subsidiary.tableName;
            }
        }
        return null;
    }

    public static List<String> getAllChineseNames() {
        return Stream.of(values())
                .map(s -> s.chineseName)
                .collect(Collectors.toList());
    }

    public static Set<String> getSubsidiaryMetrics(Subsidiary subsidiary) {
        return subsidiary.getMetrics();
    }

    static {

        // 配置各子公司指标（中文）
        Subsidiary.GAC_HYPER.addMetric("批发");
        Subsidiary.GAC_HYPER.addMetric("终端");
        Subsidiary.GAC_HYPER.addMetric("库存");
        Subsidiary.GAC_HYPER.addMetric("库存度");

        Subsidiary.GAC_AION.addMetric("产量");
        Subsidiary.GAC_AION.addMetric("一次合格率");
        Subsidiary.GAC_AION.addMetric("开动率");
        Subsidiary.GAC_AION.addMetric("批发");
        Subsidiary.GAC_AION.addMetric("终端");
        Subsidiary.GAC_AION.addMetric("库存");
        Subsidiary.GAC_AION.addMetric("库存度");

        Subsidiary.GAC_TRUMPCHI.addMetric("产量");
        Subsidiary.GAC_TRUMPCHI.addMetric("一次合格率");
        Subsidiary.GAC_TRUMPCHI.addMetric("开动率");
        Subsidiary.GAC_TRUMPCHI.addMetric("批发");
        Subsidiary.GAC_TRUMPCHI.addMetric("终端");
        Subsidiary.GAC_TRUMPCHI.addMetric("库存");
        Subsidiary.GAC_TRUMPCHI.addMetric("库存度");

        Subsidiary.GAC_HONDA.addMetric("产量");
        Subsidiary.GAC_HONDA.addMetric("批发");
        Subsidiary.GAC_HONDA.addMetric("终端");
        Subsidiary.GAC_HONDA.addMetric("库存");
        Subsidiary.GAC_HONDA.addMetric("库存度");

        Subsidiary.GAC_TOYOTA.addMetric("产量");
        Subsidiary.GAC_TOYOTA.addMetric("批发");
        Subsidiary.GAC_TOYOTA.addMetric("终端");
        Subsidiary.GAC_TOYOTA.addMetric("库存");
        Subsidiary.GAC_TOYOTA.addMetric("库存度");

        Subsidiary.GAC_INTL.addMetric("批发");
        Subsidiary.GAC_INTL.addMetric("终端");
        Subsidiary.GAC_INTL.addMetric("库存");
        Subsidiary.GAC_INTL.addMetric("库存度");

        Subsidiary.GAC_LEADWAY.addMetric("产量");
        Subsidiary.GAC_LEADWAY.addMetric("批发");
        Subsidiary.GAC_LEADWAY.addMetric("终端");
        Subsidiary.GAC_LEADWAY.addMetric("库存");
        Subsidiary.GAC_LEADWAY.addMetric("库存度");

        Subsidiary.GAC_GROUP.addMetric("行业");
        Subsidiary.GAC_GROUP.addMetric("产量");
        Subsidiary.GAC_GROUP.addMetric("一次合格率");
        Subsidiary.GAC_GROUP.addMetric("开动率");
        Subsidiary.GAC_GROUP.addMetric("批发");
        Subsidiary.GAC_GROUP.addMetric("终端");
        Subsidiary.GAC_GROUP.addMetric("库存");
        Subsidiary.GAC_GROUP.addMetric("库存度");
    }

}
