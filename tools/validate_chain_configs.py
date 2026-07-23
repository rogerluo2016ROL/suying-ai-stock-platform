#!/usr/bin/env python3
"""产业链配置一致性校验 — 防止多副本/多清单再分叉.

校验项:
  1. 包级与包内两份 supply_chains.json 语义一致 (链集合/industries/layers/layer_keywords/
     moat_keywords/upstream_influence_rules; 忽略包内副本的 "_notice" 兼容键)
  2. 每链 layers 与 layer_keywords 键完全对齐, layers 无重复
  3. supply_chains.json 链名 ⊆ BOM_COMPLETION_PROFILES 键 ∪ CHAIN_ONLY_EXCEPTIONS,
     profile 键反向 ⊆ 链名 ∪ PROFILE_ONLY_EXCEPTIONS
  4. supply_chain_foundation.CHAIN_IDS 覆盖所有链 (或有显式例外)
  5. industry_chain_templates.json: template_id 唯一, 每模板 8 层, order 为 1..8,
     layer_id 非空且模板内唯一, example_theme 非空
  6. 各链 layer_keywords 列表内无重复关键词

用法: python tools/validate_chain_configs.py  (有违规时打印全部违规项并 exit 1)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "kronos-factors"
PKG_SUPPLY_CHAINS = PKG / "configs" / "supply_chains.json"
IN_PACKAGE_SUPPLY_CHAINS = PKG / "kronos_factors" / "configs" / "supply_chains.json"
TEMPLATES_CONFIG = PKG / "configs" / "industry_chain_templates.json"

# ── 显式例外清单 (改动需附理由) ──
# 链有但无 BOM profile: 华为韬定律_先进封装 由 profile "华为韬定律" 子串匹配覆盖;
# AI Token输出电力 为模板驱动链, 不走 BOM_COMPLETION_PROFILES.
CHAIN_ONLY_EXCEPTIONS = {"华为韬定律_先进封装", "AI Token输出电力"}
# 有 BOM profile 但不是选股链: 政策主题链 (量子科技等 6 条, 源自 supply_chain_bom_v4 种子),
# 别名/子链 (华为韬定律 = 华为韬定律_先进封装的 BOM 别名, 半导体设备材料/工业软件 为种子子链).
PROFILE_ONLY_EXCEPTIONS = {
    "量子科技", "生物制造", "氢能和核聚变能", "脑机接口", "具身智能", "第六代移动通信",
    "华为韬定律", "半导体设备材料", "工业软件",
}
# CHAIN_IDS 允许缺失的链 (当前无).
CHAIN_ID_EXCEPTIONS: set[str] = set()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _semantic(data: dict) -> dict:
    """去掉兼容/元信息键后的语义内容."""
    return {k: v for k, v in data.items() if k not in {"_notice", "version", "description"}}


def validate() -> list[str]:
    violations: list[str] = []

    pkg_data = _load_json(PKG_SUPPLY_CHAINS)
    inpkg_data = _load_json(IN_PACKAGE_SUPPLY_CHAINS)
    pkg_sem, inpkg_sem = _semantic(pkg_data), _semantic(inpkg_data)

    # 1. 双副本一致
    if pkg_sem != inpkg_sem:
        diff_keys = [k for k in set(pkg_sem) | set(inpkg_sem)
                     if pkg_sem.get(k) != inpkg_sem.get(k)]
        violations.append(
            f"supply_chains.json 双副本不一致 ({PKG_SUPPLY_CHAINS} vs {IN_PACKAGE_SUPPLY_CHAINS}), "
            f"差异键: {diff_keys}")

    chains = pkg_data.get("chains") or {}

    # 2. layers 与 layer_keywords 对齐
    for cname, cd in chains.items():
        layers = cd.get("layers") or []
        kw_keys = list((cd.get("layer_keywords") or {}).keys())
        if len(layers) != len(set(layers)):
            violations.append(f"链[{cname}] layers 有重复项: {layers}")
        missing = [l for l in layers if l not in kw_keys]
        extra = [k for k in kw_keys if k not in layers]
        if missing:
            violations.append(f"链[{cname}] layers 缺 layer_keywords: {missing}")
        if extra:
            violations.append(f"链[{cname}] layer_keywords 多出不在 layers 的键: {extra}")

    # 3. 链名 ↔ BOM_COMPLETION_PROFILES
    sys.path.insert(0, str(PKG))
    from kronos_factors.engine.chain_deconstruct import BOM_COMPLETION_PROFILES
    profiles = set(BOM_COMPLETION_PROFILES)
    chain_names = set(chains)
    for name in sorted(chain_names - profiles - CHAIN_ONLY_EXCEPTIONS):
        violations.append(f"链[{name}] 无 BOM_COMPLETION_PROFILES profile 且不在 CHAIN_ONLY_EXCEPTIONS")
    for name in sorted(profiles - chain_names - PROFILE_ONLY_EXCEPTIONS):
        violations.append(f"profile[{name}] 无对应链且不在 PROFILE_ONLY_EXCEPTIONS")

    # 4. CHAIN_IDS 覆盖
    from kronos_factors.engine.supply_chain_foundation import CHAIN_IDS
    for name in sorted(chain_names - set(CHAIN_IDS) - CHAIN_ID_EXCEPTIONS):
        violations.append(f"链[{name}] 缺 CHAIN_IDS 英文 slug")

    # 5. 模板结构
    templates = _load_json(TEMPLATES_CONFIG).get("templates") or []
    seen_ids: set[str] = set()
    for tpl in templates:
        tid = str(tpl.get("template_id") or "")
        if not tid:
            violations.append("存在缺 template_id 的模板")
        elif tid in seen_ids:
            violations.append(f"template_id 重复: {tid}")
        seen_ids.add(tid)
        layers = tpl.get("layers") or []
        if len(layers) != 8:
            violations.append(f"模板[{tid}] 层数={len(layers)}, 期望 8")
        orders = sorted(int(l.get("order") or 0) for l in layers)
        if orders != list(range(1, 9)):
            violations.append(f"模板[{tid}] layer order 非 1..8: {orders}")
        layer_ids = [str(l.get("layer_id") or "") for l in layers]
        if any(not lid for lid in layer_ids) or len(set(layer_ids)) != len(layer_ids):
            violations.append(f"模板[{tid}] layer_id 为空或重复: {layer_ids}")
        if not str(tpl.get("example_theme") or "").strip():
            violations.append(f"模板[{tid}] 缺 example_theme")

    # 6. 关键词重复
    for cname, cd in chains.items():
        for layer, kws in (cd.get("layer_keywords") or {}).items():
            dups = sorted({kw for kw in kws if kws.count(kw) > 1})
            if dups:
                violations.append(f"链[{cname}] 层[{layer}] 关键词重复: {dups}")

    return violations


def main() -> int:
    violations = validate()
    if violations:
        print(f"产业链配置校验失败, 共 {len(violations)} 项违规:")
        for i, v in enumerate(violations, 1):
            print(f"  {i}. {v}")
        return 1
    print("产业链配置校验通过: 双副本一致 / 层键对齐 / profile 与 CHAIN_IDS 覆盖 / 模板结构 / 关键词无重复")
    return 0


if __name__ == "__main__":
    sys.exit(main())
