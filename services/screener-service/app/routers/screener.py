"""Compatibility entrypoint for the Screener HTTP contract.

Route implementation lives in the screening domain.  Keeping this facade
preserves imports used by existing integrations while preventing a new
monolithic router from growing here.
"""

import sys

from app.domains.screening import service as _service

# Preserve legacy monkeypatch/import behaviour: several integration tests and
# extension modules patch helpers on ``app.routers.screener`` directly.
sys.modules[__name__] = _service
