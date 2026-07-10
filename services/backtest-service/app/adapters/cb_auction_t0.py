class CbAuctionT0Adapter:
    model_key = "cb_auction_t0"
    def run(self, request, readiness):
        return {"status": "insufficient_data", "model_key": self.model_key, "missing_requirements": ["observed_factor_snapshots", "future_adjusted_returns"]}
