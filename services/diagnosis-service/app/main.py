"""Diagnosis Service — 5-dimensional stock analysis.

Usage: python -m uvicorn app.main:app --port 8009 --reload
"""
import os
import sys

# 注入共享 packages(须在 import app.routes 前——routes 依赖 kronos-factors/core/data)
_PACKAGES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages"))
for _pkg in ["kronos-factors", "kronos-core", "kronos-data"]:
    _path = os.path.join(_PACKAGES, _pkg)
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

from app.routes import router
from kronos_contracts.app_factory import create_app

app = create_app(
    "diagnosis-service",
    "0.1.0",
    [router],
    description="5-dimensional stock diagnosis — technical, capital, fundamental, AI, sentiment",
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8009, reload=True)
