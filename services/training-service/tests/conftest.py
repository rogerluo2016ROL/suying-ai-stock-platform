"""pytest 配置: training-service 测试隔离.

把 training-service 自身目录 (含 ``app`` 包) 加入 sys.path, 这样测试可写
``from app.training_engine import ...``. pytest 以本服务目录为 rootdir 运行
(``cd services/training-service && pytest tests/``), 不会与 backend 的 ``app``
包冲突 — 每个服务 pytest 会话只看见自己的 ``app``.

这是仓库既定的服务测试模式 (见 screener/trade/strategy-service/tests/),
替代之前在 backend/tests/ml/ 里用 sys.path.insert + sys.modules.pop("app")
hack 注入 training-service app 的做法 (W-1, ML-P0 review).
"""
import os
import sys

_SVC_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SVC_ROOT not in sys.path:
    sys.path.insert(0, _SVC_ROOT)
