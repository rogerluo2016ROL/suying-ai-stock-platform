package com.ds.cockpit.screen.system.service.chatbi.impl;

import cn.hutool.http.HttpRequest;
import cn.hutool.http.HttpResponse;
import com.alibaba.fastjson2.JSONArray;
import com.alibaba.fastjson2.JSONObject;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ToolCallResponse;
import com.ds.cockpit.screen.system.service.chatbi.ToolGatewayClient;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.net.URLEncoder;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class HttpToolGatewayClient implements ToolGatewayClient {
    private static final long CACHE_TTL_MS = 5 * 60 * 1000L;
    private final Map<String, CachedToolResponse> responseCache = new ConcurrentHashMap<>();

    @Value("${chatbi.tool-gateway.base-url:http://127.0.0.1:8000/api/v1}")
    private String baseUrl;

    @Override
    public ToolCallResponse callByIntent(String intent, String question) {
        if ("stock_model_run".equals(intent)) {
            return callModelRuns("stock", resolveStockModes(question));
        }
        if ("bond_model_run".equals(intent)) {
            return callModelRuns("bond", resolveBondModes(question));
        }
        if ("no_pick_diagnosis".equals(intent)) {
            return callModelRuns("stock", resolveStockModes(question));
        }
        String path = resolvePath(intent, question);
        if (path == null) {
            return ToolCallResponse.unavailable("当前意图暂未配置工具：" + intent);
        }
        try {
            String url = baseUrl + path;
            CachedToolResponse cached = responseCache.get(url);
            long now = System.currentTimeMillis();
            if (cached != null && now - cached.createdAt <= CACHE_TTL_MS) {
                return ToolCallResponse.ready(cached.body);
            }
            HttpResponse response = HttpRequest.get(url)
                    .timeout(20000)
                    .execute();
            if (response.isOk()) {
                String body = response.body();
                responseCache.put(url, new CachedToolResponse(body, now));
                return ToolCallResponse.ready(body);
            }
            return ToolCallResponse.unavailable("工具网关返回异常：" + response.getStatus());
        } catch (Exception ex) {
            return ToolCallResponse.unavailable("工具网关不可用：" + ex.getMessage());
        }
    }

    private String resolvePath(String intent, String question) {
        if ("supply_chain_ranking".equals(intent)) {
            return "/screener/supply-chain/candidate-ranking?top_n=5" + resolveChainQuery(question);
        }
        if ("company_evidence".equals(intent)) {
            return "/screener/supply-chain/candidate-ranking?top_n=10" + resolveChainQuery(question) + "&keyword=" + encode(question);
        }
        if ("model_resonance".equals(intent)) {
            return "/screener/market/index-quotes";
        }
        if ("data_quality".equals(intent)) {
            return "/screener/modes";
        }
        if ("no_pick_diagnosis".equals(intent)) {
            return "/screener/modes";
        }
        if ("report_export".equals(intent)) {
            return "/screener/supply-chain/candidate-ranking?top_n=8" + resolveChainQuery(question);
        }
        return null;
    }

    private ToolCallResponse callModelRuns(String modelType, List<String> modes) {
        String cacheKey = baseUrl + "::model-runs::" + modelType + "::" + String.join(",", modes);
        long now = System.currentTimeMillis();
        CachedToolResponse cached = responseCache.get(cacheKey);
        if (cached != null && now - cached.createdAt <= CACHE_TTL_MS) {
            return ToolCallResponse.ready(cached.body);
        }

        JSONArray runs = new JSONArray();
        boolean hasSuccess = false;
        String latestTradeDate = null;
        for (String mode : modes) {
            JSONObject run = new JSONObject();
            run.put("mode", mode);
            run.put("name", modelDisplayName(mode));
            String url = baseUrl + "/screener/run?mode=" + encode(mode) + "&top_n=10";
            try {
                HttpResponse response = HttpRequest.post(url)
                        .timeout(120000)
                        .execute();
                if (response.isOk()) {
                    JSONObject body = JSONObject.parseObject(response.body());
                    run.put("status", "ok");
                    run.put("body", body);
                    hasSuccess = true;
                    if (latestTradeDate == null && body.getString("trade_date") != null) {
                        latestTradeDate = body.getString("trade_date");
                    }
                } else {
                    run.put("status", "error");
                    run.put("message", "工具网关返回异常：" + response.getStatus() + " " + response.body());
                }
            } catch (Exception ex) {
                run.put("status", "error");
                run.put("message", "工具网关不可用：" + ex.getMessage());
            }
            runs.add(run);
        }

        JSONObject root = new JSONObject();
        root.put("version", "chatbi-model-run-v1");
        root.put("model_type", modelType);
        root.put("latest_trade_date", latestTradeDate);
        root.put("runs", runs);
        String body = root.toJSONString();
        responseCache.put(cacheKey, new CachedToolResponse(body, now));
        if (!hasSuccess) {
            return ToolCallResponse.unavailable(body);
        }
        return ToolCallResponse.ready(body);
    }

    private List<String> resolveStockModes(String question) {
        String q = question == null ? "" : question.toLowerCase();
        List<String> modes = new ArrayList<>();
        if (containsAny(q, "毕师傅", "硬核科技", "趋势启动")) {
            modes.add("bi_trend_launch");
            return modes;
        }
        if (containsAny(q, "午后", "秋神午后")) {
            modes.add("leader_afternoon");
            return modes;
        }
        if (containsAny(q, "竞价", "开盘")) {
            modes.add("leader_auction");
            return modes;
        }
        if (containsAny(q, "盘中")) {
            modes.add("leader_intraday");
            return modes;
        }
        if (containsAny(q, "尾盘")) {
            modes.add("leader_closing");
            return modes;
        }
        if (containsAny(q, "产业链", "大葱", "预期差", "预期差模型")) {
            modes.add("supply_chain");
            return modes;
        }
        modes.add("leader_afternoon");
        modes.add("bi_trend_launch");
        if (containsAny(q, "所有", "全部", "汇总", "多个模型", "模型结果")) {
            modes.add("supply_chain");
        }
        return modes;
    }

    private List<String> resolveBondModes(String question) {
        String q = question == null ? "" : question.toLowerCase();
        List<String> modes = new ArrayList<>();
        if (containsAny(q, "竞价", "t0", "t+0", "开盘")) {
            modes.add("cb_auction_t0_v2_1");
            return modes;
        }
        if (containsAny(q, "日内", "盘中")) {
            modes.add("cb_intraday");
            return modes;
        }
        modes.add("cb_floor");
        modes.add("cb_auction_t0_v2_1");
        return modes;
    }

    private String modelDisplayName(String mode) {
        if ("leader_afternoon".equals(mode)) {
            return "秋神龙头战法-午后选股";
        }
        if ("bi_trend_launch".equals(mode)) {
            return "毕师傅硬核科技趋势启动";
        }
        if ("leader_auction".equals(mode)) {
            return "秋神龙头竞价超预期";
        }
        if ("leader_intraday".equals(mode)) {
            return "秋神龙头盘中";
        }
        if ("leader_closing".equals(mode)) {
            return "秋神龙头尾盘顺势";
        }
        if ("supply_chain".equals(mode)) {
            return "产业链预期差选股模型";
        }
        if ("cb_floor".equals(mode)) {
            return "匪爷可转债底价安全垫";
        }
        if ("cb_intraday".equals(mode)) {
            return "匪爷可转债日内投机";
        }
        if ("cb_auction_t0_v2_1".equals(mode)) {
            return "竞价选债 T+0 V2.1 稳健版";
        }
        return mode;
    }

    private String resolveChainQuery(String question) {
        String q = question == null ? "" : question.toLowerCase();
        if (containsAny(q, "ai算力", "ai 算力", "光模块", "中际旭创", "源杰科技", "澜起科技", "新易盛")) {
            return "&chain_id=ai_compute";
        }
        if (containsAny(q, "具身智能", "机器人", "丝杠", "减速器", "光洋股份", "力星股份", "中大力德")) {
            return "&chain_id=embodied_intelligence";
        }
        if (containsAny(q, "氢能", "燃料电池", "加氢")) {
            return "&chain_id=hydrogen_energy";
        }
        if (containsAny(q, "6g", "六代通信", "卫星通信")) {
            return "&chain_id=sixth_generation_6g";
        }
        if (containsAny(q, "未来健康", "创新药", "医疗器械")) {
            return "&chain_id=future_health";
        }
        if (containsAny(q, "生物制造", "生物基", "酶制剂")) {
            return "&chain_id=bio_manufacturing";
        }
        if (containsAny(q, "未来材料", "新材料", "碳纤维", "高温合金")) {
            return "&chain_id=future_materials";
        }
        return "";
    }

    private boolean containsAny(String text, String... keywords) {
        for (String keyword : keywords) {
            if (text.contains(keyword.toLowerCase())) {
                return true;
            }
        }
        return false;
    }

    private String encode(String value) {
        try {
            return URLEncoder.encode(value == null ? "" : value, "UTF-8");
        } catch (Exception e) {
            return "";
        }
    }

    private static class CachedToolResponse {
        private final String body;
        private final long createdAt;

        private CachedToolResponse(String body, long createdAt) {
            this.body = body;
            this.createdAt = createdAt;
        }
    }
}
