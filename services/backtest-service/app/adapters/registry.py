from .bi_trend import BiTrendAdapter
from .cb_auction_t0 import CbAuctionT0Adapter

BACKTEST_ADAPTERS = {"bi_trend_launch": BiTrendAdapter(), "cb_auction_t0": CbAuctionT0Adapter()}
