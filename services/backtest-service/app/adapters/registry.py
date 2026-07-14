from .bi_trend import BiTrendAdapter
from .cb_auction_t0 import CbAuctionT0Adapter
from .supply_chain_selection_v2 import SupplyChainSelectionV2Adapter

BACKTEST_ADAPTERS = {
    "bi_trend_launch": BiTrendAdapter(),
    "cb_auction_t0": CbAuctionT0Adapter(),
    "supply_chain_research_selection_v2": SupplyChainSelectionV2Adapter(),
}


def get_adapter(model_key):
    return BACKTEST_ADAPTERS.get(model_key)
