class BiTrendAdapter:
    model_key = "bi_trend_launch"
    def run(self, request, readiness):
        return {"status": "insufficient_data", "model_key": self.model_key, "missing_requirements": ["observed_factor_snapshots", "future_adjusted_returns"]}
