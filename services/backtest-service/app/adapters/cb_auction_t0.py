from .base import evaluate_request, load_cb_factor_rows

class CbAuctionT0Adapter:
    model_key = "cb_auction_t0"
    def run(self, request, readiness):
        if not readiness or readiness.get("status") != "ready":
            return {"status": "blocked", "model_key": self.model_key,
                    "missing_requirements": ["data_readiness"]}
        if request.connection_factory is None:
            return {"status": "insufficient_data", "model_key": self.model_key,
                    "missing_requirements": ["database_connection"]}
        connection = request.connection_factory()
        try:
            report = evaluate_request(load_cb_factor_rows(connection, request), request)
        finally:
            connection.close()
        return {"model_key": self.model_key, **report}
