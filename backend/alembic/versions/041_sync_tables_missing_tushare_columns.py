"""Add missing Tushare-native columns to 8 sync tables.

Revision ID: 041
Revises: 040
Create Date: 2026-07-23

背景: data-service 全表回补 (2026-07-23) 中 _insert_rows 告警丢弃 8 张表的
Tushare 原生列 (表结构缺列, 数据静默丢失):

- announcements:        url, rec_time
- financial_balance:    total_cur_assets, total_liab, total_cur_liab,
                        total_hldr_eqy_exc_min_int, total_share, cap_rese, undistr_porfit
- financial_cashflow:   n_cashflow_act, n_cashflow_inv_act, n_cashflow_fin_act,
                        c_fr_sale_sg, net_profit
- financial_income:     basic_eps, revenue, oper_cost, sell_expense, admin_expense,
                        fin_expense, n_income, n_income_attr_p, operate_profit, total_profit
- hk_holdings:          hold_vol
- index_basic:          category, base_date, base_point, list_date
- margin_detail:        rqyl
- moneyflow:            net_mf_vol
- stk_holdertrade:      in_de

注意: 均为 ADD COLUMN IF NOT EXISTS (幂等); 存量行新列为 NULL,
同步路径是 ON CONFLICT DO NOTHING, 不回填历史——新数据/新报告期自动带全列。
financial_income 的 revenue/operate_profit 与既有 total_revenue/operating_profit
是 Tushare 原生名 vs 早期英文别名并存 (历史包袱, 本迁移只补原生名列)。
"""

from typing import Sequence, Union

from alembic import op


revision: str = "041"
down_revision: Union[str, None] = "040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, [(column, type), ...])
_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "announcements": [
        ("url", "TEXT"),
        ("rec_time", "TIMESTAMP"),
    ],
    "financial_balance": [
        ("total_cur_assets", "DOUBLE PRECISION"),
        ("total_liab", "DOUBLE PRECISION"),
        ("total_cur_liab", "DOUBLE PRECISION"),
        ("total_hldr_eqy_exc_min_int", "DOUBLE PRECISION"),
        ("total_share", "DOUBLE PRECISION"),
        ("cap_rese", "DOUBLE PRECISION"),
        ("undistr_porfit", "DOUBLE PRECISION"),
    ],
    "financial_cashflow": [
        ("n_cashflow_act", "DOUBLE PRECISION"),
        ("n_cashflow_inv_act", "DOUBLE PRECISION"),
        ("n_cashflow_fin_act", "DOUBLE PRECISION"),
        ("c_fr_sale_sg", "DOUBLE PRECISION"),
        ("net_profit", "DOUBLE PRECISION"),
    ],
    "financial_income": [
        ("basic_eps", "DOUBLE PRECISION"),
        ("revenue", "DOUBLE PRECISION"),
        ("oper_cost", "DOUBLE PRECISION"),
        ("sell_expense", "DOUBLE PRECISION"),
        ("admin_expense", "DOUBLE PRECISION"),
        ("fin_expense", "DOUBLE PRECISION"),
        ("n_income", "DOUBLE PRECISION"),
        ("n_income_attr_p", "DOUBLE PRECISION"),
        ("operate_profit", "DOUBLE PRECISION"),
        ("total_profit", "DOUBLE PRECISION"),
    ],
    "hk_holdings": [
        ("hold_vol", "DOUBLE PRECISION"),
    ],
    "index_basic": [
        ("category", "TEXT"),
        ("base_date", "TEXT"),
        ("base_point", "DOUBLE PRECISION"),
        ("list_date", "TEXT"),
    ],
    "margin_detail": [
        ("rqyl", "DOUBLE PRECISION"),
    ],
    "moneyflow": [
        ("net_mf_vol", "DOUBLE PRECISION"),
    ],
    "stk_holdertrade": [
        ("in_de", "TEXT"),
    ],
}


def upgrade() -> None:
    for table, columns in _COLUMNS.items():
        for column, col_type in columns:
            op.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
            )


def downgrade() -> None:
    for table, columns in _COLUMNS.items():
        for column, _col_type in columns:
            op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}")
