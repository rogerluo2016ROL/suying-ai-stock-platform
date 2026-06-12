#!/usr/bin/env python3
"""Import CB concept classification data from 腾讯文档 into cb_concept table.

数据来源: 400只转债概念分类 (用户手工维护)
用法: python tools/import_cb_concept.py
"""

import psycopg2, psycopg2.extras, re, os

PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")

# ── 概念→转债名称列表 (从腾讯文档提取) ──
CONCEPT_DATA = {
    "商业航天": "瑞可转债、立昂转债、澳弘转债、中陆转债、聚隆转债、声迅转债、华设转债、广泰转债、航新转债、宏图转债、航宇转债",
    "军工": "广泰转债、航新转债、三角转债、天箭转债、宏图转债",
    "人形机器人": "福新转债、华懋转债、集智转债、佳禾转债、万讯转债、申昊转债、联得转债、博实转债、盈丰转债、天准转债",
    "可控核聚变": "应流转债、精达转债、利柏转债、天箭转债",
    "福建板块": "华懋转债、兴业转债、福能转债",
    "AI手机眼镜": "春23转债、精测转债",
    "创新药": "博瑞转债、共同转债、九典转债",
    "数字货币": "银信转债、科蓝转债",
    "人工智能（软件方向）": "润达转债、思特转债、丝路转债、风语转债",
    "算力": "奥飞转债、思特转债、锦鸡转债、中贝转债、京源转债、佳力转债、亿田转债",
    "华为概念": "科蓝转债、润达转债、博俊转债、精测转2、春23转债、超达转债",
    "半导体、芯片、集成电路": "力合转债、华亚转债、华特转债、强力转债、韦尔转债、国微转债、闻泰转债、富瀚转债、超声转债、洁美转债、银微转债、芯海转债、立昂转债、晶瑞转2、睿创转债、甬矽转债、路维转债、鼎龙转债、正帆转债、微导转债、颀中转债、茂莱转债",
    "消费电子": "兴瑞转债、立讯转债、华兴转债、科沃转债、小熊转债、莱克转债、爱玛转债、精测转2、春23转债、海能转债、佳禾转债、欧通转债、银邦转债、安克转债、微导转债、胜蓝转02、茂莱转债",
    "数字经济": "佳力转债、奥飞转债、思特转债、恒锋转债、声迅转债、银信转债、科蓝转债、丝路转债、风语转债、卫宁转债、山石转债、正元转02、姚记转债、浩瀚转债、普联转债、鼎捷转债",
    "正股高股息": "洪城转债、平煤转债、弘亚转债、蓝天转债、上银转债、兴业转债、重银转债",
    "一带一路": "海波转债、精工转债、鸿路转债、建工转债、翔丰转债",
    "文化传媒": "姚记转债、丝路转债、天创转债",
    "产品出海": "嘉益转债、柳工转2、乐歌转债",
    "5G、6G通信": "中贝转债、瑞可转债、神宇转债",
    "中字头": "中特转债",
    "锂电池": "国泰转债、洋丰转债、万顺转2、天奈转债、科利转债、芳源转债、宙邦转债、冠宇转债、锂科转债、大中转债、海顺转债、蓝晓转02、翔丰转债、电化转债",
    "汽车及零部件": "上声转债、岱美转债、长汽转债、威唐转债、银轮转债、麒麟转债、明新转债、道通转债、顺博转债、爱迪转债、亚科转债、超达转债、国力转债、聚隆转债、博俊转债、华懋转债、铭利转债、保隆转债、伯25转债、锡振转债、恒帅转债、凯众转债、卓镁转债",
    "光伏风电": "宇邦转债、中陆转债、隆22转债、通22转债、天能转债、晶科转债、晶能转债、嘉泽转债、节能转债、帝尔转债、裕兴转债、通裕转债、福莱转债、福22转债、垒知转债、天23转债、中旗转债、能辉转债、晶澳转债、双良转债、奥维转债、芯能转债、欧晶转债、清源转债、太能转债、锦浪转02",
    "电力": "起帆转债、精达转债、申昊转债、百畅转债、新港转债、煜邦转债、广核转债、华辰转债、福能转债",
    "房地产产业链": "精装转债、华阳转债、华设转债、万青转债、冀东转债、帝欧转债、蒙娜转债、江山转债、豪美转债、欧22转债、火星转债、小熊转债、金23转债、志邦转债、建工转债、海波转债、鸿路转债、精工转债、东南转债、浙建转债、华阳转债、汇通转债、山路转债、科顺转债、利柏转债",
    "雅下水电站": "柳工转2、博22转债、文科转债、华设转债、建工转债、友发转债",
    "ST概念": "声迅转债、章鼓转债",
    "生物医药": "山河转债、九典转02、蓝帆转债、华海转债、灵康转债、万孚转债、宝莱转债、美诺转债、昌红转债、三诺转债、正川转债、大参转债、科华转债、健帆转债、康泰转2、珀莱转债、博瑞转债、洁特转债、九强转债、康医转债、微芯转债、共同转债、寿22转债、奕瑞转债、漱玉转债、花园转债、百洋转债、东亚转债、东宝转债、易瑞转债、益丰转债、楚天转债、奥锐转债、和邦转债、皓元转债、华医转债、金威转债",
    "医美": "珀莱转债、水羊转债、科思转债",
    "化工": "齐翔转2、长海转债、利民转债、盛虹转债、洋丰转债、瑞丰转债、锦鸡转债、双箭转债、苏利转债、阿拉转债、天业转债、丰山转债、博22转债、恒逸转2、瑞科转债、会通转债、新化转债、惠云转债、回天转债、优彩转债、福莱转债、三房转债、建龙转债、神马转债、赫达转债、阳谷转债、赛特转债、龙星转债、家联转债、合顺转债、万凯转债",
    "有色金属及加工": "金诚转债、金25转债、大中转债、金田转债、友发转债、精工转债、浙矿转债、丽岛转债",
    "钢铁": "本钢转债、甬金转债、中特转债、武进转债",
    "煤炭及加工": "能化转债、美锦转债、永东转2、浙矿转债、平煤转债",
    "大金融": "紫银转债、上银转债、青农转债、兴业转债、重银转债、常银转债、财通转债、国投转债",
    "服装纺织": "天创转债、开润转债、太平转债、台21转债、富春转债、盛泰转债",
    "禽畜养殖": "温氏转债、龙大转债、牧原转债、希望转2、巨星转债、湘佳转债、禾丰转债、晓鸣转债、佩蒂转债",
    "食品饮料": "天润转债、百润转债、新乳转债、洽洽转债、龙大转债、仙乐转债、立高转债、李子转债、华康转债",
    "生态环保": "冠中转债、金埔转债、天源转债、旺能转债、侨银转债、绿茵转债、盈峰转债、文科转债、洪城转债、惠城转债、绿动转债、京源转债、伟22转债、伟24转债、严牌转债",
    "包装印刷": "万顺转2、鹤21转债、特纸转债、永吉转债、永02转债、福新转债、艾录转债",
    "物流运输": "韵达转债、宏川转债、南航转债、嘉诚转债、密卫转债、盛航转债",
    "商超零售": "家悦转债",
    "机械装备": "弘亚转债、艾迪转债、柳工转2、星球转债、运机转债、章鼓转债、泰坦转债、永贵转债、应流转债",
    "公用事业": "皖天转债、天壕转债、贵燃转债、蓝天转债、燃23转债、渝水转债、洪城转债",
    "妖债": "恒帅转债、天创转债",
}


def _clean_name(name: str) -> str:
    """Remove suffixes like '转债', '转2', '转02', '定转', 'K1' etc."""
    n = name.strip()
    # Remove common suffixes
    for suffix in ["转02", "转2", "转债", "定转", "定02", "K1", "转"]:
        if n.endswith(suffix) and len(n) > len(suffix):
            # But keep the suffix as part of the name for matching
            pass
    return n


def import_concepts():
    conn = psycopg2.connect(PG_URL)
    cur = conn.cursor()

    # Load cb_basic name → ts_code mapping
    cur.execute("SELECT ts_code, bond_short_name FROM cb_basic")
    cb_map = {}  # {short_name: ts_code}
    for r in cur.fetchall():
        cb_map[r[1]] = r[0]

    # Build extended mapping with aliases
    # Some names in the spreadsheet differ from cb_basic names
    # Try exact match first, then fuzzy
    total_written = 0
    not_found = []

    for concept, bond_list in CONCEPT_DATA.items():
        bonds = [b.strip() for b in bond_list.replace("、", ",").replace("\n", ",").split(",") if b.strip()]
        for bond_name in bonds:
            ts_code = cb_map.get(bond_name)
            if not ts_code:
                # Try fuzzy: strip trailing 转债/转2 etc
                for stored_name, stored_code in cb_map.items():
                    if bond_name in stored_name or stored_name in bond_name:
                        ts_code = stored_code
                        break
            if ts_code:
                try:
                    cur.execute(
                        "INSERT INTO cb_concept (ts_code, concept, bond_name) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (ts_code, concept, bond_name),
                    )
                    if cur.rowcount > 0:
                        total_written += 1
                except Exception:
                    pass
            else:
                not_found.append(bond_name)

    conn.commit()

    cur.execute("SELECT COUNT(*), COUNT(DISTINCT ts_code), COUNT(DISTINCT concept) FROM cb_concept")
    stats = cur.fetchone()
    print(f"导入完成: {stats[0]} 条映射, {stats[1]} 只转债, {stats[2]} 个概念")
    if not_found:
        print(f"未匹配 ({len(not_found)}): {', '.join(not_found[:20])}")

    conn.close()


if __name__ == "__main__":
    import_concepts()
