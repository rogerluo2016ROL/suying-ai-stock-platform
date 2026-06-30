"""大葱产业链解构选股 — PG研报直查 + 五维评级.

V3 (重构 P1): 对齐 StrategyEngine 基类 / trade_date 历史时点支持 / layer 真实匹配.
  - run() 返回 ScreeningResult (原 dict), 继承 StrategyEngine, 新增 get_factor_weights()
  - trade_date 参数生效: 财务/研报/券商数据约束在 <= trade_date (解锁样本外回测)
  - layer 用 stock_profiles.main_business 关键词真实匹配 (原恒取 layers[0])
  - 研报查询加 ORDER BY pub_date DESC (修 LIMIT 50000 无序 bug)
后续: P2 rating 用研报覆盖广度复活 / P3 产业链配置外置 JSON / P4 权重 IC 化 / P5 样本外验证.
"""

import os, re, time, json, logging
from pathlib import Path
from typing import Optional

from kronos_factors.base import StrategyEngine, ScreeningResult
from kronos_factors.engine.supply_chain_bom import score_company_v4
from kronos_factors.engine.supply_chain_foundation import CHAIN_IDS

logger = logging.getLogger("kronos-factors.supply_chain")

MAPPING_QUALITY_WEIGHTS = {
    "verified": 1.00,
    "approved": 1.00,
    "pending_review": 0.95,
    "weak_evidence": 0.85,
    "fallback_keyword": 0.75,
    "rejected": 0.00,
}

_BUILTIN_CHAINS = {
    "半导体": {"industries": ["半导体", "元器件"], "layers": ["材料", "设备", "制造", "封测", "设计"]},
    "新能源": {"industries": ["电气设备"], "layers": ["材料", "光伏", "电池", "设备"]},
    "AI算力": {"industries": ["通信设备", "软件服务"], "layers": ["硬件", "软件", "应用"]},
    "机器人": {"industries": ["专用机械"], "layers": ["核心部件", "整机", "集成"]},
    "创新药": {"industries": ["化学制药", "生物制药", "医疗保健"], "layers": ["CXO", "原料药", "创新药"]},
}

# layer 真实匹配关键词表 — 按特异性排序 (制造/封测/设备/材料在前, 设计兜底, 因设计公司描述最泛).
# 来源: stock_profiles.main_business 实证样本 (中芯=晶圆代工/中微=半导体设备/沐曦=GPU/生益=覆铜板).
# P3 将外置到 configs/supply_chains.json 并扩展更多产业链.
_BUILTIN_LAYER_KW = {
    "半导体": {
        "制造": ["晶圆代工", "晶圆制造", "代工企业", "foundry", "特色工艺", "晶圆厂"],
        "封测": ["封装测试", "封测", "晶圆级封装", "芯粒", "集成电路封装", "芯片封装", "中段硅片"],
        "设备": ["半导体设备", "专用设备", "光刻", "刻蚀", "薄膜沉积", "离子注入", "检测设备", "半导体专用"],
        "材料": ["覆铜板", "铜箔", "硅片", "光刻胶", "靶材", "引线框架", "环氧树脂", "抛光液", "特种气体", "掩膜版", "电子化学", "基板", "电子级玻璃布"],
        "设计": ["芯片", "GPU", "处理器", "存储器", "微控制器", "传感器", "模拟芯片", "射频", "FPGA", "ASIC", "集成电路设计", "光芯片", "MCU"],
    },
    "新能源": {
        "材料": ["正极", "负极", "电解液", "隔膜", "硅料", "多晶硅", "铜箔", "铝箔", "前驱体"],
        "光伏": ["光伏", "太阳能", "组件", "电池片", "硅片", "光伏玻璃"],
        "电池": ["锂电池", "动力电池", "储能", "电芯", "蓄电池", "燃料电池"],
        "设备": ["逆变器", "光伏设备", "锂电设备", "装备"],
    },
    "AI算力": {
        "硬件": ["服务器", "芯片", "光模块", "交换机", "印制电路", "PCB", "硬件", "算力", "数据中心"],
        "软件": ["软件", "算法", "中间件", "操作系统", "数据库", "云服务", "平台"],
        "应用": ["解决方案", "智能", "应用", "服务"],
    },
    "机器人": {
        "核心部件": ["减速器", "伺服", "控制器", "电机", "传感器", "丝杠"],
        "整机": ["机器人", "工业机器人", "服务机器人", "整机"],
        "集成": ["集成", "自动化", "解决方案", "产线"],
    },
    "创新药": {
        "CXO": ["CXO", "研发外包", "生产外包", "定制研发", "CDMO", "CRO", "定制生产"],
        "原料药": ["原料药", "中间体", "API"],
        "创新药": ["创新药", "生物药", "抗体", "疫苗", "生物制品", "制剂", "药品", "PD-1", "ADC"],
    },
}

_BUILTIN_MOAT_KW = {
    "独家垄断": (r"独家供应|唯一供应商|不可替代|垄断|寡头", 20),
    "行业龙头": (r"龙头|全球第一|国内第一|市占率第一|遥遥领先|平台型龙头", 15),
    "进口替代": (r"国产替代|进口替代|打破垄断|自主可控|填补空白", 10),
    "技术壁垒": (r"核心专利|技术壁垒|护城河|全球首发|率先突破", 10),
}

RATING_MAP = {"买入": 5, "增持": 4, "推荐": 4, "强烈推荐": 5, "跑赢行业": 4,
              "持有": 2, "中性": 1, "谨慎推荐": 2, "减持": -3, "卖出": -5, "回避": -4}
# 注: research_reports_tushare.rating 列当前全空 (etl 采集缺陷, Tushare research_report() 不返回评级).
# RATING_MAP deprecated — rating 维度改用「研报覆盖广度同业分位数」复活 (见 _compute_rating_dimension),
# 与 consensus(broker_recommend 绝对券商数) 正交, 避免重复计数.


def _merge_mapping_context(pick: dict, mapping_context: dict[str, dict]) -> dict:
    enriched = dict(pick)
    contexts = [
        c for c in (mapping_context.get(str(pick.get("code") or "")) or [])
        if c.get("mapping_status") != "rejected"
    ]
    expected_chain_id = CHAIN_IDS.get(str(pick.get("chain") or ""))
    context = None
    if expected_chain_id:
        matching = [c for c in contexts if c.get("chain_id") == expected_chain_id]
        if matching:
            context = max(matching, key=lambda c: float(c.get("mapping_confidence") or 0))
    if context is None and contexts:
        context = max(contexts, key=lambda c: float(c.get("mapping_confidence") or 0))
    if not context:
        enriched.setdefault("mapping_source", "fallback_keyword")
        enriched.setdefault("mapping_status", "weak_evidence")
        enriched.setdefault("evidence_gaps", ["缺少公司到产业链节点的正式映射"])
        weight = MAPPING_QUALITY_WEIGHTS["fallback_keyword"]
        enriched["mapping_quality_weight"] = weight
        enriched["mapping_adjusted_score"] = round(float(enriched.get("total_score") or 0) * weight, 2)
        return enriched
    enriched.update({
        "node_id": context.get("node_id"),
        "node_name": context.get("node_name"),
        "mapping_confidence": context.get("mapping_confidence"),
        "mapping_status": context.get("mapping_status"),
        "mapping_source": context.get("mapping_source"),
        "evidence_gaps": context.get("evidence_gaps") or [],
    })
    weight = MAPPING_QUALITY_WEIGHTS.get(str(enriched.get("mapping_status") or ""), 0.90)
    enriched["mapping_quality_weight"] = weight
    enriched["mapping_adjusted_score"] = round(float(enriched.get("total_score") or 0) * weight, 2)
    return enriched


def _chain_id_from_node_id(node_id: str | None) -> str:
    text = str(node_id or "")
    for chain_id in sorted(CHAIN_IDS.values(), key=len, reverse=True):
        if text == f"chain_{chain_id}" or text.startswith(f"{chain_id}_"):
            return chain_id
    return ""


# ── 产业链配置加载 (P3): 优先包内 configs/supply_chains.json, 失败/缺失 fallback 内置默认 ──
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "supply_chains.json"
_LEGACY_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "configs" / "supply_chains.json"


def _load_chains_config():
    """加载产业链配置, 返回 (chains, layer_kw, moat_kw).

    chains: {链名: {industries, layers}}; layer_kw: {链名: {层: [关键词]}};
    moat_kw: {类型: (pattern, score)}. JSON 缺失/损坏/不完整时退回内置默认.
    """
    try:
        config_path = _CONFIG_PATH if _CONFIG_PATH.exists() else _LEGACY_CONFIG_PATH
        data = json.loads(config_path.read_text(encoding="utf-8"))
        chains, layer_kw = {}, {}
        for name, cd in data.get("chains", {}).items():
            chains[name] = {"industries": cd.get("industries", []), "layers": cd.get("layers", [])}
            layer_kw[name] = cd.get("layer_keywords", {})
        moat_kw = {k: (v["pattern"], v["score"]) for k, v in data.get("moat_keywords", {}).items()}
        if chains and moat_kw:
            logger.info("产业链配置加载自 JSON: %d 链", len(chains))
            return chains, layer_kw, moat_kw
        logger.warning("产业链配置不完整, 使用内置默认")
    except Exception as e:
        logger.warning("产业链配置加载失败 (%s), 使用内置默认", e)
    return _BUILTIN_CHAINS, _BUILTIN_LAYER_KW, _BUILTIN_MOAT_KW


def load_upstream_influence_rules(path: str | Path | None = None) -> list[dict]:
    """Load rules for upstream suppliers that influence strategic downstream chains."""
    config_path = Path(path) if path else _CONFIG_PATH
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("上游影响规则加载失败 (%s), 返回空规则", e)
        return []
    rules = data.get("upstream_influence_rules", [])
    return rules if isinstance(rules, list) else []


def _contains_any(text: str, terms: list[str]) -> bool:
    normalized = text.lower()
    return any(str(term).strip().lower() in normalized for term in terms if str(term).strip())


def match_upstream_influence_rules(
    code: str,
    name: str,
    industry: str,
    main_business: str,
    rules: list[dict] | None = None,
) -> list[dict]:
    """Match a company to upstream influence paths without requiring same-sector membership."""
    matches = []
    rule_set = rules if rules is not None else load_upstream_influence_rules()
    industry_text = str(industry or "")
    search_text = " ".join([str(name or ""), industry_text, str(main_business or "")])
    for rule in rule_set:
        if not isinstance(rule, dict):
            continue
        industry_hit = _contains_any(industry_text, rule.get("industries") or [])
        keyword_hit = _contains_any(search_text, rule.get("keywords") or [])
        if not industry_hit and not keyword_hit:
            continue

        upstream_node = str(rule.get("upstream_node") or "上游使能节点")
        downstream_chains = [str(item) for item in rule.get("downstream_chains", []) if item]
        matches.append({
            "candidate_source": "upstream_influence",
            "pool_status": rule.get("pool_status") or "观察池",
            "rule_id": rule.get("rule_id") or upstream_node,
            "policy_theme": rule.get("policy_theme") or "新质生产力",
            "upstream_node": upstream_node,
            "impact_role": rule.get("impact_role") or "上游使能环节",
            "downstream_chains": downstream_chains,
            "influence_paths": [f"{name or code} → {upstream_node} → {chain}" for chain in downstream_chains],
            "evidence_gaps": rule.get("evidence_gaps") or [],
        })
    return matches


CHAINS, LAYER_KW, MOAT_KW = _load_chains_config()


class SupplyChainEngine(StrategyEngine):
    """大葱产业链解构选股 — 护城河/成长/盈利/评级/共识 五维打分 (中长线)."""

    mode = "supply_chain"

    # 归一化权重 (满分100: moat40/growth30/profit15/rating10/consensus5).
    # P4 用 IC/ICIR 校准; P5 样本外验证 PASS 后才更新此处默认值.
    DEFAULT_WEIGHTS = {"moat": 0.40, "growth": 0.30, "profit": 0.15, "rating": 0.10, "consensus": 0.05}
    # 各维满分 (归一化用); 默认权重下 total = sum(dim) 与原硬编码等价.
    DIM_MAX = {"moat": 40, "growth": 30, "profit": 15, "rating": 10, "consensus": 5}

    def __init__(self, weights: dict = None):
        """Args:
            weights: 自定义归一化权重 {moat,growth,profit,rating,consensus}, 和≈1.0;
                     None=用 DEFAULT_WEIGHTS (向后兼容). P4 校准/P5 验证时注入.
        """
        self.weights = dict(weights) if weights else dict(self.DEFAULT_WEIGHTS)

    def get_factor_weights(self) -> dict:
        return dict(self.weights)

    def run(self, top_n=30, chain=None, min_score=30,
            trade_date: Optional[str] = None, **kw) -> ScreeningResult:
        """运行产业链解构选股.

        Args:
            top_n: 返回前 N 只.
            chain: 指定单条产业链 (None=跑全部 CHAINS).
            min_score: 最低总分阈值.
            trade_date: 历史时点 (YYYY-MM-DD). None=取最新数据 (生产默认, 向后兼容);
                        传入时财务/研报/券商数据约束在 <= trade_date, 支持样本外回测防未来泄露.
        """
        from kronos_factors.scorer._db_stub import _get_db
        t0 = time.time()

        fin, broker, reports, report_counts, peers, main_business = {}, {}, {}, {}, {}, {}
        mapping_context = {}
        try:
            import psycopg2
            pg = psycopg2.connect(os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"), connect_timeout=5)
            cur = pg.cursor()

            # 财务指标 — DISTINCT ON 取每只股最新一期, trade_date cutoff 防样本外未来泄露
            fin_sql = ("SELECT DISTINCT ON (code) code, roe, COALESCE(gross_margin,30), net_margin, "
                       "debt_ratio, eps, revenue_growth, profit_growth FROM financial_indicator")
            if trade_date:
                fin_sql += " WHERE end_date <= %s"
            fin_sql += " ORDER BY code, end_date DESC"
            cur.execute(fin_sql, (trade_date,) if trade_date else ())
            for r in cur.fetchall():
                fin[str(r[0])] = {"roe": float(r[1] or 0), "gross_margin": float(r[2] or 30), "net_margin": float(r[3] or 0),
                                  "debt_ratio": float(r[4] or 50), "eps": float(r[5] or 0), "revenue_growth": float(r[6] or 0),
                                  "profit_growth": float(r[7] or 0)}

            # 券商覆盖数 — trade_date cutoff (month 为 YYYYMM)
            if trade_date:
                month_cut = trade_date[:7].replace("-", "")
                cur.execute("SELECT code, COUNT(DISTINCT broker) FROM broker_recommend WHERE month <= %s GROUP BY code", (month_cut,))
            else:
                cur.execute("SELECT code, COUNT(DISTINCT broker) FROM broker_recommend GROUP BY code")
            for r in cur.fetchall():
                broker[str(r[0])] = r[1]

            # 研报标题 — pub_date cutoff + ORDER BY DESC (修原 LIMIT 50000 无序 bug), 仅用于 moat 关键词匹配
            rep_sql = ("SELECT code, title FROM research_reports_tushare "
                       "WHERE code IS NOT NULL AND code != 'nan'")
            if trade_date:
                rep_sql += " AND pub_date <= %s"
            rep_sql += " ORDER BY pub_date DESC LIMIT 50000"
            cur.execute(rep_sql, (trade_date,) if trade_date else ())
            for r in cur.fetchall():
                code = str(r[0] or ""); title = str(r[1] or "")
                if code not in reports:
                    reports[code] = {"moat": 0, "sigs": []}
                for mt, (pat, sc) in MOAT_KW.items():
                    if re.search(pat, title):
                        reports[code]["moat"] = min(40, reports[code]["moat"] + sc)
                        if mt not in reports[code]["sigs"]:
                            reports[code]["sigs"].append(mt)

            # 研报篇数 (title 100% 非空, 篇数可靠) — rating 维度数据源, trade_date cutoff
            rc_sql = "SELECT code, COUNT(*) FROM research_reports_tushare WHERE code IS NOT NULL AND code != 'nan'"
            if trade_date:
                rc_sql += " AND pub_date <= %s"
            rc_sql += " GROUP BY code"
            cur.execute(rc_sql, (trade_date,) if trade_date else ())
            for r in cur.fetchall():
                report_counts[str(r[0])] = r[1]

            # 主营业务 — layer 真实匹配数据源 (100% 覆盖)
            cur.execute("SELECT code, main_business FROM stock_profiles")
            for r in cur.fetchall():
                main_business[str(r[0])] = str(r[1] or "")

            cur.execute("SELECT industry, COUNT(*) FROM stocks WHERE is_st=0 GROUP BY industry")
            for r in cur.fetchall():
                peers[r[0]] = r[1]
            try:
                cur.execute("""
                    SELECT c.code, c.node_id, n.node_name,
                           b.confidence, b.status, c.evidence
                    FROM company_chain_mapping c
                    LEFT JOIN company_bom_mapping b ON b.code = c.code AND b.node_id = c.node_id
                    LEFT JOIN chain_nodes n ON n.node_id = c.node_id
                """)
                for code, node_id, node_name, confidence, status, evidence in cur.fetchall():
                    evidence = evidence or {}
                    conf = float(confidence or evidence.get("confidence") or 0)
                    item = {
                        "node_id": node_id,
                        "node_name": node_name,
                        "chain_id": evidence.get("chain_id") or _chain_id_from_node_id(node_id),
                        "mapping_confidence": conf,
                        "mapping_status": status or evidence.get("status") or "pending_review",
                        "mapping_source": evidence.get("mapping_source") or "company_chain_mapping",
                        "evidence_gaps": evidence.get("evidence_gaps") or [],
                    }
                    mapping_context.setdefault(str(code), []).append(item)
            except Exception as e:
                logger.warning("供应链映射上下文加载失败: %s", e)
            pg.close()
        except Exception as e:
            logger.warning("PG: %s", e)

        with _get_db(readonly=True) as db:
            names, industries = {}, {}
            for r in db.execute("SELECT code,name,industry FROM stocks WHERE is_st=0").fetchall():
                names[r["code"]] = r["name"] or ""
                industries[r["code"]] = r["industry"] or ""
            # 同业分布 — rating 维度分位数计算基准 (全市场非ST股, 按 industry 聚合 bc/rc, 缺省0)
            peer_broker, peer_report = {}, {}
            for c, ind in industries.items():
                peer_broker.setdefault(ind, []).append(broker.get(c, 0))
                peer_report.setdefault(ind, []).append(report_counts.get(c, 0))
            for d in (peer_broker, peer_report):
                for ind in d:
                    d[ind].sort()
            chains_to_run = {chain: CHAINS[chain]} if chain in CHAINS else CHAINS
            picks = []
            for ck, cd in chains_to_run.items():
                candidates = set()
                for ind in cd["industries"]:
                    for r in db.execute("SELECT code FROM stocks WHERE is_st=0 AND industry LIKE ?", (f"%{ind}%",)).fetchall():
                        candidates.add(r["code"])
                layer_kw = LAYER_KW.get(ck, {})
                for code in candidates:
                    name = names.get(code, ""); industry = industries.get(code, "")
                    fd = fin.get(code, {}); bc = broker.get(code, 0)
                    rp = reports.get(code, {"moat": 0, "sigs": []})

                    # 1. Moat (40%)
                    moat = rp.get("moat", 0); moat_sigs = rp.get("sigs", [])[:]
                    if bc >= 5:
                        moat = min(40, moat + 8); moat_sigs.append(f"{bc}券商")
                    elif bc >= 3:
                        moat = min(40, moat + 4)
                    pc = peers.get(industry, 100)
                    if pc <= 5:
                        moat = min(40, moat + 10); moat_sigs.append(f"仅{pc}家")
                    elif pc <= 10:
                        moat = min(40, moat + 5); moat_sigs.append(f"{pc}家寡头")

                    # 2. Growth (30%)
                    rg = fd.get("revenue_growth", 0); pg = fd.get("profit_growth", 0)
                    growth = 10.0
                    if rg > 30: growth += 12
                    elif rg > 20: growth += 9
                    elif rg > 10: growth += 6
                    elif rg > 0: growth += 3
                    if pg > 30: growth += 10
                    elif pg > 20: growth += 7
                    elif pg > 10: growth += 4
                    elif pg > 0: growth += 2
                    if rg > 15 and pg > 15: growth += 5
                    if rg > 15 and pg > rg: growth += 3
                    growth = min(30, growth)

                    # 3. Profit (15%)
                    roe = fd.get("roe", 0); gm = fd.get("gross_margin", 30); debt = fd.get("debt_ratio", 50)
                    profit = 5.0
                    if roe > 25: profit += 5
                    elif roe > 15: profit += 4
                    elif roe > 8: profit += 2
                    if gm > 60: profit += 5
                    elif gm > 40: profit += 3
                    elif gm > 20: profit += 1
                    if debt < 30: profit += 3
                    elif debt < 50: profit += 2
                    elif debt > 70: profit -= 2
                    profit = max(0, min(15, profit))

                    # 4. Rating (10%) — 研报覆盖广度同业分位数 (与 consensus 绝对券商数正交)
                    rc = report_counts.get(code, 0)
                    rating_score = self._compute_rating_dimension(
                        bc, rc, peer_broker.get(industry, []), peer_report.get(industry, []))
                    # 5. Consensus (5%) — broker_recommend 绝对券商数
                    consensus = min(5, bc * 1.0)
                    # P4: 维度归一化×权重×100 (默认权重下与原 sum(dim) 等价, grade 阈值不变)
                    w = self.weights
                    dm = self.DIM_MAX
                    total = ((moat / dm["moat"]) * w["moat"]
                             + (growth / dm["growth"]) * w["growth"]
                             + (profit / dm["profit"]) * w["profit"]
                             + (rating_score / dm["rating"]) * w["rating"]
                             + (consensus / dm["consensus"]) * w["consensus"]) * 100
                    if total < min_score:
                        continue
                    grade = "S" if total >= 80 else ("A" if total >= 65 else ("B" if total >= 50 else "C"))

                    # layer 真实匹配: main_business 关键词 → name → layers[0] 兜底
                    layer = self._match_layer(code, name, layer_kw, cd["layers"][0], main_business)

                    picks.append({"code": code, "name": name, "industry": industry, "chain": ck, "layer": layer,
                                  "total_score": round(total, 1), "grade": grade, "moat_score": moat,
                                  "moat_signals": moat_sigs[:4], "growth_score": round(growth, 1),
                                  "profit_score": round(profit, 1), "rating_score": round(rating_score, 1),
                                  "consensus_score": round(consensus, 1), "revenue_growth": rg,
                                  "profit_growth": pg, "roe": roe, "gross_margin": gm, "report_count": rc})

        seen = {}
        for p in sorted(picks, key=lambda x: -x["total_score"]):
            if p["code"] not in seen:
                seen[p["code"]] = p
        picks = [score_company_v4(p) for p in seen.values()]
        picks = [_merge_mapping_context(p, mapping_context) for p in picks]
        picks = sorted(picks, key=lambda x: -float(x.get("mapping_adjusted_score") or x["total_score"]))[:top_n]
        elapsed = time.time() - t0
        logger.info("产业链解构V4: %d picks, %d chains (%.1fs, trade_date=%s)",
                    len(picks), len(set(p["chain"] for p in picks)), elapsed, trade_date)
        return ScreeningResult(
            mode=self.mode, picks=picks, total_scored=len(picks),
            total_excluded=0, elapsed=elapsed,
            metadata={"chains_run": list(chains_to_run.keys()), "trade_date": trade_date,
                      "weights": self.weights, "bom_model_version": "4.0"},
        )

    @staticmethod
    def _percentile(value, sorted_dist):
        """value 在已排序分布中的分位数 (0~1). 空分布返回 0."""
        if not sorted_dist:
            return 0.0
        import bisect
        lo = bisect.bisect_left(sorted_dist, value)
        hi = bisect.bisect_right(sorted_dist, value)
        # 区间内取中位, 避免并列值偏置
        return ((lo + hi) / 2) / len(sorted_dist)

    @classmethod
    def _compute_rating_dimension(cls, broker_count, report_count, peer_broker_dist, peer_report_dist):
        """rating 维度 (满分10) — 研报覆盖广度同业分位数.

        report_count 分位×6 (research_reports_tushare, 4098股, 与 consensus 用的 broker_recommend
        不同数据源, 更正交) + broker_count 分位×4. 两者均在同行业内相对排名, 与 consensus 绝对券商数解耦.
        """
        rp = cls._percentile(report_count, peer_report_dist)
        bp = cls._percentile(broker_count, peer_broker_dist)
        return round(min(10.0, rp * 6 + bp * 4), 1)

    @staticmethod
    def _match_layer(code, name, layer_kw, fallback, main_business):
        """按 main_business 关键词匹配产业链层级 (dict 顺序=特异性优先级).

        优先 main_business 文本匹配; 全 miss 则退回 name 匹配; 仍 miss 则 fallback (layers[0]).
        """
        text = main_business.get(code, "") or ""
        for layer, keywords in layer_kw.items():
            for kw in keywords:
                if kw and kw in text:
                    return layer
        nm = name or ""
        for layer, keywords in layer_kw.items():
            for kw in keywords:
                if kw and kw in nm:
                    return layer
        return fallback
