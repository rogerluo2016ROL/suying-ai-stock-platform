import pandas as pd

from kronos_factors.backtest.bom_universe import (
    build_cutoff_universe_from_cache,
    has_visible_node_evidence,
    infer_embodied_node,
)


def test_infer_embodied_node_from_product_keywords():
    assert infer_embodied_node("精密谐波减速器组件") == "reducer"
    assert infer_embodied_node("机器人运动控制器") == "controller"
    assert infer_embodied_node("普通注塑件") is None


def test_build_cutoff_universe_uses_latest_visible_mainbz_period_and_ratio():
    mainbz = pd.DataFrame(
        [
            {"code6": "688017", "end_date": "20231231", "bz_item": "普通零件", "bz_sales": 900},
            {"code6": "688017", "end_date": "20241231", "bz_item": "谐波减速器", "bz_sales": 300},
            {"code6": "688017", "end_date": "20241231", "bz_item": "其他业务", "bz_sales": 700},
            {"code6": "300503", "end_date": "20251231", "bz_item": "运动控制器", "bz_sales": 1000},
        ]
    )

    universe = build_cutoff_universe_from_cache(
        mainbz_df=mainbz,
        qa_df=pd.DataFrame(),
        research_df=pd.DataFrame(),
        cutoff_yyyymmdd="20250630",
    )

    assert universe == {"688017": ("reducer", "谐波减速器", 30.0)}


def test_build_cutoff_universe_can_require_visible_evidence():
    mainbz = pd.DataFrame(
        [
            {"code6": "002708", "end_date": "20241231", "bz_item": "精密轴承", "bz_sales": 500},
            {"code6": "002708", "end_date": "20241231", "bz_item": "其他业务", "bz_sales": 500},
            {"code6": "688017", "end_date": "20241231", "bz_item": "谐波减速器", "bz_sales": 400},
            {"code6": "688017", "end_date": "20241231", "bz_item": "其他业务", "bz_sales": 600},
        ]
    )
    qa = pd.DataFrame(
        [
            {
                "code6": "688017",
                "trade_date": "20250301",
                "q": "机器人业务进展？",
                "a": "公司谐波减速器已进入客户验证阶段。",
            },
            {
                "code6": "002708",
                "trade_date": "20250701",
                "q": "轴承业务？",
                "a": "精密轴承已有订单。",
            },
        ]
    )

    assert has_visible_node_evidence(
        "688017",
        "reducer",
        "谐波减速器",
        qa_df=qa,
        research_df=pd.DataFrame(),
        cutoff_yyyymmdd="20250630",
    )
    universe = build_cutoff_universe_from_cache(
        mainbz_df=mainbz,
        qa_df=qa,
        research_df=pd.DataFrame(),
        cutoff_yyyymmdd="20250630",
        require_evidence=True,
    )

    assert universe == {"688017": ("reducer", "谐波减速器", 40.0)}
