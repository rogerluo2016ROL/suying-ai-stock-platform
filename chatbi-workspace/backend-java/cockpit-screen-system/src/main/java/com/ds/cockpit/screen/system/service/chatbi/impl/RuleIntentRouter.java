package com.ds.cockpit.screen.system.service.chatbi.impl;

import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.IntentResult;
import com.ds.cockpit.screen.system.service.chatbi.IntentRouter;
import org.springframework.stereotype.Service;

@Service
public class RuleIntentRouter implements IntentRouter {
    @Override
    public IntentResult route(String question) {
        String q = question == null ? "" : question.toLowerCase();
        if (containsAny(q, "报告", "导出", "word", "excel")) {
            return new IntentResult("report_export", 0.9, "命中报告导出规则");
        }
        if (containsAny(q, "为什么没有", "没票", "未入选", "为什么没", "为什么没有进入")) {
            if (containsAny(q, "选债模型")) {
                return new IntentResult("bond_model_run", 0.9, "命中选债模型规则");
            }
            return new IntentResult("no_pick_diagnosis", 0.9, "命中无票诊断规则");
        }
        if (containsAny(q, "共振", "多个模型", "同时命中")) {
            return new IntentResult("model_resonance", 0.9, "命中模型共振规则");
        }
        if (containsAny(q, "选债", "可转债", "匪爷")) {
            return new IntentResult("bond_model_run", 0.9, "命中选债模型规则");
        }
        if (containsAny(q, "选股", "股票", "模型结果", "模型信号", "预期差模型", "产业链预期差", "毕师傅", "秋神")) {
            return new IntentResult("stock_model_run", 0.82, "命中选股模型规则");
        }
        if (containsAny(q, "数据质量", "更新", "最新数据", "缺失")) {
            return new IntentResult("data_quality", 0.78, "命中数据质量规则");
        }
        if (q.contains("产业链") && containsAny(q, "候选", "top", "top20", "排序", "清单", "公司")) {
            return new IntentResult("supply_chain_ranking", 0.86, "命中产业链候选/排序规则");
        }
        if (containsAny(q, "证据链", "l8", "研发", "商用", "三高", "卡脖子", "标签证据", "毛利证据", "证据")) {
            return new IntentResult("company_evidence", 0.86, "命中公司证据链/三高规则");
        }
        if (containsAny(q, "产业链", "候选", "top", "top20", "排序", "清单")) {
            return new IntentResult("supply_chain_ranking", 0.86, "命中产业链候选/排序规则");
        }
        return new IntentResult("unknown", 0.3, "未命中明确规则");
    }

    private boolean containsAny(String text, String... keywords) {
        for (String keyword : keywords) {
            if (text.contains(keyword.toLowerCase())) {
                return true;
            }
        }
        return false;
    }
}
